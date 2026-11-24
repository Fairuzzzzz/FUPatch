"""Observe and optionally relocate selected MHFU draw operations in LLDB.

Import in the LLDB session attached to the already-running MH Unite process:
    command script import /path/to/mh_layout_explorer.py
    mhgrid install

Installation only adds an auto-continuing breakpoint. Discovery is the default;
register relocation requires an explicit `mhgrid move` followed by `mhgrid on`.
Only the current invocation's x1/x2 registers are changed; target memory is
never written. Coordinates are absolute renderer units, not verified physical
screen pixels. Confirm a draw visually before enabling relocation.
"""

import lldb
import shlex
import struct


EXPECTED_UUID = "58cc55c760ca3196b5d20c2aeb64b32b"
EXECUTABLE_NAME = "MH Unite"

# The documented low-level draw operation. The old script's 0x100378D14
# wrapper and 0x1003A4158 caller were not corroborated in the research notes.
DRAW_UNSLID = 0x100378D6C
MAX_OPERATIONS = 64
MAX_CALLBACKS = 512

_state = {
    "breakpoint": None,
    "module": None,
    "slide": None,
    "enabled": False,
    "selected": None,
    "destinations": {},
    "operations": {},
    "counts": {},
    "last": {},
    "callback_hits": 0,
}


def _register(frame, name):
    value = frame.FindRegister(name)
    if not value or not value.IsValid():
        return None
    return value.GetValueAsUnsigned()


def _signed32(value):
    if value is None:
        return None
    value &= 0xffffffff
    return value - 0x100000000 if value & 0x80000000 else value


def _atlas_from_stack(frame):
    """Read the documented atlas selector at entry SP+8; never write memory."""
    sp = _register(frame, "sp")
    process = frame.GetThread().GetProcess()
    if sp is None or not process or not process.IsValid():
        return None
    error = lldb.SBError()
    data = process.ReadMemory(sp + 8, 4, error)
    if not error.Success() or len(data) != 4:
        return None
    return struct.unpack("<I", data)[0]


def _module(target):
    for module in target.module_iter():
        spec = module.GetFileSpec()
        if spec and spec.GetFilename() == EXECUTABLE_NAME:
            uuid = (module.GetUUIDString() or "").replace("-", "").lower()
            if uuid != EXPECTED_UUID:
                raise RuntimeError(
                    "Refusing probe: MH Unite UUID is %s, expected %s"
                    % (uuid or "<missing>", EXPECTED_UUID)
                )
            return module
    raise RuntimeError("Loaded MH Unite executable was not found")


def _resolve(target, module, unslid):
    file_address = module.ResolveFileAddress(unslid)
    if not file_address or not file_address.IsValid():
        raise RuntimeError("Unslid address did not resolve: 0x%x" % unslid)
    load_address = file_address.GetLoadAddress(target)
    if load_address == lldb.LLDB_INVALID_ADDRESS:
        raise RuntimeError("Address is not loaded: 0x%x" % unslid)
    return load_address, load_address - unslid


def _operation_key(frame, atlas):
    # Coordinates x1/x2 are deliberately excluded so animated/moving calls
    # remain the same operation. Remaining arguments distinguish same-caller
    # draws where possible; inspect the logged values before selecting one.
    lr = _register(frame, "lr")
    stable_args = tuple(_register(frame, "x%d" % i) for i in range(3, 8))
    return (lr, atlas) + stable_args


def _format_key(key):
    return "lr=%s atlas=%s stable=%s" % (
        "?" if key[0] is None else "0x%x" % key[0],
        "?" if key[1] is None else str(key[1]),
        ",".join("?" if value is None else "0x%x" % value
                 for value in key[2:]),
    )


