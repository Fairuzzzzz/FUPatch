# Read-only LLDB probe attempt — aborted before attach

**Status:** Aborted. No LLDB session was launched and no game process was
attached.

## Requested target

- Device identifier: `EB90DDE0-50FB-5593-A792-E211E636A9EC`
- Expected game bundle: `jp.co.capcom.mhp2g`
- User-reported PID: `29949` (not independently verified during this attempt)

## Preflight and outcome

The available research documents `docs/research.md`,
`docs/research-phase4.md`, and `docs/research-phase5.md` were read. The requested
`docs/PROJECT_HANDOFF.md` is absent from this checkout.

Read-only `devicectl` checks failed before LLDB attachment:

- Device details returned partial model/software information, followed by
  `The device disconnected immediately after connecting`.
- Reported device state included `tunnelState: disconnected` and
  `ddiServicesAvailable: false`.
- The process-list query failed to establish a connection to the device
  (`CoreDeviceError error 4000`); it did not confirm PID `29949`.
- The installed-app query failed with the same connection error; it did not
  confirm the current game process.

Because the device/process could not be verified as available, the experiment
stopped here. No LLDB command was run, no attach was attempted, and therefore no
current ASLR slide, loaded executable UUID, Cockpit singleton pointer, or menu
field values were obtained. No detachment was necessary because no debugger was
attached. No breakpoint, watchpoint, process-memory write, or register write
occurred.

## Address evidence and limits

The Phase 4 research includes an LLDB example that reads a pointer from unslid
address `0x100732FC0` after resolving it in the loaded `MH Unite` module. The
available documents do not provide a separately resolved named symbol for
`Singleton<Cockpit>::objectPtr`; `0x100732FC0` is a historical address
reference, not a current-session verification. It must not be used at runtime
until the device connection, executable UUID, and address resolution are
verified in the attached session.

## Next safe step

Re-establish the iPad connection, then repeat only the read-only preflight.
Proceed to LLDB attachment only after the device and running process are
confirmed. This report records the failed preflight; it does not claim the
requested LLDB inspection succeeded.

## Retry attempt

The available research documents `docs/research.md` and
`docs/research-phase4.md` were re-read. `docs/PROJECT_HANDOFF.md` remains absent;
`docs/research-phase5.md`, referenced in the prior attempt notes, is also absent
from the current checkout.

`xcrun devicectl list devices` returned the target device as **`available
(paired)`**, not `connected`. Per the instruction to stop if disconnected, no
developer-service query, process enumeration, LLDB launch, or attach was
attempted. The current game PID and developer-service availability therefore
remain unverified. No device process was touched.

**Retry status:** Stopped at connectivity preflight. The requested live
inspection and clean-detach verification have not occurred.

## Second retry attempt

Read-only preflight observations:

- `xcrun devicectl list devices` again reported the iPad as
  **`available (paired)`**, not `connected`.
- `xcrun devicectl device info processes` succeeded and independently showed
  MH Unite at PID `29949`, path
  `/private/var/containers/Bundle/Application/1A491814-FC3E-4E16-A688-C5896AD06220/MH Unite.app/MH Unite`.
  The command reported acquiring a tunnel, enabling developer disk image
  services, and acquiring a usage assertion.
- LLDB's own `device list` reported that same device as **`disconnected`**.

One LLDB batch then selected the supplied device identifier. The command
returned `Succeeded() == false`, with an empty LLDB command output and error
string. The captured result was:

```text
{"device_select":{"error":"","output":"","succeeded":false},
 "inspection":"failed",
 "failure":"device select failed",
 "pid":29949,
 "selected_device":"EB90DDE0-50FB-5593-A792-E211E636A9EC"}
```

Because LLDB could not select the device, `device process attach --pid 29949`
was **not issued**. No automatic recovery or second attach attempt was made.
Consequently there are no current LLDB-derived slide, UUID, singleton-pointer,
or menu-field observations; no LLDB detachment was needed. The game was verified
running by `devicectl` immediately before this LLDB selection attempt, but was
not queried again afterward.

**Second retry status:** Stopped before attachment because the device was
disconnected in LLDB. This attempt did not inspect or modify the game process.

## Third retry attempt

Research review: `docs/research.md`, `docs/research-phase4.md`, and this report
were read before the attempt. `docs/PROJECT_HANDOFF.md` remains absent.

### Device and process preflight

- `xcrun devicectl list devices` reported the target as `available (paired)`.
- The read-only `devicectl device info processes` query successfully acquired a
  tunnel and listed MH Unite as PID `29949` at:
  `/private/var/containers/Bundle/Application/1A491814-FC3E-4E16-A688-C5896AD06220/MH Unite.app/MH Unite`.
- LLDB's `device list` reported the same device as `connected` (iOS 18.7.3,
  build `22H217`).
- A direct LLDB `device select EB90DDE0-50FB-5593-A792-E211E636A9EC` command
  emitted no diagnostic text.

### Bounded attach-batch selection result

In the subsequent single LLDB batch intended to select the device and attach,
the `device select` command returned `Succeeded() == false` with empty command
output and error text. The exact captured JSON result for that stage was:

```text
{"device_select":{"error":"","output":"","succeeded":false},
 "failure":"device select failed",
 "inspection":"failed",
 "pid":29949,
 "selected_device":"EB90DDE0-50FB-5593-A792-E211E636A9EC"}
```

Per instruction, the batch stopped at this failure. The attach command was not
issued; there was no LLDB attachment, memory read, breakpoint, or write, and no
detachment was needed. The process was confirmed running immediately before
this LLDB batch, but was not queried again afterward.

**Third retry status:** Device/process communication worked through `devicectl`;
LLDB listed the device as connected, but device selection failed inside the
attach batch. The experiment stopped before attachment. No ASLR slide, current
singleton pointer, or current menu-state values were obtained.

## Automated read-only LLDB retry — 2026-11-24T02:56:26.016693+00:00

```json
{
  "current_pid": 29949,
  "device_id": "EB90DDE0-50FB-5593-A792-E211E636A9EC",
  "devicectl_list_exit_code": 0,
  "devicectl_process_line": "29949   /private/var/containers/Bundle/Application/1A491814-FC3E-4E16-A688-C5896AD06220/MH Unite.app/MH Unite",
  "devicectl_process_list_exit_code": 0,
  "devicectl_target_listed": true,
  "game_bundle_id": "jp.co.capcom.mhp2g",
  "lldb_exit_code": 0,
  "lldb_result": {
    "attach": {
      "command": "device process attach --pid 29949",
      "error": "",
      "output": "",
      "result_status": 2,
      "result_status_name": "eReturnStatusSuccessFinishResult",
      "return_status": 2,
      "return_status_name": "eReturnStatusSuccessFinishResult",
      "succeeded": true
    },
    "attach_command": "device process attach --pid 29949",
    "attached_process_candidate": true,
    "attached_process_state": {
      "pid": 29949,
      "state": 3,
      "state_name": "eStateAttaching",
      "valid": true
    },
    "detach": {
      "command": "process detach",
      "error": "error: Process must be launched.\n",
      "output": "",
      "result_status": 6,
      "result_status_name": "eReturnStatusFailed",
      "return_status": 6,
      "return_status_name": "eReturnStatusFailed",
      "succeeded": false
    },
    "detached_process_state": {
      "pid": 29949,
      "state": 3,
      "state_name": "eStateAttaching",
      "valid": true
    },
    "detached_verified": false,
    "device_id": "EB90DDE0-50FB-5593-A792-E211E636A9EC",
    "device_process_list": {
      "command": "device process list",
      "error": "",
      "result_status": 2,
      "result_status_name": "eReturnStatusSuccessFinishResult",
      "return_status": 2,
      "return_status_name": "eReturnStatusSuccessFinishResult",
      "succeeded": true
    },
    "failure": "attached PID was not stopped; refusing inspection (state=eStateAttaching)",
    "inspection": "failed",
    "ll_db_pid_match": {
      "line": "29949  0                                                MH Unite",
      "name": "Unite",
      "pid": 29949
    },
    "preflight_pid": 29949,
    "process_list_command": "device process list",
    "selected_device_verified": true,
    "selection": {
      "command": "device select EB90DDE0-50FB-5593-A792-E211E636A9EC",
      "error": "",
      "output": "",
      "result_status": 5,
      "result_status_name": "eReturnStatusStarted",
      "return_status": 5,
      "return_status_name": "eReturnStatusStarted",
      "succeeded": false
    },
    "selection_command": "device select EB90DDE0-50FB-5593-A792-E211E636A9EC"
  },
  "safety": {
    "breakpoints": false,
    "game_launch": false,
    "memory_writes": false,
    "register_writes": false,
    "watchpoints": false
  },
  "status": "incomplete: inspect result and detach status above",
  "timestamp_utc": "2026-11-24T02:56:21.692702+00:00"
}
```

## Automated read-only LLDB retry — 2026-11-24T03:11:12.674313+00:00

