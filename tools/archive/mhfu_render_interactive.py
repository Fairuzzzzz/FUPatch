#!/usr/bin/env python3
"""Operator-assisted, in-session LLDB renderer diagnostic for MH Unite.

Import this module into an already-attached interactive LLDB session, then run
``mhfu-render capture --label hamburger-menu-opening --capture-seconds 30``.
The selected target must be the already-attached MH Unite process, stopped.
This module never launches or attaches to a process.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any


DEVICE_ID = "EB90DDE0-50FB-5593-A792-E211E636A9EC"
EXECUTABLE_NAME = "MH Unite"
EXPECTED_UUID = "58cc55c760ca3196b5d20c2aeb64b32b"
COCKPIT_DISPATCHER_UNSLID = 0x10037EDBC
MAX_TOTAL_HITS = 512
MAX_HITS_PER_SITE = 160
DEFAULT_CAPTURE_SECONDS = 30
MIN_CAPTURE_SECONDS = 5
MAX_CAPTURE_SECONDS = 30
RUNNING_START_TIMEOUT_SECONDS = 5
STOP_TIMEOUT_SECONDS = 8
STOP_STABLE_SECONDS = 0.2
POLL_SECONDS = 0.05
DEFAULT_STATUS_PATH = Path.home() / ".mhfu-render-interactive" / "status.json"
DEFAULT_REPORT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "logs"
    / "mhfu-render-interactive-attempts.jsonl"
)
CALLBACK_FUNCTION_NAME = "on_render_hit"

_ACTIVE: dict[str, Any] | None = None
_ACTIVE_LOCK = threading.RLock()


def atomic_write_json(path: str | Path, payload: dict[str, Any]) -> None:
    """Publish one complete status snapshot with an atomic replacement."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(
        target.name + ".tmp.%d.%d" % (os.getpid(), threading.get_ident())
    )
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


def _publish(ctx: dict[str, Any], stage: str, **fields: Any) -> None:
    ctx["report"].update(fields)
    snapshot = {
        "run_id": ctx["report"]["run_id"],
        "stage": stage,
        "updated_epoch": time.time(),
        "updated_monotonic": time.monotonic(),
        "pid": ctx["report"].get("pid"),
        "state": ctx["report"].get("process_state_name"),
        "ready_epoch": ctx["report"].get("ready_epoch"),
        "capture_deadline_epoch": ctx["report"].get("capture_deadline_epoch"),
        "capture_deadline_monotonic": ctx["report"].get(
            "capture_deadline_monotonic"
        ),
        "capture_window_elapsed_seconds": ctx["report"].get(
            "capture_window_elapsed_seconds"
        ),
        "breakpoint_id": ctx["report"].get("breakpoint_id"),
    }
    snapshot.update(fields)
    try:
        atomic_write_json(ctx["status_path"], snapshot)
    except OSError as error:
        ctx["report"].setdefault("status_write_errors", []).append(str(error))


def _operator_print(message: str) -> None:
    try:
        print(message, flush=True)
    except OSError:
        pass


def _ready_banner(seconds: int, pid: int) -> str:
    return (
        "\n"
        "============================================================\n"
        "                  MHFU CAPTURE READY\n"
        "============================================================\n"
        f"Process {pid} is RUNNING. Fixed capture window: {seconds} seconds.\n"
        "\n"
        "Capture is active now. Perform the intended UI interaction during\n"
        "this window if needed. No Enter key or acknowledgement is required.\n"
        "\n"
        "The process will be stopped automatically when the window expires.\n"
        "============================================================\n"
    )


def _format_final_summary(report: dict[str, Any]) -> str:
    cleanup = report.get("breakpoint_cleanup", {})
    verified = bool(cleanup.get("verified", False))
    remaining = cleanup.get("remaining_breakpoint_ids")
    if remaining is None:
        remaining = [
            item.get("breakpoint_id")
            for item in cleanup.get("items", [])
            if not item.get("invalidated", False)
        ]
    lines = [
        "MHFU CAPTURE SUMMARY",
        "Status: " + str(report.get("status", "unknown")),
        "Final process state: "
        + str(report.get("process_state_name", "unverified")),
        "Capture elapsed seconds: "
        + str(report.get("capture_window_elapsed_seconds", "unavailable")),
        "Capture stop reason: "
        + str(report.get("capture_stop_reason", "unavailable")),
        "Observed breakpoint hits: "
        + str(report.get("observed_breakpoint_hits", "unavailable")),
        "Stop-inferred hits: " + str(report.get("stop_inferred_hits", 0)),
        "Callback records: " + str(report.get("callback_records", 0)),
        "Breakpoint cleanup verified: " + ("yes" if verified else "NO"),
        "Remaining owned breakpoint IDs: "
        + (", ".join(map(str, remaining)) if remaining else "none confirmed"),
    ]
    if not verified:
        if remaining:
            if report.get("process_state_name") in {
                "eStateRunning",
                "eStateStepping",
            }:
                lines.append(
                    "Recovery: `process interrupt`; when stopped, run "
                    + "; ".join(
                        f"`breakpoint delete {bp_id}`" for bp_id in remaining
                    )
                    + "; then `breakpoint list`."
                )
            else:
                lines.append(
                    "Recovery: run "
                    + "; ".join(
                        f"`breakpoint delete {bp_id}`" for bp_id in remaining
                    )
                    + "; then `breakpoint list`."
                )
        else:
            lines.append("Recovery: run `breakpoint list` to verify no orphan remains.")
    lines.append("JSONL report: " + str(report.get("report_path", "unavailable")))
    return "\n".join(lines)