def on_draw(frame, bp_loc, internal_dict):
    try:
        _state["callback_hits"] += 1
        atlas = _atlas_from_stack(frame)
        key = _operation_key(frame, atlas)
        operations = _state["operations"]
        if key not in operations:
            if len(operations) >= MAX_OPERATIONS:
                slot = None
            else:
                operations[key] = len(operations)
                slot = operations[key]
        else:
            slot = operations[key]

        if slot is not None:
            _state["counts"][slot] = _state["counts"].get(slot, 0) + 1
            args = tuple(_register(frame, "x%d" % i) for i in range(8))
            _state["last"][slot] = {
                "args": args,
                "atlas": atlas,
                "sp": _register(frame, "sp"),
            }

            destination = _state["destinations"].get(slot)
            if (_state["enabled"] and _state["selected"] == slot
                    and destination is not None):
                xreg = frame.FindRegister("x1")
                yreg = (frame.FindRegister("x2")
                        if destination[1] is not None else None)
                old_x, old_y = args[1], args[2]
                ok_x = xreg.SetValueFromCString(str(destination[0]))
                ok_y = (True if yreg is None else
                        yreg.SetValueFromCString(str(destination[1])))
                if not (ok_x and ok_y):
                    # Best-effort rollback of this invocation's register edit.
                    if old_x is not None:
                        xreg.SetValueFromCString(str(old_x))
                    if old_y is not None and yreg is not None:
                        yreg.SetValueFromCString(str(old_y))
                    _state["enabled"] = False
                    print("mhgrid: register edit failed; relocation disabled")
        if _state["callback_hits"] >= MAX_CALLBACKS:
            bp_loc.GetBreakpoint().SetEnabled(False)
            print("mhgrid: bounded capture reached %d callbacks; "
                  "breakpoint disabled" % MAX_CALLBACKS)
    except Exception as exc:
        # A diagnostic callback must not leave the game stopped or crash LLDB.
        print("mhgrid callback warning: %s" % exc)
    return False


def install(debugger):
    target = debugger.GetSelectedTarget()
    if not target or not target.IsValid():
        raise RuntimeError("No selected LLDB target")
    process = target.GetProcess()
    if not process or not process.IsValid():
        raise RuntimeError("Attach to the already-running game first")
    if process.GetState() != lldb.eStateStopped:
        raise RuntimeError("Stop the process in LLDB before installing")
    if _state["breakpoint"] is not None:
        raise RuntimeError("Explorer is already installed")

    module = _module(target)
    address, slide = _resolve(target, module, DRAW_UNSLID)
    bp = target.BreakpointCreateByAddress(address)
    if not bp or not bp.IsValid() or bp.GetNumLocations() == 0:
        if bp and bp.IsValid():
            target.BreakpointDelete(bp.GetID())
        raise RuntimeError("Could not resolve draw breakpoint at 0x%x" % address)

    bp.SetScriptCallbackFunction(__name__ + ".on_draw")
    try:
        bp.SetAutoContinue(True)
    except Exception:
        pass

    _state.update({
        "breakpoint": bp.GetID(),
        "module": module,
        "slide": slide,
        "enabled": False,
        "selected": None,
        "destinations": {},
        "operations": {},
        "counts": {},
        "last": {},
        "callback_hits": 0,
    })
    print("Observe-only draw probe installed: bp %d" % bp.GetID())
    print("UUID: %s" % EXPECTED_UUID)
    print("ASLR slide: 0x%x" % slide)
    print("Unslid draw: 0x%x -> runtime 0x%x" % (DRAW_UNSLID, address))
    print("Relocation is OFF. Use `mhgrid list` to inspect captured operations.")


def uninstall(debugger):
    bp_id = _state["breakpoint"]
    if bp_id is not None:
        debugger.GetSelectedTarget().BreakpointDelete(bp_id)
    _state.update({
        "breakpoint": None,
        "module": None,
        "slide": None,
        "enabled": False,
        "selected": None,
        "destinations": {},
        "operations": {},
        "counts": {},
        "last": {},
        "callback_hits": 0,
    })
    print("mhgrid breakpoint removed; relocation is OFF")


def show():
    print("Probe: %s; slide: %s; relocation: %s; selected: %s; "
          "capture hits: %d/%d" % (
        _state["breakpoint"],
        "unknown" if _state["slide"] is None
        else "0x%x" % _state["slide"],
        "ON" if _state["enabled"] else "OFF",
        _state["selected"],
        _state["callback_hits"],
        MAX_CALLBACKS,
    ))
    for key, slot in sorted(_state["operations"].items(),
                            key=lambda item: item[1]):
        last = _state["last"].get(slot, {})
        args = last.get("args", ())
        xy = (None, None) if len(args) < 3 else (
            _signed32(args[1]), _signed32(args[2]))
        print("  %02d hits=%d %s x/y=%s destination=%s" % (
            slot,
            _state["counts"].get(slot, 0),
            _format_key(key),
            xy,
            _state["destinations"].get(slot, "<observe-only>"),
        ))