```json
{
  "attachment_outcome": "unknown: LLDB ended without a final lifecycle result",
  "automatic_retry": false,
  "cleanup_note": "No retry or follow-up attach/detach command was issued.",
  "current_pid": 29949,
  "device_id": "EB90DDE0-50FB-5593-A792-E211E636A9EC",
  "devicectl_list_exit_code": 0,
  "devicectl_process_line": "29949   /private/var/containers/Bundle/Application/1A491814-FC3E-4E16-A688-C5896AD06220/MH Unite.app/MH Unite",
  "devicectl_process_list_exit_code": 0,
  "devicectl_target_listed": true,
  "failure": "stopped: LLDB result marker missing; target attachment state unknown",
  "game_bundle_id": "jp.co.capcom.mhp2g",
  "lldb_exit_code": 1,
  "lldb_result": null,
  "lldb_stderr": "error: <user expression 0>:1:1: unknown type name 'process'\n    1 | process detach\n      | ^\n",
  "lldb_stdout": "(lldb) script exec('import json\\nimport lldb\\nimport math\\nimport time\\n\\nDEVICE_ID = \\'EB90DDE0-50FB-5593-A792-E211E636A9EC\\'\\nEXPECTED_PID = 29949\\nEXPECTED_UUID = \\'58cc55c760ca3196b5d20c2aeb64b32b\\'\\nEXECUTABLE_NAME = \\'MH Unite\\'\\nOBJECT_PTR_UNSLID = 4302516160\\nATTACH_STATE_TIMEOUT_SECONDS = 30\\nDETACH_STATE_TIMEOUT_SECONDS = 20\\ndebugger = lldb.debugger\\ninterpreter = debugger.GetCommandInterpreter()\\nreport = {\\n    \"device_id\": DEVICE_ID,\\n    \"preflight_pid\": EXPECTED_PID,\\n    \"selection_command\": \"device select \" + DEVICE_ID,\\n    \"process_list_command\": \"device process list\",\\n    \"attach_command\": \"device process attach --pid \" + str(EXPECTED_PID),\\n    \"attached_process_candidate\": False,\\n    \"attach_attempted\": False,\\n    \"detach_attempted\": False,\\n    \"explicit_detach_attempted\": False,\\n    \"confirmed_attached\": False,\\n    \"attachment_outcome\": \"not attempted\",\\n    \"attach_state_transitions\": [],\\n    \"detach_state_transitions\": [],\\n}\\n\\nstatus_names = {\\n    getattr(lldb, name): name\\n    for name in dir(lldb)\\n    if name.startswith(\"eReturnStatus\")\\n}\\nstate_names = {\\n    getattr(lldb, name): name\\n    for name in dir(lldb)\\n    if name.startswith(\"eState\")\\n}\\nfinished_statuses = {\\n    lldb.eReturnStatusSuccessFinishNoResult,\\n    lldb.eReturnStatusSuccessFinishResult,\\n}\\nstarted_status = lldb.eReturnStatusStarted\\n\\ndef run_lldb_command(command):\\n    result = lldb.SBCommandReturnObject()\\n    status = interpreter.HandleCommand(command, result)\\n    status_value = int(status)\\n    result_status_value = int(result.GetStatus())\\n    return {\\n        \"command\": command,\\n        \"return_status\": status_value,\\n        \"return_status_name\": status_names.get(status_value, \"unknown\"),\\n        \"result_status\": result_status_value,\\n        \"result_status_name\": status_names.get(result_status_value, \"unknown\"),\\n        \"succeeded\": bool(result.Succeeded()),\\n        \"output\": result.GetOutput() or \"\",\\n        \"error\": result.GetError() or \"\",\\n    }\\n\\ndef process_state(process):\\n    if not process or not process.IsValid():\\n        return {\"valid\": False, \"pid\": None, \"state\": None, \"state_name\": \"invalid\"}\\n    state = int(process.GetState())\\n    return {\\n        \"valid\": True,\\n        \"pid\": int(process.GetProcessID()),\\n        \"state\": state,\\n        \"state_name\": state_names.get(state, \"unknown\"),\\n    }\\n\\ndef create_state_listener(process, name):\\n    listener = lldb.SBListener(name)\\n    broadcaster = process.GetBroadcaster()\\n    event_mask = lldb.SBProcess.eBroadcastBitStateChanged\\n    registered_mask = int(broadcaster.AddListener(listener, event_mask))\\n    if registered_mask & int(event_mask) == 0:\\n        raise RuntimeError(\"LLDB process-state listener registration failed\")\\n    return listener, broadcaster, event_mask\\n\\ndef remove_state_listener(listener, broadcaster, event_mask):\\n    try:\\n        broadcaster.RemoveListener(listener, event_mask)\\n    except Exception:\\n        pass\\n\\ndef observe_until_state(process, expected_state, timeout_seconds,\\n                        listener, broadcaster, event_mask, phase):\\n    observations = []\\n\\n    def record(source, state):\\n        state_value = int(state)\\n        observation = {\\n            \"source\": source,\\n            \"phase\": phase,\\n            \"pid\": int(process.GetProcessID()) if process.IsValid() else None,\\n            \"state\": state_value,\\n            \"state_name\": state_names.get(state_value, \"unknown\"),\\n        }\\n        observations.append(observation)\\n        print(\"MHFU_STATE_OBSERVATION=\" + json.dumps(observation, sort_keys=True),\\n              flush=True)\\n\\n    initial = process_state(process)\\n    if initial[\"state\"] is not None:\\n        record(\"initial snapshot\", initial[\"state\"])\\n    if not initial[\"valid\"] and expected_state != lldb.eStateDetached:\\n        return {\\n            \"reached\": False, \"timed_out\": False,\\n            \"reason\": phase + \": process handle became invalid\",\\n            \"final_state\": initial, \"observations\": observations,\\n        }\\n    if initial[\"valid\"] and initial[\"pid\"] != EXPECTED_PID:\\n        return {\\n            \"reached\": False, \"timed_out\": False,\\n            \"reason\": phase + \": process handle PID changed unexpectedly\",\\n            \"final_state\": initial, \"observations\": observations,\\n        }\\n    if initial[\"valid\"] and initial[\"state\"] == expected_state:\\n        return {\\n            \"reached\": True, \"timed_out\": False,\\n            \"reason\": \"expected state already observed\",\\n            \"final_state\": initial, \"observations\": observations,\\n        }\\n\\n    deadline = time.monotonic() + timeout_seconds\\n    terminal_states = {\\n        lldb.eStateInvalid, lldb.eStateUnloaded,\\n        lldb.eStateExited, lldb.eStateCrashed,\\n        lldb.eStateDetached,\\n    }\\n    while True:\\n        remaining = deadline - time.monotonic()\\n        if remaining <= 0:\\n            final = process_state(process)\\n            if final[\"state\"] is not None:\\n                record(\"timeout snapshot\", final[\"state\"])\\n            if final[\"valid\"] and final[\"pid\"] == EXPECTED_PID and final[\"state\"] == expected_state:\\n                return {\\n                    \"reached\": True, \"timed_out\": False,\\n                    \"reason\": \"expected state confirmed by final process snapshot\",\\n                    \"final_state\": final, \"observations\": observations,\\n                }\\n            return {\\n                \"reached\": False, \"timed_out\": True,\\n                \"reason\": phase + \": state wait timed out\",\\n                \"final_state\": final, \"observations\": observations,\\n            }\\n\\n        event = lldb.SBEvent()\\n        try:\\n            received = listener.WaitForEventForBroadcasterWithType(\\n                max(1, int(math.ceil(remaining))),\\n                broadcaster,\\n                event_mask,\\n                event,\\n            )\\n        except Exception as wait_error:\\n            final = process_state(process)\\n            if final[\"state\"] is not None:\\n                record(\"listener-error snapshot\", final[\"state\"])\\n            return {\\n                \"reached\": False, \"timed_out\": False,\\n                \"reason\": phase + \": listener wait failed: \" + str(wait_error),\\n                \"final_state\": final, \"observations\": observations,\\n            }\\n\\n        event_state = None\\n        event_pid = None\\n        if received:\\n            event_state = int(lldb.SBProcess.GetStateFromEvent(event))\\n            record(\"state-change event\", event_state)\\n            event_process = lldb.SBProcess.GetProcessFromEvent(event)\\n            if event_process and event_process.IsValid():\\n                event_pid = int(event_process.GetProcessID())\\n            observations[-1][\"event_pid\"] = event_pid\\n            observations[-1][\"is_process_event\"] = bool(\\n                lldb.SBProcess.EventIsProcessEvent(event)\\n            )\\n            if (not observations[-1][\"is_process_event\"]\\n                    or (event_pid is not None and event_pid != EXPECTED_PID)):\\n                return {\\n                    \"reached\": False, \"timed_out\": False,\\n                    \"reason\": phase + \": received event for an unexpected process\",\\n                    \"final_state\": process_state(process),\\n                    \"observations\": observations,\\n                }\\n\\n        current = process_state(process)\\n        if current[\"state\"] is not None:\\n            record(\"current process snapshot\", current[\"state\"])\\n        if not current[\"valid\"]:\\n            if (expected_state == lldb.eStateDetached\\n                    and received\\n                    and event_state == lldb.eStateDetached\\n                    and (event_pid is None or event_pid == EXPECTED_PID)):\\n                return {\\n                    \"reached\": True, \"timed_out\": False,\\n                    \"reason\": \"eStateDetached confirmed by target process event\",\\n                    \"final_state\": {\\n                        \"valid\": False,\\n                        \"pid\": event_pid or EXPECTED_PID,\\n                        \"state\": lldb.eStateDetached,\\n                        \"state_name\": state_names.get(\\n                            lldb.eStateDetached, \"eStateDetached\"\\n                        ),\\n                        \"confirmed_by\": \"process broadcaster event\",\\n                    },\\n                    \"observations\": observations,\\n                }\\n            if expected_state == lldb.eStateDetached:\\n                if received and event_state in terminal_states:\\n                    return {\\n                        \"reached\": False, \"timed_out\": False,\\n                        \"reason\": phase + \": unexpected terminal process event\",\\n                        \"final_state\": {\\n                            \"valid\": False,\\n                            \"pid\": event_pid or EXPECTED_PID,\\n                            \"state\": event_state,\\n                            \"state_name\": state_names.get(event_state, \"unknown\"),\\n                        },\\n                        \"observations\": observations,\\n                    }\\n                # The SBProcess may become invalid as detach completes before\\n                # its queued eStateDetached event is read. Wait boundedly for\\n                # that target-process event instead of assuming success.\\n                continue\\n            return {\\n                \"reached\": False, \"timed_out\": False,\\n                \"reason\": phase + \": process handle became invalid\",\\n                \"final_state\": current, \"observations\": observations,\\n            }\\n        if current[\"pid\"] != EXPECTED_PID:\\n            return {\\n                \"reached\": False, \"timed_out\": False,\\n                \"reason\": phase + \": process handle PID changed unexpectedly\",\\n                \"final_state\": current, \"observations\": observations,\\n            }\\n        if current[\"state\"] == expected_state:\\n            return {\\n                \"reached\": True, \"timed_out\": False,\\n                \"reason\": \"expected state observed\",\\n                \"final_state\": current, \"observations\": observations,\\n            }\\n        if current[\"state\"] in terminal_states:\\n            return {\\n                \"reached\": False, \"timed_out\": False,\\n                \"reason\": phase + \": unexpected terminal process state\",\\n                \"final_state\": current, \"observations\": observations,\\n            }\\n\\nattached_process = None\\nconfirmed_attached = False\\ntry:\\n    selection = run_lldb_command(report[\"selection_command\"])\\n    report[\"selection\"] = selection\\n    selection_status = selection[\"return_status\"]\\n    # eReturnStatusStarted means only that selection was initiated. Any hard\\n    # failure/quit/continuing status stops before the independent verification.\\n    if selection_status not in finished_statuses and selection_status != started_status:\\n        raise RuntimeError(\\n            \"device selection returned a non-success, non-started status: \"\\n            + selection[\"return_status_name\"]\\n        )\\n\\n    listing = run_lldb_command(report[\"process_list_command\"])\\n    report[\"device_process_list\"] = {\\n        key: value for key, value in listing.items() if key != \"output\"\\n    }\\n    listed_processes = []\\n    for line in listing[\"output\"].splitlines():\\n        fields = line.split()\\n        if fields and fields[0].isdigit():\\n            listed_processes.append({\\n                \"pid\": int(fields[0]),\\n                \"name\": fields[-1] if len(fields) > 1 else \"\",\\n                \"line\": line.strip(),\\n            })\\n    matches = [\\n        item for item in listed_processes\\n        if item[\"pid\"] == EXPECTED_PID and item[\"line\"].endswith(EXECUTABLE_NAME)\\n    ]\\n    report[\"selected_device_verified\"] = (\\n        listing[\"return_status\"] in finished_statuses\\n        and listing[\"succeeded\"]\\n        and len(matches) == 1\\n    )\\n    report[\"ll_db_pid_match\"] = matches[0] if matches else None\\n    if not report[\"selected_device_verified\"]:\\n        raise RuntimeError(\\n            \"LLDB device process list did not independently confirm \"\\n            \"the current MH Unite PID\"\\n        )\\n\\n    report[\"attach_attempted\"] = True\\n    attach = run_lldb_command(report[\"attach_command\"])\\n    report[\"attach\"] = attach\\n    target = debugger.GetSelectedTarget()\\n    attached_process = target.GetProcess() if target and target.IsValid() else None\\n    attach_state = process_state(attached_process)\\n    report[\"attached_process_candidate\"] = (\\n        attach_state[\"valid\"] and attach_state[\"pid\"] == EXPECTED_PID\\n    )\\n    report[\"attached_process_state\"] = attach_state\\n    if not report[\"attached_process_candidate\"]:\\n        report[\"attachment_outcome\"] = \"no matching attached-process handle\"\\n        raise RuntimeError(\"attach did not produce a process handle for the expected PID\")\\n\\n    attach_listener, attach_broadcaster, attach_event_mask = create_state_listener(\\n        attached_process, \"mhfu-readonly-attach-state\"\\n    )\\n    try:\\n        attach_wait = observe_until_state(\\n            attached_process,\\n            lldb.eStateStopped,\\n            ATTACH_STATE_TIMEOUT_SECONDS,\\n            attach_listener,\\n            attach_broadcaster,\\n            attach_event_mask,\\n            \"attach\",\\n        )\\n    finally:\\n        remove_state_listener(\\n            attach_listener, attach_broadcaster, attach_event_mask\\n        )\\n    report[\"attach_state_wait\"] = attach_wait\\n    report[\"attach_state_transitions\"] = attach_wait[\"observations\"]\\n    if not attach_wait[\"reached\"]:\\n        report[\"attachment_outcome\"] = \"incomplete; eStateStopped not reached\"\\n        report[\"attachment_state_at_stop\"] = attach_wait[\"final_state\"]\\n        report[\"explicit_detach_attempted\"] = False\\n        # An incomplete or timed-out attach is intentionally left alone:\\n        # do not issue `process detach` until LLDB confirms eStateStopped.\\n        raise RuntimeError(attach_wait[\"reason\"])\\n\\n    confirmed_attached = True\\n    report[\"confirmed_attached\"] = True\\n    report[\"attachment_outcome\"] = \"confirmed stopped\"\\n    if attach[\"return_status\"] not in finished_statuses | {started_status}:\\n        report[\"attachment_outcome\"] = (\\n            \"stopped state confirmed, but attach command status was unexpected\"\\n        )\\n        raise RuntimeError(\\n            \"attach reached eStateStopped, but command status was unexpected: \"\\n            + attach[\"return_status_name\"]\\n        )\\n\\n    executable = None\\n    for module in target.module_iter():\\n        spec = module.GetFileSpec()\\n        if spec and spec.GetFilename() == EXECUTABLE_NAME:\\n            executable = module\\n            break\\n    if executable is None:\\n        raise RuntimeError(\"loaded MH Unite executable was not found\")\\n\\n    uuid = (executable.GetUUIDString() or \"\").replace(\"-\", \"\").lower()\\n    report[\"executable_uuid\"] = uuid\\n    if uuid != EXPECTED_UUID:\\n        raise RuntimeError(\"executable UUID mismatch; refusing memory reads\")\\n\\n    header = executable.GetObjectFileHeaderAddress()\\n    header_file = header.GetFileAddress()\\n    header_load = header.GetLoadAddress(target)\\n    if (header_file == lldb.LLDB_INVALID_ADDRESS\\n            or header_load == lldb.LLDB_INVALID_ADDRESS):\\n        raise RuntimeError(\"could not resolve the loaded executable header\")\\n    slide = header_load - header_file\\n    report[\"aslr_slide\"] = hex(slide)\\n    report[\"image_header_file\"] = hex(header_file)\\n    report[\"image_header_load\"] = hex(header_load)\\n\\n    # Prefer an exact exported symbol when available. The existing research\\n    # identifies this UUID-verified unslid slot as the fallback global.\\n    symbol_addresses = []\\n    try:\\n        contexts = target.FindSymbols(\\n            \"Singleton<Cockpit>::objectPtr\", lldb.eSymbolTypeAny\\n        )\\n        for index in range(contexts.GetSize()):\\n            symbol = contexts.GetContextAtIndex(index).GetSymbol()\\n            if symbol.IsValid() and symbol.GetName() == \"Singleton<Cockpit>::objectPtr\":\\n                symbol_address = symbol.GetStartAddress()\\n                symbol_load = symbol_address.GetLoadAddress(target)\\n                if symbol_load != lldb.LLDB_INVALID_ADDRESS:\\n                    symbol_addresses.append((symbol_load, symbol_address.GetFileAddress()))\\n    except Exception as symbol_error:\\n        report[\"symbol_lookup_note\"] = str(symbol_error)\\n\\n    if len(symbol_addresses) > 1:\\n        raise RuntimeError(\"multiple exact Singleton<Cockpit>::objectPtr symbols found\")\\n    if symbol_addresses:\\n        object_ptr_load, object_ptr_file = symbol_addresses[0]\\n        report[\"object_ptr_resolution\"] = \"exact named symbol\"\\n    else:\\n        object_file_address = executable.ResolveFileAddress(OBJECT_PTR_UNSLID)\\n        if not object_file_address.IsValid():\\n            raise RuntimeError(\"research-documented objectPtr slot did not resolve\")\\n        object_ptr_file = object_file_address.GetFileAddress()\\n        object_ptr_load = object_file_address.GetLoadAddress(target)\\n        report[\"object_ptr_resolution\"] = \"UUID-validated research address fallback\"\\n\\n    if (object_ptr_load == lldb.LLDB_INVALID_ADDRESS\\n            or object_ptr_load - object_ptr_file != slide):\\n        raise RuntimeError(\"objectPtr address does not agree with the executable ASLR slide\")\\n    report[\"object_ptr_unslid\"] = hex(object_ptr_file)\\n    report[\"object_ptr_runtime\"] = hex(object_ptr_load)\\n\\n    def read_unsigned(address, size, label):\\n        error = lldb.SBError()\\n        value = attached_process.ReadUnsignedFromMemory(address, size, error)\\n        if not error.Success():\\n            raise RuntimeError(\\n                \"read failed for %s at 0x%x: %s\"\\n                % (label, address, error.GetCString())\\n            )\\n        return value\\n\\n    cockpit = read_unsigned(object_ptr_load, 8, \"Singleton<Cockpit>::objectPtr\")\\n    if cockpit == 0:\\n        raise RuntimeError(\"Singleton<Cockpit>::objectPtr is null\")\\n    report[\"cockpit_pointer\"] = hex(cockpit)\\n    report[\"menu_state_11B0_u8\"] = hex(\\n        read_unsigned(cockpit + 0x11B0, 1, \"Cockpit+0x11B0\")\\n    )\\n    report[\"menu_selector_11B4_u32\"] = hex(\\n        read_unsigned(cockpit + 0x11B4, 4, \"Cockpit+0x11B4\")\\n    )\\n    report[\"inspection\"] = \"success\"\\nexcept Exception as error:\\n    report[\"inspection\"] = \"failed\"\\n    report[\"failure\"] = str(error)\\nfinally:\\n    if report[\"attach_attempted\"] and not confirmed_attached:\\n        report[\"explicit_detach_attempted\"] = False\\n        state_at_stop = process_state(attached_process)\\n        report[\"attachment_state_at_stop\"] = state_at_stop\\n        wait_timed_out = report.get(\"attach_state_wait\", {}).get(\"timed_out\") is True\\n        if (not wait_timed_out and state_at_stop[\"valid\"]\\n                and state_at_stop[\"pid\"] == EXPECTED_PID\\n                and state_at_stop[\"state\"] == lldb.eStateStopped):\\n            # A process-API snapshot independently confirms a completed attach\\n            # despite an event/listener error. It is then safe to detach, but\\n            # inspection is not resumed after the unexpected error.\\n            confirmed_attached = True\\n            report[\"confirmed_attached\"] = True\\n            report[\"attachment_outcome\"] = (\\n                \"stopped state confirmed by process snapshot after an error; \"\\n                \"inspection aborted\"\\n            )\\n        else:\\n            report[\"attachment_outcome\"] = (\\n                \"incomplete or unresolved; no stopped state confirmed\"\\n            )\\n            report[\"cleanup_note\"] = (\\n                \"No explicit detach was issued because eStateStopped was not \"\\n                \"confirmed, or the bounded attach wait timed out.\"\\n            )\\n    if confirmed_attached:\\n        try:\\n            before_detach = process_state(attached_process)\\n            report[\"state_before_detach\"] = before_detach\\n            if (not before_detach[\"valid\"]\\n                    or before_detach[\"pid\"] != EXPECTED_PID\\n                    or before_detach[\"state\"] not in\\n                    (lldb.eStateStopped, lldb.eStateRunning)):\\n                report[\"detached_verified\"] = False\\n                report[\"detach_skipped_reason\"] = (\\n                    \"LLDB no longer reports the expected process in a safe \"\\n                    \"attached state\"\\n                )\\n                report[\"attachment_outcome\"] = (\\n                    \"stopped state had been confirmed, but detach was skipped \"\\n                    \"after the process state changed\"\\n                )\\n            else:\\n                detach_listener, detach_broadcaster, detach_event_mask = (\\n                    create_state_listener(\\n                        attached_process, \"mhfu-readonly-detach-state\"\\n                    )\\n                )\\n                try:\\n                    report[\"detach_attempted\"] = True\\n                    report[\"explicit_detach_attempted\"] = True\\n                    detach = run_lldb_command(\"process detach\")\\n                    report[\"detach\"] = detach\\n                    detach_wait = observe_until_state(\\n                        attached_process,\\n                        lldb.eStateDetached,\\n                        DETACH_STATE_TIMEOUT_SECONDS,\\n                        detach_listener,\\n                        detach_broadcaster,\\n                        detach_event_mask,\\n                        \"detach\",\\n                    )\\n                    report[\"detach_state_wait\"] = detach_wait\\n                    report[\"detach_state_transitions\"] = detach_wait[\"observations\"]\\n                    report[\"detached_process_state\"] = detach_wait[\"final_state\"]\\n                    report[\"detached_state_confirmed\"] = detach_wait[\"reached\"]\\n                    report[\"detached_verified\"] = (\\n                        detach[\"return_status\"] in finished_statuses | {started_status}\\n                        and detach_wait[\"reached\"]\\n                    )\\n                    if report[\"detached_verified\"]:\\n                        report[\"attachment_outcome\"] = \"detached and verified\"\\n                    elif detach_wait[\"reached\"]:\\n                        report[\"attachment_outcome\"] = (\\n                            \"eStateDetached observed, but detach command status \"\\n                            \"was unexpected\"\\n                        )\\n                    else:\\n                        report[\"attachment_outcome\"] = (\\n                            \"detach issued but eStateDetached was not verified\"\\n                        )\\n                finally:\\n                    remove_state_listener(\\n                        detach_listener, detach_broadcaster, detach_event_mask\\n                    )\\n        except Exception as detach_error:\\n            report[\"detached_verified\"] = False\\n            report[\"detach_exception\"] = str(detach_error)\\n            report[\"attachment_outcome\"] = (\\n                \"detach behavior unexpected; state may be unresolved\"\\n            )\\n            try:\\n                report[\"detached_process_state\"] = process_state(attached_process)\\n            except Exception as state_error:\\n                report[\"detached_process_state_error\"] = str(state_error)\\nprint(\\'MHFU_READONLY_PROBE_RESULT=\\' + json.dumps(report, sort_keys=True))\\n')\n",
  "safety": {
    "breakpoints": false,
    "game_launch": false,
    "memory_writes": false,
    "register_writes": false,
    "watchpoints": false
  },
  "state_observations": [],
  "status": "stopped: LLDB result marker missing; target attachment state unknown",
  "timestamp_utc": "2026-11-24T03:11:11.621795+00:00"
}
```