def _append_report(path: str | Path, report: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _process_state(process: Any) -> tuple[int | None, int | None, str]:
    if not process or not process.IsValid():
        return None, None, "invalid"
    value = int(process.GetState())
    lldb_api = _ACTIVE["lldb"] if _ACTIVE else None
    state_name = "unknown"
    if lldb_api is not None:
        state_name = next(
            (
                name
                for name in dir(lldb_api)
                if name.startswith("eState") and getattr(lldb_api, name) == value
            ),
            "unknown",
        )
    return int(process.GetProcessID()), value, state_name


def _find_main_module(target: Any) -> Any:
    for module in target.module_iter():
        spec = module.GetFileSpec()
        if spec and spec.GetFilename() == EXECUTABLE_NAME:
            return module
    return None


def _breakpoint_ids(target: Any) -> set[int]:
    return {
        int(target.GetBreakpointAtIndex(index).GetID())
        for index in range(int(target.GetNumBreakpoints()))
    }


def _register_unsigned(frame: Any, name: str) -> int | None:
    try:
        value = frame.FindRegister(name)
        if value and value.IsValid():
            return int(value.GetValueAsUnsigned())
    except Exception:
        pass
    return None


def _caller_file_address(target: Any, runtime_address: int | None) -> int | None:
    if runtime_address is None:
        return None
    try:
        address = target.ResolveLoadAddress(runtime_address)
        if not address or not address.IsValid():
            return None
        module = address.GetModule()
        if not module or not module.IsValid():
            return None
        spec = module.GetFileSpec()
        module_uuid = (module.GetUUIDString() or "").replace("-", "").lower()
        if (
            not spec
            or spec.GetFilename() != EXECUTABLE_NAME
            or module_uuid != EXPECTED_UUID
        ):
            return None
        file_address = int(address.GetFileAddress())
        return None if file_address < 0 else file_address
    except Exception:
        return None


def on_render_hit(frame: Any, bp_loc: Any, internal_dict: Any) -> bool:
    """Read-only callback; fail closed if its diagnostic owner is unavailable."""
    del internal_dict
    ctx = _ACTIVE
    if ctx is None:
        # A stale breakpoint must not silently auto-continue forever after its
        # owning capture context has gone away.
        return True
    try:
        with ctx["callback_lock"]:
            bp_id = int(bp_loc.GetBreakpoint().GetID())
            if bp_id != ctx["report"].get("breakpoint_id"):
                ctx["report"]["callback_stop_requested"] = True
                ctx["report"]["callback_stop_reason"] = (
                    "callback invoked for an unowned breakpoint"
                )
                return True
            report = ctx["report"]
            report["callback_records"] += 1
            report["total_callback_records"] += 1
            thread = frame.GetThread()
            lr = _register_unsigned(frame, "lr")
            pc = _register_unsigned(frame, "pc")
            caller = _caller_file_address(ctx["target"], lr)
            record = {
                "run_id": report["run_id"],
                "time_epoch": time.time(),
                "time_monotonic": time.monotonic(),
                "site": "cockpit_dispatcher",
                "breakpoint_id": bp_id,
                "hit_index": report["callback_records"],
                "total_hit_index": report["total_callback_records"],
                "thread_id": int(thread.GetThreadID()),
                "pc_runtime": None if pc is None else hex(pc),
                "caller_return_runtime": None if lr is None else hex(lr),
                "caller_return_unslid": None if caller is None else hex(caller),
                "caller_return_unslid_resolution": (
                    "MH Unite module"
                    if caller is not None
                    else "not resolved within MH Unite module"
                ),
                "registers_read_only": True,
            }
            report["hits"].append(record)
            if report["callback_records"] >= MAX_HITS_PER_SITE:
                ctx["breakpoint"].SetEnabled(False)
                report["site_hit_cap_reached"] = True
                _publish(
                    ctx,
                    "site_hit_cap_reached",
                    callback_records=report["callback_records"],
                    last_hit_epoch=record["time_epoch"],
                )
            if report["total_callback_records"] >= MAX_TOTAL_HITS:
                report["total_hit_cap_reached"] = True
                report["callback_stop_requested"] = True
                report["callback_stop_reason"] = "total callback hit cap reached"
                _publish(
                    ctx,
                    "total_hit_cap_reached",
                    total_callback_records=report["total_callback_records"],
                    last_hit_epoch=record["time_epoch"],
                )
                return True
    except Exception as error:
        ctx["report"]["callback_errors"] += 1
        ctx["report"]["callback_stop_requested"] = True
        ctx["report"]["callback_stop_reason"] = "callback exception"
        ctx["report"].setdefault("callback_error_details", []).append(
            {"error": str(error), "traceback": traceback.format_exc()}
        )
        _publish(ctx, "callback_error", error=str(error))
        return True
    return False


def _wait_for_running(process: Any, lldb_api: Any, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process or not process.IsValid():
            return False
        state_value = int(process.GetState())
        if state_value == lldb_api.eStateRunning:
            return True
        # Continue can return before LLDB's state snapshot advances from the
        # pre-continue stopped state. Keep waiting within the bound instead of
        # mistaking that stale snapshot for a confirmed failed resume.
        if state_value in {
            lldb_api.eStateExited,
            lldb_api.eStateCrashed,
            lldb_api.eStateInvalid,
        }:
            return False
        time.sleep(POLL_SECONDS)
    return False


def _running_states(lldb_api: Any) -> set[int]:
    return {
        int(lldb_api.eStateRunning),
        int(getattr(lldb_api, "eStateStepping", -1)),
    }


def _callback_activity_snapshot(process: Any) -> tuple[int, int] | None:
    ctx = _ACTIVE
    if ctx is None or ctx.get("process") is not process:
        return None
    report = ctx.get("report", {})
    return (
        int(report.get("total_callback_records", 0)),
        int(report.get("callback_errors", 0)),
    )


def _wait_for_stable_stopped(
    process: Any,
    lldb_api: Any,
    timeout: float,
    stable_seconds: float = STOP_STABLE_SECONDS,
) -> bool:
    deadline = time.monotonic() + timeout
    stopped_since = None
    last_activity = None
    while time.monotonic() < deadline:
        if not process or not process.IsValid():
            return False
        state_value = int(process.GetState())
        if state_value == lldb_api.eStateStopped:
            activity = _callback_activity_snapshot(process)
            if stopped_since is None or activity != last_activity:
                # LLDB may expose a stopped snapshot while a script callback
                # is still being dispatched/auto-continued. Do not classify it
                # as a stable stop until callback activity has also quiesced.
                stopped_since = time.monotonic()
            elif time.monotonic() - stopped_since >= stable_seconds:
                return True
            last_activity = activity
        else:
            stopped_since = None
            last_activity = None
        if state_value in {
            lldb_api.eStateExited,
            lldb_api.eStateCrashed,
            lldb_api.eStateInvalid,
        }:
            return False
        time.sleep(POLL_SECONDS)
    return False


def _wait_for_capture_window(
    process: Any,
    lldb_api: Any,
    deadline_monotonic: float,
    breakpoint_id: int,
) -> dict[str, Any]:
    """Collect until the monotonic deadline or a stable/terminal process stop."""
    active_states = _running_states(lldb_api)
    while True:
        remaining = deadline_monotonic - time.monotonic()
        if remaining <= 0:
            return {
                "window_expired": True,
                "stopped": False,
                "unexpected_stop": False,
                "reason": "fixed capture window elapsed",
            }
        if not process or not process.IsValid():
            return {
                "window_expired": False,
                "stopped": False,
                "unexpected_stop": True,
                "reason": "process handle became invalid during capture",
            }
        state_value = int(process.GetState())
        if state_value in active_states:
            time.sleep(min(POLL_SECONDS, remaining))
            continue
        if state_value == lldb_api.eStateStopped:
            stop_inferred = _stop_reason_evidence(process, breakpoint_id)
            if stop_inferred:
                report = _ACTIVE["report"] if _ACTIVE is not None else {}
                if report.get("callback_stop_requested"):
                    return {
                        "window_expired": False,
                        "stopped": True,
                        "breakpoint_stop": True,
                        "unexpected_stop": False,
                        "reason": report.get(
                            "callback_stop_reason",
                            "owned breakpoint callback requested stop",
                        ),
                    }
                # Script callbacks returning False normally auto-continue. A
                # stopped snapshot for this breakpoint can be transient while
                # LLDB is dispatching that callback; it is not the window end.
                time.sleep(min(POLL_SECONDS, remaining))
                continue
            if not _wait_for_stable_stopped(process, lldb_api, timeout=0.25):
                continue
            return {
                "window_expired": False,
                "stopped": True,
                "breakpoint_stop": False,
                "unexpected_stop": True,
                "reason": "stable process stop before capture deadline",
            }
        return {
            "window_expired": False,
            "stopped": False,
            "unexpected_stop": True,
            "reason": "terminal process state observed during capture",
        }


def _ensure_stopped(ctx: dict[str, Any], timeout: float) -> bool:
    """Require a stable stopped state; stop again if a transient state resumes."""
    process = ctx.get("process")
    lldb_api = ctx["lldb"]
    report = ctx["report"]
    if not process or not process.IsValid():
        return False
    deadline = time.monotonic() + timeout
    stop_attempts = 0
    report.setdefault("stop_requests", [])
    while time.monotonic() < deadline:
        state_value = int(process.GetState())
        if state_value == lldb_api.eStateStopped:
            remaining = max(0.0, deadline - time.monotonic())
            if _wait_for_stable_stopped(
                process,
                lldb_api,
                timeout=min(0.25, remaining),
            ):
                return True
            continue
        if state_value in _running_states(lldb_api):
            if stop_attempts >= 2:
                time.sleep(POLL_SECONDS)
                continue
            stop_attempts += 1
            _publish(
                ctx,
                "process_stop_before",
                stop_attempt=stop_attempts,
                reason="ensure stable stopped state for cleanup",
            )
            try:
                error = process.Stop()
                request = {
                    "attempt": stop_attempts,
                    "succeeded": bool(error.Success()),
                    "error": error.GetCString() or "",
                }
            except Exception as error:
                request = {
                    "attempt": stop_attempts,
                    "succeeded": False,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
            report["stop_requests"].append(request)
            _publish(ctx, "process_stop_after", **request)
            continue
        return False
    return False


def _stop_reason_evidence(process: Any, breakpoint_id: int) -> int:
    """Return one stop-inferred hit only for this breakpoint's stop reason."""
    observation: dict[str, Any] = {"captured": False}
    try:
        thread = process.GetSelectedThread()
        lldb_api = _ACTIVE["lldb"]
        reason = int(thread.GetStopReason())
        get_thread_id = getattr(thread, "GetThreadID", None)
        observation = {
            "captured": True,
            "thread_id": (
                int(get_thread_id()) if callable(get_thread_id) else None
            ),
            "stop_reason": reason,
            "stop_reason_name": next(
                (
                    name for name in dir(lldb_api)
                    if name.startswith("eStopReason")
                    and int(getattr(lldb_api, name)) == reason
                ),
                "unknown",
            ),
            "stop_reason_data": [],
        }
        count_method = getattr(thread, "GetStopReasonDataCount", None)
        count = int(count_method()) if callable(count_method) else 1
        for index in range(min(max(count, 0), 8)):
            observation["stop_reason_data"].append(
                int(thread.GetStopReasonDataAtIndex(index))
            )
        is_target_breakpoint = (
            reason == lldb_api.eStopReasonBreakpoint
            and observation["stop_reason_data"]
            and observation["stop_reason_data"][0] == int(breakpoint_id)
        )
        observation["matches_owned_breakpoint"] = bool(is_target_breakpoint)
        if _ACTIVE is not None:
            _ACTIVE["report"]["process_stop_observation"] = observation
        return int(bool(is_target_breakpoint))
    except Exception as error:
        observation["error"] = str(error)
        if _ACTIVE is not None:
            _ACTIVE["report"]["process_stop_observation"] = observation
        return 0


def _cleanup_breakpoint(ctx: dict[str, Any]) -> None:
    report = ctx["report"]
    bp_ids = list(report.get("breakpoint_ids_owned", []))
    if not bp_ids and report.get("breakpoint_id") is not None:
        bp_ids = [int(report["breakpoint_id"])]
    process = ctx.get("process")
    target = ctx.get("target")
    lldb_api = ctx["lldb"]
    if not bp_ids or target is None:
        return
    if not process or not process.IsValid() or int(process.GetState()) != lldb_api.eStateStopped:
        report["breakpoint_cleanup"] = {
            "attempted": False,
            "verified": False,
            "reason": "process not confirmed stopped; breakpoint left installed",
            "remaining_breakpoint_ids": bp_ids,
        }
        _publish(ctx, "breakpoint_cleanup_skipped")
        return
    results = []
    for bp_id in bp_ids:
        _publish(ctx, "breakpoint_delete_before", breakpoint_id=bp_id)
        try:
            deleted = bool(target.BreakpointDelete(int(bp_id)))
            remaining = target.FindBreakpointByID(int(bp_id))
            invalidated = not (remaining and remaining.IsValid())
            results.append(
                {
                    "breakpoint_id": int(bp_id),
                    "delete_returned": deleted,
                    "invalidated": invalidated,
                    "verified": deleted and invalidated,
                }
            )
        except Exception as error:
            results.append(
                {
                    "breakpoint_id": int(bp_id),
                    "delete_returned": False,
                    "invalidated": False,
                    "verified": False,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
            )
        _publish(
            ctx,
            "breakpoint_delete_after",
            breakpoint_id=bp_id,
            breakpoint_cleanup_item=results[-1],
        )
    report["breakpoint_cleanup"] = {
        "attempted": True,
        "items": results,
        "verified": bool(results) and all(item["verified"] for item in results),
        "remaining_breakpoint_ids": [
            item["breakpoint_id"]
            for item in results
            if not item["invalidated"]
        ],
    }
    _publish(
        ctx,
        "breakpoint_cleanup_verified",
        breakpoint_cleanup_verified=report["breakpoint_cleanup"]["verified"],
    )


def _cleanup_breakpoint_safely(ctx: dict[str, Any]) -> None:
    try:
        _cleanup_breakpoint(ctx)
    except Exception as error:
        report = ctx["report"]
        ids = list(report.get("breakpoint_ids_owned", []))
        if not ids and report.get("breakpoint_id") is not None:
            ids = [int(report["breakpoint_id"])]
        target = ctx.get("target")
        if target is not None:
            for bp_id in ids[:]:
                try:
                    bp = target.FindBreakpointByID(int(bp_id))
                    if not bp or not bp.IsValid():
                        ids.remove(bp_id)
                except Exception:
                    pass
        report["breakpoint_cleanup"] = {
            "attempted": True,
            "verified": False,
            "remaining_breakpoint_ids": ids,
            "error": str(error),
            "traceback": traceback.format_exc(),
        }
        _publish(
            ctx,
            "breakpoint_cleanup_exception",
            remaining_breakpoint_ids=ids,
            error=str(error),
        )


def _collect_counts(ctx: dict[str, Any]) -> None:
    report = ctx["report"]
    bp = ctx.get("breakpoint")
    observed = None
    if bp is not None:
        try:
            observed = int(bp.GetHitCount())
        except Exception as error:
            report["observed_hit_count_error"] = str(error)
    stop_inferred = 0
    if bp is not None and ctx.get("process") is not None:
        stop_inferred = _stop_reason_evidence(
            ctx["process"], report.get("breakpoint_id", -1)
        )
    report["observed_breakpoint_hits"] = observed
    report["stop_inferred_hits"] = stop_inferred
    report["callback_records"] = int(report.get("callback_records", 0))
    report["hit_count_source"] = "SBBreakpoint.GetHitCount (observed)"
    report["stop_inferred_hit_count_source"] = (
        "selected-thread stop reason; separate from observed hit count"
    )
    _publish(
        ctx,
        "evidence_collected",
        observed_breakpoint_hits=observed,
        stop_inferred_hits=stop_inferred,
        callback_records=report["callback_records"],
    )


def _finalize(ctx: dict[str, Any]) -> None:
    if ctx.get("finalization_started"):
        return
    ctx["finalization_started"] = True
    report = ctx["report"]
    process = ctx.get("process")
    if process and process.IsValid():
        _publish(ctx, "ensure_stopped_before_cleanup")
        try:
            report["stopped_verified"] = _ensure_stopped(
                ctx, STOP_TIMEOUT_SECONDS
            )
        except Exception as error:
            report["stopped_verified"] = False
            report["stop_state_verification_error"] = str(error)
    if process is not None:
        try:
            pid, state_value, state_name = _process_state(process)
            report["process_state"] = state_value
            report["process_state_name"] = state_name
        except Exception as error:
            pid = report.get("pid")
            report["process_state"] = None
            report["process_state_name"] = "unverified"
            report["process_state_error"] = str(error)
        report.setdefault("stopped_verified", False)
        _publish(
            ctx,
            "process_state_after_stop",
            pid=pid,
            process_state=state_value,
            process_state_name=state_name,
            stopped_verified=report.get("stopped_verified", False),
        )
    if report.get("stopped_verified"):
        try:
            _publish(ctx, "evidence_collection_before")
            _collect_counts(ctx)
        except Exception as error:
            report["evidence_collection_error"] = str(error)
            report["evidence_collection_traceback"] = traceback.format_exc()
        finally:
            _cleanup_breakpoint_safely(ctx)
        cleanup = report.get("breakpoint_cleanup", {})
        if (
            not cleanup.get("verified")
            and cleanup.get("reason") == "process not confirmed stopped; breakpoint left installed"
        ):
            report["cleanup_stop_retry"] = True
            try:
                if _ensure_stopped(ctx, STOP_TIMEOUT_SECONDS):
                    report["stopped_verified"] = True
                    _cleanup_breakpoint_safely(ctx)
            except Exception as error:
                report["cleanup_stop_retry_error"] = str(error)
    else:
        report["breakpoint_cleanup"] = {
            "attempted": False,
            "verified": False,
            "reason": "stopped state not verified; breakpoint left installed",
            "remaining_breakpoint_ids": list(
                report.get("breakpoint_ids_owned", [])
            ),
        }
        _publish(ctx, "cleanup_skipped_process_not_stopped")
    ctx["finalization_complete"] = True


def _parse_capture_args(arguments: str) -> dict[str, Any]:
    import argparse

    class ArgumentParser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            raise ValueError(message)

    parser = ArgumentParser(prog="mhfu-render capture", add_help=False)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--capture-seconds", type=int, default=DEFAULT_CAPTURE_SECONDS
    )
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--report", default=str(DEFAULT_REPORT_PATH))
    values = vars(parser.parse_args(shlex.split(arguments)))
    if not values["label"].strip():
        raise ValueError("label must not be empty")
    if not MIN_CAPTURE_SECONDS <= values["capture_seconds"] <= MAX_CAPTURE_SECONDS:
        raise ValueError("capture-seconds must be between 5 and 30")
    return values


def capture_in_session(
    debugger: Any,
    arguments: str,
    *,
    lldb_api: Any,
) -> dict[str, Any]:
    """Run one interactive capture using the already selected LLDB session."""
    global _ACTIVE
    options = _parse_capture_args(arguments)
    report: dict[str, Any] = {
        "run_id": uuid.uuid4().hex,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "device_id": DEVICE_ID,
        "report_path": str(Path(options["report"]).expanduser()),
        "capture_label": options["label"],
        "capture_seconds": options["capture_seconds"],
        "capture_mode": "fixed monotonic duration",
        "active_candidate": {
            "name": "cockpit_dispatcher",
            "unslid": hex(COCKPIT_DISPATCHER_UNSLID),
            "hardware_requested": True,
        },
        "memory_writes": False,
        "register_writes": False,
        "ipa_or_save_changes": False,
        "hits": [],
        "callback_records": 0,
        "total_callback_records": 0,
        "callback_errors": 0,
        "breakpoint_cleanup": {"attempted": False, "verified": False},
    }
    ctx: dict[str, Any] = {
        "debugger": debugger,
        "lldb": lldb_api,
        "report": report,
        "status_path": Path(options["status_file"]).expanduser(),
        "report_path": Path(options["report"]).expanduser(),
        "callback_lock": threading.RLock(),
        "target": None,
        "process": None,
        "breakpoint": None,
    }
    with _ACTIVE_LOCK:
        if _ACTIVE is not None:
            raise RuntimeError("an interactive renderer capture is already active")
        _ACTIVE = ctx

    try:
        _operator_print("MHFU: checking the selected, stopped LLDB process…")
        _publish(ctx, "preflight_selected_target_before")
        target = debugger.GetSelectedTarget()
        if not target or not target.IsValid():
            raise RuntimeError("no valid selected target; attach manually first")
        process = target.GetProcess()
        if not process or not process.IsValid():
            raise RuntimeError("selected target has no valid process")
        pid, state_value, state_name = _process_state(process)
        report["pid"] = pid
        report["process_state"] = state_value
        report["process_state_name"] = state_name
        if state_value != lldb_api.eStateStopped:
            raise RuntimeError(
                "expected the manually attached process to be stopped; "
                "observed " + state_name
            )
        ctx.update({"target": target, "process": process})
        _publish(
            ctx,
            "preflight_selected_target_after",
            pid=pid,
            process_state_name=state_name,
        )

        _operator_print("MHFU: verifying executable UUID and resolving ASLR address…")
        _publish(ctx, "uuid_verification_before")
        module = _find_main_module(target)
        if module is None:
            raise RuntimeError("MH Unite executable module was not found")
        module_uuid = (module.GetUUIDString() or "").replace("-", "").lower()
        report["executable_uuid"] = module_uuid
        if module_uuid != EXPECTED_UUID:
            raise RuntimeError("executable UUID mismatch; refusing breakpoint setup")
        header = module.GetObjectFileHeaderAddress()
        header_file = int(header.GetFileAddress())
        header_load = int(header.GetLoadAddress(target))
        invalid_address = int(getattr(lldb_api, "LLDB_INVALID_ADDRESS", -1))
        if (
            header_file == invalid_address
            or header_load == invalid_address
            or header_file < 0
            or header_load < 0
        ):
            raise RuntimeError("could not resolve executable header/ASLR slide")
        slide = header_load - header_file
        report["slide"] = hex(slide)
        _publish(ctx, "uuid_verification_after", executable_uuid=module_uuid)

        _publish(ctx, "address_resolution_before")
        file_address = module.ResolveFileAddress(COCKPIT_DISPATCHER_UNSLID)
        if not file_address or not file_address.IsValid():
            raise RuntimeError("Cockpit dispatcher address did not resolve")
        runtime_address = int(file_address.GetLoadAddress(target))
        if (
            runtime_address == invalid_address
            or runtime_address < 0
            or runtime_address - COCKPIT_DISPATCHER_UNSLID != slide
        ):
            raise RuntimeError("resolved runtime address disagrees with ASLR slide")
        report["runtime_address"] = hex(runtime_address)
        _publish(
            ctx,
            "address_resolution_after",
            unslid_address=hex(COCKPIT_DISPATCHER_UNSLID),
            runtime_address=hex(runtime_address),
            slide=hex(slide),
        )

        _operator_print("MHFU: installing the hardware breakpoint and callback…")
        _publish(
            ctx,
            "hardware_breakpoint_install_before",
            runtime_address=hex(runtime_address),
        )
        before_ids = _breakpoint_ids(target)
        command_result = lldb_api.SBCommandReturnObject()
        command_text = "breakpoint set --hardware --address 0x%x" % runtime_address
        command_status = debugger.GetCommandInterpreter().HandleCommand(
            command_text, command_result
        )
        after_ids = _breakpoint_ids(target)
        added_ids = sorted(after_ids - before_ids)
        report["breakpoint_command"] = command_text
        report["breakpoint_command_status"] = int(command_status)
        report["breakpoint_command_succeeded"] = bool(command_result.Succeeded())
        report["breakpoint_command_output"] = command_result.GetOutput() or ""
        report["breakpoint_command_error"] = command_result.GetError() or ""
        report["breakpoint_ids_owned"] = added_ids
        if len(added_ids) == 1:
            report["breakpoint_id"] = int(added_ids[0])
            ctx["breakpoint"] = target.FindBreakpointByID(added_ids[0])
        if not command_result.Succeeded() or len(added_ids) != 1:
            raise RuntimeError(
                "hardware breakpoint command failed or did not add exactly one "
                "new breakpoint: " + (report["breakpoint_command_error"] or "unknown")
            )
        bp = target.FindBreakpointByID(added_ids[0])
        if bp and bp.IsValid():
            report["breakpoint_id"] = int(bp.GetID())
            ctx["breakpoint"] = bp
        if not bp or not bp.IsValid() or int(bp.GetNumLocations()) != 1:
            raise RuntimeError("new hardware breakpoint identity/location is invalid")
        location = bp.GetLocationAtIndex(0)
        location_address = location.GetAddress()
        resolved_location = int(location_address.GetLoadAddress(target))
        if resolved_location != runtime_address:
            raise RuntimeError(
                "hardware breakpoint resolved to an unexpected runtime address"
            )
        is_hardware = getattr(bp, "IsHardware", None)
        if callable(is_hardware) and not is_hardware():
            raise RuntimeError("LLDB did not create a hardware breakpoint")
        report["resolved_breakpoint_locations"] = 1
        report["resolved_breakpoint_runtime"] = hex(resolved_location)
        _publish(
            ctx,
            "hardware_breakpoint_install_after",
            breakpoint_id=report["breakpoint_id"],
            command_output=report["breakpoint_command_output"],
        )

        _publish(ctx, "callback_resolution_before")
        callback_module = sys.modules.get(__name__)
        callback = getattr(callback_module, CALLBACK_FUNCTION_NAME, None)
        if callback is not on_render_hit:
            raise RuntimeError("LLDB callback module/function is not importable")
        callback_spec = __name__ + "." + CALLBACK_FUNCTION_NAME
        report["callback_spec"] = callback_spec
        report["callback_resolved"] = True
        _publish(ctx, "callback_resolution_after", callback_spec=callback_spec)

        _publish(ctx, "callback_install_before", callback_spec=callback_spec)
        callback_result = bp.SetScriptCallbackFunction(callback_spec)
        if callback_result is not None:
            success = getattr(callback_result, "Success", None)
            if callable(success) and not success():
                get_error = getattr(callback_result, "GetCString", None)
                raise RuntimeError(
                    "callback installation failed: "
                    + (get_error() if callable(get_error) else "")
                )
        report["callback_install_status"] = "installed"
        _publish(ctx, "callback_install_after", callback_spec=callback_spec)

        debugger_async_before = bool(debugger.GetAsync())
        report["debugger_async_before"] = debugger_async_before
        debugger.SetAsync(True)
        _operator_print("MHFU: continuing; waiting to observe the process running…")
        _publish(ctx, "continue_before", debugger_async_before=debugger_async_before)
        continue_error = process.Continue()
        if not continue_error.Success():
            raise RuntimeError(
                "process continue failed: " + (continue_error.GetCString() or "")
            )
        report["continue_returned"] = True
        _publish(ctx, "await_running")
        if not _wait_for_running(
            process, lldb_api, RUNNING_START_TIMEOUT_SECONDS
        ):
            _, current_state, current_name = _process_state(process)
            report["process_state"] = current_state
            report["process_state_name"] = current_name
            raise RuntimeError(
                "process was not observed running after Continue; state="
                + current_name
            )

        ready_pid, ready_state, ready_state_name = _process_state(process)
        if ready_state != lldb_api.eStateRunning:
            report["process_state"] = ready_state
            report["process_state_name"] = ready_state_name
            raise RuntimeError(
                "process stopped before readiness could be published; state="
                + ready_state_name
            )
        start_monotonic = time.monotonic()
        start_epoch = time.time()
        deadline_monotonic = start_monotonic + options["capture_seconds"]
        deadline_epoch = start_epoch + options["capture_seconds"]
        report.update(
            {
                "ready": True,
                "ready_epoch": start_epoch,
                "ready_monotonic": start_monotonic,
                "capture_start_epoch": start_epoch,
                "capture_deadline_epoch": deadline_epoch,
                "capture_deadline_monotonic": deadline_monotonic,
                "capture_window_seconds": options["capture_seconds"],
                "pid": ready_pid,
                "process_state": ready_state,
                "process_state_name": ready_state_name,
            }
        )
        _publish(
            ctx,
            "ready",
            ready=True,
            ready_epoch=start_epoch,
            capture_deadline_epoch=deadline_epoch,
            capture_deadline_monotonic=deadline_monotonic,
            process_state_name=ready_state_name,
            capture_window_seconds=options["capture_seconds"],
        )
        _operator_print(_ready_banner(options["capture_seconds"], pid))
        _publish(ctx, "capture_window_begin")
        capture_wait = _wait_for_capture_window(
            process,
            lldb_api,
            deadline_monotonic,
            report["breakpoint_id"],
        )
        capture_end_monotonic = time.monotonic()
        report["capture_wait"] = capture_wait
        report["capture_stop_reason"] = capture_wait["reason"]
        report["capture_window_elapsed_seconds"] = round(
            capture_end_monotonic - start_monotonic, 6
        )
        report["capture_end_monotonic"] = capture_end_monotonic
        report["capture_end_epoch"] = time.time()
        report["unexpected_stop"] = bool(capture_wait.get("unexpected_stop"))
        _publish(
            ctx,
            "capture_window_end",
            capture_stop_reason=report["capture_stop_reason"],
            capture_window_elapsed_seconds=report[
                "capture_window_elapsed_seconds"
            ],
            unexpected_stop=report["unexpected_stop"],
        )
        _operator_print(
            "MHFU: " + report["capture_stop_reason"]
            + "; stopping, collecting evidence, and cleaning up…"
        )

        _finalize(ctx)
        if not report.get("stopped_verified"):
            raise RuntimeError("capture process stop was not verified")
        if report.get("callback_errors"):
            report["status"] = (
                "incomplete: callback error stopped capture; evidence may be partial"
            )
        elif report.get("unexpected_stop"):
            report["status"] = (
                "incomplete: unexpected stop observed; no automatic resume attempted"
            )
        elif not capture_wait.get("window_expired"):
            report["status"] = (
                "incomplete: capture ended before its fixed window; "
                + report["capture_stop_reason"]
            )
        elif not report.get("breakpoint_cleanup", {}).get("verified"):
            report["status"] = (
                "incomplete: capture completed but breakpoint cleanup "
                "was not verified"
            )
        else:
            report["status"] = "complete"
    except KeyboardInterrupt:
        report["interrupted_by_operator"] = True
        report["status"] = "interrupted; no automatic resume attempted"
        try:
            _finalize(ctx)
        except Exception as error:
            report["finalize_error"] = str(error)
    except Exception as error:
        report["status"] = "failed"
        report["failure"] = str(error)
        report["traceback"] = traceback.format_exc()
        try:
            _publish(ctx, "error", error=str(error))
        except Exception:
            pass
        try:
            _finalize(ctx)
        except Exception as finalize_error:
            report["finalize_error"] = str(finalize_error)
    finally:
        if "debugger_async_before" in report:
            try:
                debugger.SetAsync(bool(report["debugger_async_before"]))
            except Exception as error:
                report["debugger_async_restore_error"] = str(error)
        report["finished_epoch"] = time.time()
        report["finished_monotonic"] = time.monotonic()
        try:
            _publish(ctx, "report_append_before")
            _append_report(ctx["report_path"], report)
            _publish(ctx, "report_append_after")
        except Exception as error:
            report["report_append_error"] = str(error)
        try:
            _publish(ctx, "finished", final_status=report.get("status"))
        except Exception:
            pass
        with _ACTIVE_LOCK:
            _ACTIVE = None
    return report


def mhfu_render_command(
    debugger: Any, command: str, result: Any, internal_dict: Any
) -> None:
    """LLDB command: mhfu-render capture --label ... [--capture-seconds N]."""
    del internal_dict
    try:
        words = shlex.split(command)
        if not words or words[0] in {"help", "-h", "--help"}:
            result.AppendMessage(
                "Usage: mhfu-render capture --label LABEL "
                "[--capture-seconds 5..30] [--status-file PATH] [--report PATH]"
            )
            return
        if words[0] != "capture":
            raise ValueError("only the 'capture' subcommand is supported")
        report = capture_in_session(
            debugger,
            shlex.join(words[1:]),
            lldb_api=__import__("lldb"),
        )
        result.AppendMessage(_format_final_summary(report))
        if report.get("failure"):
            result.SetError(str(report["failure"]))
    except Exception as error:
        result.SetError(str(error))


def __lldb_init_module(debugger: Any, internal_dict: Any) -> None:
    """Register one command in the existing LLDB command interpreter."""
    del internal_dict
    debugger.HandleCommand(
        "command script add -f "
        + __name__
        + ".mhfu_render_command mhfu-render"
    )
    print(
        "mhfu-render loaded. Existing selected process only; no launch or attach.",
        flush=True,
    )