class Command:
    def __init__(self, debugger, internal_dict):
        pass

    def __call__(self, debugger, command, exe_ctx, result):
        try:
            args = shlex.split(command)
            action = args[0] if args else "list"

            if action == "install":
                install(debugger)
            elif action in ("list", "status"):
                show()
            elif action == "select":
                if len(args) != 2:
                    raise ValueError("Usage: mhgrid select SLOT")
                slot = int(args[1], 0)
                if slot not in _state["counts"]:
                    raise ValueError("Unknown slot; inspect `mhgrid list`")
                _state["selected"] = slot
                print("Selected operation %d (relocation remains %s)" % (
                    slot, "ON" if _state["enabled"] else "OFF"))
            elif action == "move":
                if len(args) != 3:
                    raise ValueError(
                        "Usage: mhgrid move ABSOLUTE_RENDER_X ABSOLUTE_RENDER_Y")
                if _state["selected"] is None:
                    raise ValueError("Select an operation first")
                x, y = int(args[1], 0), int(args[2], 0)
                if not (-0x80000000 <= x <= 0x7fffffff
                        and -0x80000000 <= y <= 0x7fffffff):
                    raise ValueError("Coordinates must fit signed 32-bit values")
                _state["destinations"][_state["selected"]] = (x, y)
                _state["enabled"] = False
                print("Destination set to absolute renderer coordinates (%d,%d). "
                      "Effect remains OFF; inspect and use `mhgrid on` "
                      "to apply." % (x, y))
            elif action == "move-x":
                if len(args) != 2:
                    raise ValueError("Usage: mhgrid move-x ABSOLUTE_RENDER_X")
                if _state["selected"] is None:
                    raise ValueError("Select an operation first")
                x = int(args[1], 0)
                if not -0x80000000 <= x <= 0x7fffffff:
                    raise ValueError("X must fit a signed 32-bit value")
                _state["destinations"][_state["selected"]] = (x, None)
                _state["enabled"] = False
                print("Absolute renderer X set to %d; Y remains unchanged. "
                      "Effect remains OFF until `mhgrid on`." % x)
            elif action == "on":
                if _state["selected"] is None:
                    raise ValueError("Select an operation first")
                if _state["selected"] not in _state["destinations"]:
                    raise ValueError(
                        "Set an absolute destination with `move` or `move-x`")
                _state["enabled"] = True
                print("Relocation ON for operation %d at %s" % (
                    _state["selected"],
                    _state["destinations"][_state["selected"]]))
            elif action == "off":
                _state["enabled"] = False
                print("Relocation OFF; original call coordinates are used")
            elif action == "restore":
                _state["enabled"] = False
                if _state["selected"] is not None:
                    _state["destinations"].pop(_state["selected"], None)
                print("Relocation OFF; selected operation uses original coordinates")
            elif action == "clear":
                _state["enabled"] = False
                _state["selected"] = None
                _state["destinations"].clear()
                _state["operations"].clear()
                _state["counts"].clear()
                _state["last"].clear()
                _state["callback_hits"] = 0
                bp = debugger.GetSelectedTarget().FindBreakpointByID(
                    _state["breakpoint"]) if _state["breakpoint"] is not None else None
                if bp and bp.IsValid():
                    bp.SetEnabled(True)
                print("Captured operations cleared; relocation OFF")
            elif action == "resume":
                if _state["breakpoint"] is None:
                    raise ValueError("Install the explorer first")
                target = debugger.GetSelectedTarget()
                bp = target.FindBreakpointByID(_state["breakpoint"])
                if not bp or not bp.IsValid():
                    raise ValueError("Explorer breakpoint no longer exists")
                _state["callback_hits"] = 0
                bp.SetEnabled(True)
                print("Bounded observe-only capture resumed; relocation is %s" %
                      ("ON" if _state["enabled"] else "OFF"))
            elif action == "uninstall":
                uninstall(debugger)
            else:
                raise ValueError(
                    "Commands: install, list, select SLOT, move X Y, move-x X, "
                    "on, off, restore, clear, resume, uninstall"
                )
        except Exception as exc:
            result.SetError(str(exc))


def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand(
        "command script add -c mh_layout_explorer.Command mhgrid"
    )
    print("Visual Layout Explorer loaded. Relocation is OFF by default.")