## Automated read-only LLDB retry — 2026-11-24T03:13:40.786280+00:00

```json
{
  "attachment_outcome": "unknown: LLDB ended without a final lifecycle result",
  "automatic_retry": false,
  "cleanup_note": "No retry or follow-up attach/detach command was issued.",
  "current_pid": 29949,
  "device_id": "EB90DDE0-50FB-5593-A792-E211E636A9EC",
  "devicectl_list_exit_code": 0,
  "devicectl_process_line": "29949   /private/var/containers/Bundle/Application/1A491814-FC3E-4E16-A688-C5896AD06220/MH Unite.app/MH Unite",
  "devicectl_process_list_exit_code": 0,
  "devicectl_target_listed": true,
  "failure": "stopped: LLDB result marker missing; target attachment state unknown",
  "game_bundle_id": "jp.co.capcom.mhp2g",
  "lldb_exit_code": 1,
  "lldb_result": null,
  "lldb_stderr": "error: <user expression 0>:1:1: unknown type name 'process'\n    1 | process detach\n      | ^\n",
  "lldb_stdout": "(lldb) script exec('import json\\nimport lldb\\nimport math\\nimport time\\n\\nDEVICE_ID = \\'EB90DDE0-50FB-5593-A792-E211E636A9EC\\'\\nEXPECTED_PID = 29949\\nEXPECTED_UUID = \\'58cc55c760ca3196b5d20c2aeb64b32b\\'\\nEXECUTABLE_NAME = \\'MH Unite\\'\\nOBJECT_PTR_UNSLID = 4302516160\\nATTACH_STATE_TIMEOUT_SECONDS = 30\\nDETACH_STATE_TIMEOUT_SECONDS = 20\\ndebugger = lldb.debugger\\ninterpreter = debugger.GetCommandInterpreter()\\nreport = {\\n    \"device_id\": DEVICE_ID,\\n    \"preflight_pid\": EXPECTED_PID,\\n    \"selection_command\": \"device select \" + DEVICE_ID,\\n    \"process_list_command\": \"device process list\",\\n    \"attach_command\": \"device process attach --pid \" + str(EXPECTED_PID),\\n    \"attached_process_candidate\": False,\\n    \"attach_attempted\": False,\\n    \"detach_attempted\": False,\\n    \"explicit_detach_attempted\": False,\\n    \"confirmed_attached\": False,\\n    \"attachment_outcome\": \"not attempted\",\\n    \"attach_state_transitions\": [],\\n    \"detach_state_transitions\": [],\\n}\\n\\nstatus_names = {\\n    getattr(lldb, name): name\\n    for name in dir(lldb)\\n    if name.startswith(\"eReturnStatus\")\\n}\\nstate_names = {\\n    getattr(lldb, name): name\\n    for name in dir(lldb)\\n    if name.startswith(\"eState\")\\n}\\nfinished_statuses = {\\n    lldb.eReturnStatusSuccessFinishNoResult,\\n    lldb.eReturnStatusSuccessFinishResult,\\n}\\nstarted_status = lldb.eReturnStatusStarted\\n\\ndef run_lldb_command(command):\\n    result = lldb.SBCommandReturnObject()\\n    status = interpreter.HandleCommand(command, result)\\n    status_value = int(status)\\n    result_status_value = int(result.GetStatus())\\n    return {\\n        \"command\": command,\\n        \"return_status\": status_value,\\n        \"return_status_name\": status_names.get(status_value, \"unknown\"),\\n        \"result_status\": result_status_value,\\n        \"result_status_name\": status_names.get(result_status_value, \"unknown\"),\\n        \"succeeded\": bool(result.Succeeded()),\\n        \"output\": result.GetOutput() or \"\",\\n        \"error\": result.GetError() or \"\",\\n    }\\n\\ndef process_state(process):\\n    if not process or not process.IsValid():\\n        return {\"valid\": False, \"pid\": None, \"state\": None, \"state_name\": \"invalid\"}\\n    state = int(process.GetState())\\n    return {\\n        \"valid\": True,\\n        \"pid\": int(process.GetProcessID()),\\n        \"state\": state,\\n        \"state_name\": state_names.get(state, \"unknown\"),\\n    }\\n\\ndef create_state_listener(process, name):\\n    listener = lldb.SBListener(name)\\n    broadcaster = process.GetBroadcaster()\\n    event_mask = lldb.SBProcess.eBroadcastBitStateChanged\\n    registered_mask = int(broadcaster.AddListener(listener, event_mask))\\n    if registered_mask & int(event_mask) == 0:\\n        raise RuntimeError(\"LLDB process-state listener registration failed\")\\n    return listener, broadcaster, event_mask\\n\\ndef remove_state_listener(listener, broadcaster, event_mask):\\n    try:\\n        broadcaster.RemoveListener(listener, event_mask)\\n    except Exception:\\n        pass\\n\\ndef observe_until_state(process, expected_state, timeout_seconds,\\n                        listener, broadcaster, event_mask, phase):\\n    observations = []\\n\\n    def record(source, state):\\n        state_value = int(state)\\n        observation = {\\n            \"source\": source,\\n            \"phase\": phase,\\n            \"pid\": int(process.GetProcessID()) if process.IsValid() else None,\\n            \"state\": state_value,\\n            \"state_name\": state_names.get(state_value, \"unknown\"),\\n        }\\n        observations.append(observation)\\n        print(\"MHFU_STATE_OBSERVATION=\" + json.dumps(observation, sort_keys=True),\\n              flush=True)\\n\\n    initial = process_state(process)\\n    if initial[\"state\"] is not None:\\n        record(\"initial snapshot\", initial[\"state\"])\\n    if not initial[\"valid\"] and expected_state != lldb.eStateDetached:\\n        return {\\n            \"reached\": False, \"timed_out\": False,\\n            \"reason\": phase + \": process handle became invalid\",\\n            \"final_state\": initial, \"observations\": observations,\\n        }\\n    if initial[\"valid\"] and initial[\"pid\"] != EXPECTED_PID:\\n        return {\\n            \"reached\": False, \"timed_out\": False,\\n            \"reason\": phase + \": process handle PID changed unexpectedly\",\\n            \"final_state\": initial, \"observations\": observations,\\n        }\\n    if initial[\"valid\"] and initial[\"state\"] == expected_state:\\n        return {\\n            \"reached\": True, \"timed_out\": False,\\n            \"reason\": \"expected state already observed\",\\n            \"final_state\": initial, \"observations\": observations,\\n        }\\n\\n    deadline = time.monotonic() + timeout_seconds\\n    terminal_states = {\\n        lldb.eStateInvalid, lldb.eStateUnloaded,\\n        lldb.eStateExited, lldb.eStateCrashed,\\n        lldb.eStateDetached,\\n    }\\n    while True:\\n        remaining = deadline - time.monotonic()\\n        if remaining <= 0:\\n            final = process_state(process)\\n            if final[\"state\"] is not None:\\n                record(\"timeout snapshot\", final[\"state\"])\\n            if final[\"valid\"] and final[\"pid\"] == EXPECTED_PID and final[\"state\"] == expected_state:\\n                return {\\n                    \"reached\": True, \"timed_out\": False,\\n                    \"reason\": \"expected state confirmed by final process snapshot\",\\n                    \"final_state\": final, \"observations\": observations,\\n                }\\n            return {\\n                \"reached\": False, \"timed_out\": True,\\n                \"reason\": phase + \": state wait timed out\",\\n                \"final_state\": final, \"observations\": observations,\\n            }\\n\\n        event = lldb.SBEvent()\\n        try:\\n            received = listener.WaitForEventForBroadcasterWithType(\\n                max(1, int(math.ceil(remaining))),\\n                broadcaster,\\n                event_mask,\\n                event,\\n            )\\n        except Exception as wait_error:\\n            final = process_state(process)\\n            if final[\"state\"] is not None:\\n                record(\"listener-error snapshot\", final[\"state\"])\\n            return {\\n                \"reached\": False, \"timed_out\": False,\\n                \"reason\": phase + \": listener wait failed: \" + str(wait_error),\\n                \"final_state\": final, \"observations\": observations,\\n            }\\n\\n        event_state = None\\n        event_pid = None\\n        if received:\\n            event_state = int(lldb.SBProcess.GetStateFromEvent(event))\\n            record(\"state-change event\", event_state)\\n            event_process = lldb.SBProcess.GetProcessFromEvent(event)\\n            if event_process and event_process.IsValid():\\n                event_pid = int(event_process.GetProcessID())\\n            observations[-1][\"event_pid\"] = event_pid\\n            observations[-1][\"is_process_event\"] = bool(\\n                lldb.SBProcess.EventIsProcessEvent(event)\\n            )\\n            if (not observations[-1][\"is_process_event\"]\\n                    or (event_pid is not None and event_pid != EXPECTED_PID)):\\n                return {\\n                    \"reached\": False, \"timed_out\": False,\\n                    \"reason\": phase + \": received event for an unexpected process\",\\n                    \"final_state\": process_state(process),\\n                    \"observations\": observations,\\n                }\\n\\n        current = process_state(process)\\n        if current[\"state\"] is not None:\\n            record(\"current process snapshot\", current[\"state\"])\\n        if not current[\"valid\"]:\\n            if (expected_state == lldb.eStateDetached\\n                    and received\\n                    and event_state == lldb.eStateDetached\\n                    and (event_pid is None or event_pid == EXPECTED_PID)):\\n                return {\\n                    \"reached\": True, \"timed_out\": False,\\n                    \"reason\": \"eStateDetached confirmed by target process event\",\\n                    \"final_state\": {\\n                        \"valid\": False,\\n                        \"pid\": event_pid or EXPECTED_PID,\\n                        \"state\": lldb.eStateDetached,\\n                        \"state_name\": state_names.get(\\n                            lldb.eStateDetached, \"eStateDetached\"\\n                        ),\\n                        \"confirmed_by\": \"process broadcaster event\",\\n                    },\\n                    \"observations\": observations,\\n                }\\n            if expected_state == lldb.eStateDetached:\\n                if received and event_state in terminal_states:\\n                    return {\\n                        \"reached\": False, \"timed_out\": False,\\n                        \"reason\": phase + \": unexpected terminal process event\",\\n                        \"final_state\": {\\n                            \"valid\": False,\\n                            \"pid\": event_pid or EXPECTED_PID,\\n                            \"state\": event_state,\\n                            \"state_name\": state_names.get(event_state, \"unknown\"),\\n                        },\\n                        \"observations\": observations,\\n                    }\\n                # The SBProcess may become invalid as detach completes before\\n                # its queued eStateDetached event is read. Wait boundedly for\\n                # that target-process event instead of assuming success.\\n                continue\\n            return {\\n                \"reached\": False, \"timed_out\": False,\\n                \"reason\": phase + \": process handle became invalid\",\\n                \"final_state\": current, \"observations\": observations,\\n            }\\n        if current[\"pid\"] != EXPECTED_PID:\\n            return {\\n                \"reached\": False, \"timed_out\": False,\\n                \"reason\": phase + \": process handle PID changed unexpectedly\",\\n                \"final_state\": current, \"observations\": observations,\\n            }\\n        if current[\"state\"] == expected_state:\\n            return {\\n                \"reached\": True, \"timed_out\": False,\\n                \"reason\": \"expected state observed\",\\n                \"final_state\": current, \"observations\": observations,\\n            }\\n        if current[\"state\"] in terminal_states:\\n            return {\\n                \"reached\": False, \"timed_out\": False,\\n                \"reason\": phase + \": unexpected terminal process state\",\\n                \"final_state\": current, \"observations\": observations,\\n            }\\n\\nattached_process = None\\nconfirmed_attached = False\\ntry:\\n    selection = run_lldb_command(report[\"selection_command\"])\\n    report[\"selection\"] = selection\\n    selection_status = selection[\"return_status\"]\\n    # eReturnStatusStarted means only that selection was initiated. Any hard\\n    # failure/quit/continuing status stops before the independent verification.\\n    if selection_status not in finished_statuses and selection_status != started_status:\\n        raise RuntimeError(\\n            \"device selection returned a non-success, non-started status: \"\\n            + selection[\"return_status_name\"]\\n        )\\n\\n    listing = run_lldb_command(report[\"process_list_command\"])\\n    report[\"device_process_list\"] = {\\n        key: value for key, value in listing.items() if key != \"output\"\\n    }\\n    listed_processes = []\\n    for line in listing[\"output\"].splitlines():\\n        fields = line.split()\\n        if fields and fields[0].isdigit():\\n            listed_processes.append({\\n                \"pid\": int(fields[0]),\\n                \"name\": fields[-1] if len(fields) > 1 else \"\",\\n                \"line\": line.strip(),\\n            })\\n    matches = [\\n        item for item in listed_processes\\n        if item[\"pid\"] == EXPECTED_PID and item[\"line\"].endswith(EXECUTABLE_NAME)\\n    ]\\n    report[\"selected_device_verified\"] = (\\n        listing[\"return_status\"] in finished_statuses\\n        and listing[\"succeeded\"]\\n        and len(matches) == 1\\n    )\\n    report[\"ll_db_pid_match\"] = matches[0] if matches else None\\n    if not report[\"selected_device_verified\"]:\\n        raise RuntimeError(\\n            \"LLDB device process list did not independently confirm \"\\n            \"the current MH Unite PID\"\\n        )\\n\\n    report[\"attach_attempted\"] = True\\n    attach = run_lldb_command(report[\"attach_command\"])\\n    report[\"attach\"] = attach\\n    target = debugger.GetSelectedTarget()\\n    attached_process = target.GetProcess() if target and target.IsValid() else None\\n    attach_state = process_state(attached_process)\\n    report[\"attached_process_candidate\"] = (\\n        attach_state[\"valid\"] and attach_state[\"pid\"] == EXPECTED_PID\\n    )\\n    report[\"attached_process_state\"] = attach_state\\n    if not report[\"attached_process_candidate\"]:\\n        report[\"attachment_outcome\"] = \"no matching attached-process handle\"\\n        raise RuntimeError(\"attach did not produce a process handle for the expected PID\")\\n\\n    attach_listener, attach_broadcaster, attach_event_mask = create_state_listener(\\n        attached_process, \"mhfu-readonly-attach-state\"\\n    )\\n    try:\\n        attach_wait = observe_until_state(\\n            attached_process,\\n            lldb.eStateStopped,\\n            ATTACH_STATE_TIMEOUT_SECONDS,\\n            attach_listener,\\n            attach_broadcaster,\\n            attach_event_mask,\\n            \"attach\",\\n        )\\n    finally:\\n        remove_state_listener(\\n            attach_listener, attach_broadcaster, attach_event_mask\\n        )\\n    report[\"attach_state_wait\"] = attach_wait\\n    report[\"attach_state_transitions\"] = attach_wait[\"observations\"]\\n    if not attach_wait[\"reached\"]:\\n        report[\"attachment_outcome\"] = \"incomplete; eStateStopped not reached\"\\n        report[\"attachment_state_at_stop\"] = attach_wait[\"final_state\"]\\n        report[\"explicit_detach_attempted\"] = False\\n        # An incomplete or timed-out attach is intentionally left alone:\\n        # do not issue `process detach` until LLDB confirms eStateStopped.\\n        raise RuntimeError(attach_wait[\"reason\"])\\n\\n    confirmed_attached = True\\n    report[\"confirmed_attached\"] = True\\n    report[\"attachment_outcome\"] = \"confirmed stopped\"\\n    if attach[\"return_status\"] not in finished_statuses | {started_status}:\\n        report[\"attachment_outcome\"] = (\\n            \"stopped state confirmed, but attach command status was unexpected\"\\n        )\\n        raise RuntimeError(\\n            \"attach reached eStateStopped, but command status was unexpected: \"\\n            + attach[\"return_status_name\"]\\n        )\\n\\n    executable = None\\n    for module in target.module_iter():\\n        spec = module.GetFileSpec()\\n        if spec and spec.GetFilename() == EXECUTABLE_NAME:\\n            executable = module\\n            break\\n    if executable is None:\\n        raise RuntimeError(\"loaded MH Unite executable was not found\")\\n\\n    uuid = (executable.GetUUIDString() or \"\").replace(\"-\", \"\").lower()\\n    report[\"executable_uuid\"] = uuid\\n    if uuid != EXPECTED_UUID:\\n        raise RuntimeError(\"executable UUID mismatch; refusing memory reads\")\\n\\n    header = executable.GetObjectFileHeaderAddress()\\n    header_file = header.GetFileAddress()\\n    header_load = header.GetLoadAddress(target)\\n    if (header_file == lldb.LLDB_INVALID_ADDRESS\\n            or header_load == lldb.LLDB_INVALID_ADDRESS):\\n        raise RuntimeError(\"could not resolve the loaded executable header\")\\n    slide = header_load - header_file\\n    report[\"aslr_slide\"] = hex(slide)\\n    report[\"image_header_file\"] = hex(header_file)\\n    report[\"image_header_load\"] = hex(header_load)\\n\\n    # Prefer an exact exported symbol when available. The existing research\\n    # identifies this UUID-verified unslid slot as the fallback global.\\n    symbol_addresses = []\\n    try:\\n        contexts = target.FindSymbols(\\n            \"Singleton<Cockpit>::objectPtr\", lldb.eSymbolTypeAny\\n        )\\n        for index in range(contexts.GetSize()):\\n            symbol = contexts.GetContextAtIndex(index).GetSymbol()\\n            if symbol.IsValid() and symbol.GetName() == \"Singleton<Cockpit>::objectPtr\":\\n                symbol_address = symbol.GetStartAddress()\\n                symbol_load = symbol_address.GetLoadAddress(target)\\n                if symbol_load != lldb.LLDB_INVALID_ADDRESS:\\n                    symbol_addresses.append((symbol_load, symbol_address.GetFileAddress()))\\n    except Exception as symbol_error:\\n        report[\"symbol_lookup_note\"] = str(symbol_error)\\n\\n    if len(symbol_addresses) > 1:\\n        raise RuntimeError(\"multiple exact Singleton<Cockpit>::objectPtr symbols found\")\\n    if symbol_addresses:\\n        object_ptr_load, object_ptr_file = symbol_addresses[0]\\n        report[\"object_ptr_resolution\"] = \"exact named symbol\"\\n    else:\\n        object_file_address = executable.ResolveFileAddress(OBJECT_PTR_UNSLID)\\n        if not object_file_address.IsValid():\\n            raise RuntimeError(\"research-documented objectPtr slot did not resolve\")\\n        object_ptr_file = object_file_address.GetFileAddress()\\n        object_ptr_load = object_file_address.GetLoadAddress(target)\\n        report[\"object_ptr_resolution\"] = \"UUID-validated research address fallback\"\\n\\n    if (object_ptr_load == lldb.LLDB_INVALID_ADDRESS\\n            or object_ptr_load - object_ptr_file != slide):\\n        raise RuntimeError(\"objectPtr address does not agree with the executable ASLR slide\")\\n    report[\"object_ptr_unslid\"] = hex(object_ptr_file)\\n    report[\"object_ptr_runtime\"] = hex(object_ptr_load)\\n\\n    def read_unsigned(address, size, label):\\n        error = lldb.SBError()\\n        value = attached_process.ReadUnsignedFromMemory(address, size, error)\\n        if not error.Success():\\n            raise RuntimeError(\\n                \"read failed for %s at 0x%x: %s\"\\n                % (label, address, error.GetCString())\\n            )\\n        return value\\n\\n    cockpit = read_unsigned(object_ptr_load, 8, \"Singleton<Cockpit>::objectPtr\")\\n    if cockpit == 0:\\n        raise RuntimeError(\"Singleton<Cockpit>::objectPtr is null\")\\n    report[\"cockpit_pointer\"] = hex(cockpit)\\n    report[\"menu_state_11B0_u8\"] = hex(\\n        read_unsigned(cockpit + 0x11B0, 1, \"Cockpit+0x11B0\")\\n    )\\n    report[\"menu_selector_11B4_u32\"] = hex(\\n        read_unsigned(cockpit + 0x11B4, 4, \"Cockpit+0x11B4\")\\n    )\\n    report[\"inspection\"] = \"success\"\\nexcept Exception as error:\\n    report[\"inspection\"] = \"failed\"\\n    report[\"failure\"] = str(error)\\nfinally:\\n    if report[\"attach_attempted\"] and not confirmed_attached:\\n        report[\"explicit_detach_attempted\"] = False\\n        state_at_stop = process_state(attached_process)\\n        report[\"attachment_state_at_stop\"] = state_at_stop\\n        wait_timed_out = report.get(\"attach_state_wait\", {}).get(\"timed_out\") is True\\n        if (not wait_timed_out and state_at_stop[\"valid\"]\\n                and state_at_stop[\"pid\"] == EXPECTED_PID\\n                and state_at_stop[\"state\"] == lldb.eStateStopped):\\n            # A process-API snapshot independently confirms a completed attach\\n            # despite an event/listener error. It is then safe to detach, but\\n            # inspection is not resumed after the unexpected error.\\n            confirmed_attached = True\\n            report[\"confirmed_attached\"] = True\\n            report[\"attachment_outcome\"] = (\\n                \"stopped state confirmed by process snapshot after an error; \"\\n                \"inspection aborted\"\\n            )\\n        else:\\n            report[\"attachment_outcome\"] = (\\n                \"incomplete or unresolved; no stopped state confirmed\"\\n            )\\n            report[\"cleanup_note\"] = (\\n                \"No explicit detach was issued because eStateStopped was not \"\\n                \"confirmed, or the bounded attach wait timed out.\"\\n            )\\n    if confirmed_attached:\\n        try:\\n            before_detach = process_state(attached_process)\\n            report[\"state_before_detach\"] = before_detach\\n            if (not before_detach[\"valid\"]\\n                    or before_detach[\"pid\"] != EXPECTED_PID\\n                    or before_detach[\"state\"] not in\\n                    (lldb.eStateStopped, lldb.eStateRunning)):\\n                report[\"detached_verified\"] = False\\n                report[\"detach_skipped_reason\"] = (\\n                    \"LLDB no longer reports the expected process in a safe \"\\n                    \"attached state\"\\n                )\\n                report[\"attachment_outcome\"] = (\\n                    \"stopped state had been confirmed, but detach was skipped \"\\n                    \"after the process state changed\"\\n                )\\n            else:\\n                detach_listener, detach_broadcaster, detach_event_mask = (\\n                    create_state_listener(\\n                        attached_process, \"mhfu-readonly-detach-state\"\\n                    )\\n                )\\n                try:\\n                    report[\"detach_attempted\"] = True\\n                    report[\"explicit_detach_attempted\"] = True\\n                    # Use the SBProcess API directly. Routing the CLI command\\n                    # `process detach` through HandleCommand from inside the\\n                    # `script exec` callback was parsed as an expression in\\n                    # the prior attempt and failed with \"unknown type name\".\\n                    detach_error = attached_process.Detach()\\n                    report[\"detach\"] = {\\n                        \"api\": \"SBProcess.Detach\",\\n                        \"succeeded\": bool(detach_error.Success()),\\n                        \"error\": detach_error.GetCString() or \"\",\\n                    }\\n                    detach_wait = observe_until_state(\\n                        attached_process,\\n                        lldb.eStateDetached,\\n                        DETACH_STATE_TIMEOUT_SECONDS,\\n                        detach_listener,\\n                        detach_broadcaster,\\n                        detach_event_mask,\\n                        \"detach\",\\n                    )\\n                    report[\"detach_state_wait\"] = detach_wait\\n                    report[\"detach_state_transitions\"] = detach_wait[\"observations\"]\\n                    report[\"detached_process_state\"] = detach_wait[\"final_state\"]\\n                    report[\"detached_state_confirmed\"] = detach_wait[\"reached\"]\\n                    report[\"detached_verified\"] = (\\n                        detach_error.Success()\\n                        and detach_wait[\"reached\"]\\n                    )\\n                    if report[\"detached_verified\"]:\\n                        report[\"attachment_outcome\"] = \"detached and verified\"\\n                    elif detach_wait[\"reached\"]:\\n                        report[\"attachment_outcome\"] = (\\n                            \"eStateDetached observed, but SBProcess.Detach returned an error\"\\n                        )\\n                    else:\\n                        report[\"attachment_outcome\"] = (\\n                            \"detach issued but eStateDetached was not verified\"\\n                        )\\n                finally:\\n                    remove_state_listener(\\n                        detach_listener, detach_broadcaster, detach_event_mask\\n                    )\\n        except Exception as detach_error:\\n            report[\"detached_verified\"] = False\\n            report[\"detach_exception\"] = str(detach_error)\\n            report[\"attachment_outcome\"] = (\\n                \"detach behavior unexpected; state may be unresolved\"\\n            )\\n            try:\\n                report[\"detached_process_state\"] = process_state(attached_process)\\n            except Exception as state_error:\\n                report[\"detached_process_state_error\"] = str(state_error)\\nprint(\\'MHFU_READONLY_PROBE_RESULT=\\' + json.dumps(report, sort_keys=True))\\n')\n",
  "safety": {
    "breakpoints": false,
    "game_launch": false,
    "memory_writes": false,
    "register_writes": false,
    "watchpoints": false
  },
  "state_observations": [],
  "status": "stopped: LLDB result marker missing; target attachment state unknown",
  "timestamp_utc": "2026-11-24T03:13:38.959107+00:00"
}
```

## Automated read-only LLDB retry — 2026-11-24T03:27:02.579484+00:00

```json
{
  "current_pid": 29949,
  "device_id": "EB90DDE0-50FB-5593-A792-E211E636A9EC",
  "devicectl_list_exit_code": 0,
  "devicectl_process_line": "29949   /private/var/containers/Bundle/Application/1A491814-FC3E-4E16-A688-C5896AD06220/MH Unite.app/MH Unite",
  "devicectl_process_list_exit_code": 0,
  "devicectl_target_listed": true,
  "game_bundle_id": "jp.co.capcom.mhp2g",
  "game_process_present_after_detach": true,
  "lldb_diagnostics": [
    {
      "command": "device select EB90DDE0-50FB-5593-A792-E211E636A9EC",
      "event": "device_select_before",
      "monotonic_time": 0.262669282,
      "phase": "device selection"
    },
    {
      "error": "",
      "event": "device_select_after",
      "monotonic_time": 3.297132944,
      "output": "",
      "phase": "device selection",
      "return_status": 5,
      "return_status_name": "eReturnStatusStarted",
      "succeeded": false
    },
    {
      "command": "device process list",
      "event": "device_process_list_before",
      "monotonic_time": 3.297272597,
      "phase": "device process list verification"
    },
    {
      "error": "",
      "event": "device_process_list_after",
      "matching_pid": {
        "line": "29949  0                                                MH Unite",
        "name": "Unite",
        "pid": 29949
      },
      "monotonic_time": 3.43923733,
      "phase": "device process list verification",
      "return_status": 2,
      "return_status_name": "eReturnStatusSuccessFinishResult",
      "selected_device_verified": true,
      "succeeded": true
    },
    {
      "command": "device process attach --pid 29949",
      "event": "attach_before",
      "monotonic_time": 3.439308183,
      "phase": "device process attach",
      "selected_device_verified": true,
      "target_pid": 29949
    },
    {
      "error": "",
      "event": "attach_after",
      "monotonic_time": 3.486720282,
      "output": "",
      "phase": "device process attach",
      "return_status": 2,
      "return_status_name": "eReturnStatusSuccessFinishResult",
      "succeeded": true
    },
    {
      "event": "attach_state_wait_before",
      "monotonic_time": 3.487005414,
      "phase": "attach state wait",
      "process_state": {
        "pid": 29949,
        "state": 2,
        "state_name": "eStateConnected",
        "valid": true
      },
      "timeout_seconds": 30
    },
    {
      "event": "attach_state_wait_after",
      "final_state": {
        "pid": 29949,
        "state": 5,
        "state_name": "eStateStopped",
        "valid": true
      },
      "monotonic_time": 11.846896537,
      "phase": "attach state wait",
      "reached": true,
      "timed_out": false,
      "transitions": [
        {
          "phase": "attach",
          "pid": 29949,
          "source": "initial snapshot",
          "state": 2,
          "state_name": "eStateConnected"
        },
        {
          "event_pid": 29949,
          "is_process_event": true,
          "phase": "attach",
          "pid": 29949,
          "source": "state-change event",
          "state": 5,
          "state_name": "eStateStopped"
        },
        {
          "phase": "attach",
          "pid": 29949,
          "source": "current process snapshot",
          "state": 5,
          "state_name": "eStateStopped"
        }
      ]
    },
    {
      "event": "memory_inspection_before",
      "monotonic_time": 11.847188257,
      "phase": "read-only memory inspection",
      "pid": 29949,
      "process_state": {
        "pid": 29949,
        "state": 5,
        "state_name": "eStateStopped",
        "valid": true
      }
    },
    {
      "aslr_slide": "0x498c000",
      "cockpit_pointer": "0x10aa81500",
      "event": "memory_inspection_after",
      "executable_uuid": "58cc55c760ca3196b5d20c2aeb64b32b",
      "menu_selector_11B4_u32": "0x0",
      "menu_state_11B0_u8": "0x0",
      "monotonic_time": 11.865034462,
      "object_ptr_resolution": "exact named symbol",
      "object_ptr_runtime": "0x1050befc0",
      "phase": "read-only memory inspection"
    },
    {
      "event": "sbprocess_detach_before",
      "monotonic_time": 11.86531975,
      "phase": "SBProcess.Detach",
      "pid_matches_target": true,
      "process_handle_valid": true,
      "process_pid": 29949,
      "process_state": {
        "pid": 29949,
        "state": 5,
        "state_name": "eStateStopped",
        "valid": true
      }
    },
    {
      "event": "sbprocess_detach_after",
      "monotonic_time": 11.874181139,
      "phase": "SBProcess.Detach",
      "return_value_repr": "success",
      "sb_error_message": "",
      "sb_error_success": true
    },
    {
      "event": "detach_state_wait_before",
      "monotonic_time": 11.874274011,
      "phase": "detach state wait",
      "timeout_seconds": 20
    },
    {
      "event": "detach_state_wait_after",
      "final_state": {
        "pid": 29949,
        "state": 9,
        "state_name": "eStateDetached",
        "valid": true
      },
      "monotonic_time": 11.874348829,
      "phase": "detach state wait",
      "reached": true,
      "timed_out": false,
      "transitions": [
        {
          "phase": "detach",
          "pid": 29949,
          "source": "initial snapshot",
          "state": 9,
          "state_name": "eStateDetached"
        }
      ]
    }
  ],
  "lldb_exit_code": 0,
  "lldb_result": {
    "aslr_slide": "0x498c000",
    "attach": {
      "command": "device process attach --pid 29949",
      "error": "",
      "output": "",
      "result_status": 2,
      "result_status_name": "eReturnStatusSuccessFinishResult",
      "return_status": 2,
      "return_status_name": "eReturnStatusSuccessFinishResult",
      "succeeded": true
    },
    "attach_attempted": true,
    "attach_command": "device process attach --pid 29949",
    "attach_state_transitions": [
      {
        "phase": "attach",
        "pid": 29949,
        "source": "initial snapshot",
        "state": 2,
        "state_name": "eStateConnected"
      },
      {
        "event_pid": 29949,
        "is_process_event": true,
        "phase": "attach",
        "pid": 29949,
        "source": "state-change event",
        "state": 5,
        "state_name": "eStateStopped"
      },
      {
        "phase": "attach",
        "pid": 29949,
        "source": "current process snapshot",
        "state": 5,
        "state_name": "eStateStopped"
      }
    ],
    "attach_state_wait": {
      "final_state": {
        "pid": 29949,
        "state": 5,
        "state_name": "eStateStopped",
        "valid": true
      },
      "observations": [
        {
          "phase": "attach",
          "pid": 29949,
          "source": "initial snapshot",
          "state": 2,
          "state_name": "eStateConnected"
        },
        {
          "event_pid": 29949,
          "is_process_event": true,
          "phase": "attach",
          "pid": 29949,
          "source": "state-change event",
          "state": 5,
          "state_name": "eStateStopped"
        },
        {
          "phase": "attach",
          "pid": 29949,
          "source": "current process snapshot",
          "state": 5,
          "state_name": "eStateStopped"
        }
      ],
      "reached": true,
      "reason": "expected state observed",
      "timed_out": false
    },
    "attached_process_candidate": true,
    "attached_process_state": {
      "pid": 29949,
      "state": 2,
      "state_name": "eStateConnected",
      "valid": true
    },
    "attachment_outcome": "detached and verified",
    "cockpit_pointer": "0x10aa81500",
    "confirmed_attached": true,
    "detach": {
      "api": "SBProcess.Detach",
      "error": "",
      "return_value_repr": "success",
      "succeeded": true
    },
    "detach_attempted": true,
    "detach_state_transitions": [
      {
        "phase": "detach",
        "pid": 29949,
        "source": "initial snapshot",
        "state": 9,
        "state_name": "eStateDetached"
      }
    ],
    "detach_state_wait": {
      "final_state": {
        "pid": 29949,
        "state": 9,
        "state_name": "eStateDetached",
        "valid": true
      },
      "observations": [
        {
          "phase": "detach",
          "pid": 29949,
          "source": "initial snapshot",
          "state": 9,
          "state_name": "eStateDetached"
        }
      ],
      "reached": true,
      "reason": "expected state already observed",
      "timed_out": false
    },
    "detached_process_state": {
      "pid": 29949,
      "state": 9,
      "state_name": "eStateDetached",
      "valid": true
    },
    "detached_state_confirmed": true,
    "detached_verified": true,
    "device_id": "EB90DDE0-50FB-5593-A792-E211E636A9EC",
    "device_process_list": {
      "command": "device process list",
      "error": "",
      "result_status": 2,
      "result_status_name": "eReturnStatusSuccessFinishResult",
      "return_status": 2,
      "return_status_name": "eReturnStatusSuccessFinishResult",
      "succeeded": true
    },
    "diagnostics": [
      {
        "command": "device select EB90DDE0-50FB-5593-A792-E211E636A9EC",
        "event": "device_select_before",
        "monotonic_time": 0.262669282,
        "phase": "device selection"
      },
      {
        "error": "",
        "event": "device_select_after",
        "monotonic_time": 3.297132944,
        "output": "",
        "phase": "device selection",
        "return_status": 5,
        "return_status_name": "eReturnStatusStarted",
        "succeeded": false
      },
      {
        "command": "device process list",
        "event": "device_process_list_before",
        "monotonic_time": 3.297272597,
        "phase": "device process list verification"
      },
      {
        "error": "",
        "event": "device_process_list_after",
        "matching_pid": {
          "line": "29949  0                                                MH Unite",
          "name": "Unite",
          "pid": 29949
        },
        "monotonic_time": 3.43923733,
        "phase": "device process list verification",
        "return_status": 2,
        "return_status_name": "eReturnStatusSuccessFinishResult",
        "selected_device_verified": true,
        "succeeded": true
      },
      {
        "command": "device process attach --pid 29949",
        "event": "attach_before",
        "monotonic_time": 3.439308183,
        "phase": "device process attach",
        "selected_device_verified": true,
        "target_pid": 29949
      },
      {
        "error": "",
        "event": "attach_after",
        "monotonic_time": 3.486720282,
        "output": "",
        "phase": "device process attach",
        "return_status": 2,
        "return_status_name": "eReturnStatusSuccessFinishResult",
        "succeeded": true
      },
      {
        "event": "attach_state_wait_before",
        "monotonic_time": 3.487005414,
        "phase": "attach state wait",
        "process_state": {
          "pid": 29949,
          "state": 2,
          "state_name": "eStateConnected",
          "valid": true
        },
        "timeout_seconds": 30
      },
      {
        "event": "attach_state_wait_after",
        "final_state": {
          "pid": 29949,
          "state": 5,
          "state_name": "eStateStopped",
          "valid": true
        },
        "monotonic_time": 11.846896537,
        "phase": "attach state wait",
        "reached": true,
        "timed_out": false,
        "transitions": [
          {
            "phase": "attach",
            "pid": 29949,
            "source": "initial snapshot",
            "state": 2,
            "state_name": "eStateConnected"
          },
          {
            "event_pid": 29949,
            "is_process_event": true,
            "phase": "attach",
            "pid": 29949,
            "source": "state-change event",
            "state": 5,
            "state_name": "eStateStopped"
          },
          {
            "phase": "attach",
            "pid": 29949,
            "source": "current process snapshot",
            "state": 5,
            "state_name": "eStateStopped"
          }
        ]
      },
      {
        "event": "memory_inspection_before",
        "monotonic_time": 11.847188257,
        "phase": "read-only memory inspection",
        "pid": 29949,
        "process_state": {
          "pid": 29949,
          "state": 5,
          "state_name": "eStateStopped",
          "valid": true
        }
      },
      {
        "aslr_slide": "0x498c000",
        "cockpit_pointer": "0x10aa81500",
        "event": "memory_inspection_after",
        "executable_uuid": "58cc55c760ca3196b5d20c2aeb64b32b",
        "menu_selector_11B4_u32": "0x0",
        "menu_state_11B0_u8": "0x0",
        "monotonic_time": 11.865034462,
        "object_ptr_resolution": "exact named symbol",
        "object_ptr_runtime": "0x1050befc0",
        "phase": "read-only memory inspection"
      },
      {
        "event": "sbprocess_detach_before",
        "monotonic_time": 11.86531975,
        "phase": "SBProcess.Detach",
        "pid_matches_target": true,
        "process_handle_valid": true,
        "process_pid": 29949,
        "process_state": {
          "pid": 29949,
          "state": 5,
          "state_name": "eStateStopped",
          "valid": true
        }
      },
      {
        "event": "sbprocess_detach_after",
        "monotonic_time": 11.874181139,
        "phase": "SBProcess.Detach",
        "return_value_repr": "success",
        "sb_error_message": "",
        "sb_error_success": true
      },
      {
        "event": "detach_state_wait_before",
        "monotonic_time": 11.874274011,
        "phase": "detach state wait",
        "timeout_seconds": 20
      },
      {
        "event": "detach_state_wait_after",
        "final_state": {
          "pid": 29949,
          "state": 9,
          "state_name": "eStateDetached",
          "valid": true
        },
        "monotonic_time": 11.874348829,
        "phase": "detach state wait",
        "reached": true,
        "timed_out": false,
        "transitions": [
          {
            "phase": "detach",
            "pid": 29949,
            "source": "initial snapshot",
            "state": 9,
            "state_name": "eStateDetached"
          }
        ]
      }
    ],
    "executable_uuid": "58cc55c760ca3196b5d20c2aeb64b32b",
    "explicit_detach_attempted": true,
    "image_header_file": "0x100000000",
    "image_header_load": "0x10498c000",
    "inspection": "success",
    "ll_db_pid_match": {
      "line": "29949  0                                                MH Unite",
      "name": "Unite",
      "pid": 29949
    },
    "menu_selector_11B4_u32": "0x0",
    "menu_state_11B0_u8": "0x0",
    "object_ptr_resolution": "exact named symbol",
    "object_ptr_runtime": "0x1050befc0",
    "object_ptr_unslid": "0x100732fc0",
    "preflight_pid": 29949,
    "process_list_command": "device process list",
    "selected_device_verified": true,
    "selection": {
      "command": "device select EB90DDE0-50FB-5593-A792-E211E636A9EC",
      "error": "",
      "output": "",
      "result_status": 5,
      "result_status_name": "eReturnStatusStarted",
      "return_status": 5,
      "return_status_name": "eReturnStatusStarted",
      "succeeded": false
    },
    "selection_command": "device select EB90DDE0-50FB-5593-A792-E211E636A9EC",
    "state_before_detach": {
      "pid": 29949,
      "state": 5,
      "state_name": "eStateStopped",
      "valid": true
    }
  },
  "lldb_state_observations": [
    {
      "phase": "attach",
      "pid": 29949,
      "source": "initial snapshot",
      "state": 2,
      "state_name": "eStateConnected"
    },
    {
      "phase": "attach",
      "pid": 29949,
      "source": "state-change event",
      "state": 5,
      "state_name": "eStateStopped"
    },
    {
      "phase": "attach",
      "pid": 29949,
      "source": "current process snapshot",
      "state": 5,
      "state_name": "eStateStopped"
    },
    {
      "phase": "detach",
      "pid": 29949,
      "source": "initial snapshot",
      "state": 9,
      "state_name": "eStateDetached"
    }
  ],
  "lldb_stderr": "",
  "post_detach_pid": 29949,
  "post_detach_process_line": "29949   /private/var/containers/Bundle/Application/1A491814-FC3E-4E16-A688-C5896AD06220/MH Unite.app/MH Unite",
  "post_detach_process_list_exit_code": 0,
  "post_detach_verification_note": "devicectl process listing confirms the same PID is present; it does not report scheduler run/suspend state",
  "safety": {
    "breakpoints": false,
    "game_launch": false,
    "memory_writes": false,
    "register_writes": false,
    "watchpoints": false
  },
  "status": "success: read-only inspection and detach verified; game PID remains listed",
  "timestamp_utc": "2026-11-24T03:26:49.401689+00:00"
}
```
