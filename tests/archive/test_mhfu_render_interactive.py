import ast
import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from tools.archive import mhfu_render_interactive as interactive


class InteractiveStaticTests(unittest.TestCase):
    def test_module_parses_and_only_one_candidate_is_defined(self):
        source = Path(interactive.__file__).read_text()
        ast.parse(source)
        self.assertEqual(interactive.COCKPIT_DISPATCHER_UNSLID, 0x10037EDBC)
        self.assertEqual(interactive.MAX_TOTAL_HITS, 512)
        self.assertEqual(interactive.MAX_HITS_PER_SITE, 160)
        self.assertNotIn("AttachToProcess", source)
        self.assertNotIn("LaunchSimple", source)
        self.assertNotIn("WriteMemory", source)
        self.assertNotIn("SetValueFromCString", source)
        self.assertIn('breakpoint set --hardware --address', source)

    def test_command_registration_uses_current_module(self):
        class FakeDebugger:
            def __init__(self):
                self.commands = []

            def HandleCommand(self, command):
                self.commands.append(command)

        debugger = FakeDebugger()
        with contextlib.redirect_stdout(io.StringIO()):
            getattr(interactive, "__lldb_init_module")(debugger, {})
        self.assertEqual(len(debugger.commands), 1)
        self.assertIn("mhfu_render_command", debugger.commands[0])
        self.assertTrue(debugger.commands[0].endswith(" mhfu-render"))

    def test_capture_arguments_enforce_bounded_window(self):
        parsed = interactive._parse_capture_args(
            "--label hamburger-menu-opening --capture-seconds 30"
        )
        self.assertEqual(parsed["capture_seconds"], 30)
        self.assertEqual(parsed["label"], "hamburger-menu-opening")
        for value in (4, 31):
            with self.assertRaises(ValueError):
                interactive._parse_capture_args(
                    "--label test --capture-seconds %d" % value
                )
        with self.assertRaises(ValueError):
            interactive._parse_capture_args("--capture-seconds 10")

    def test_atomic_status_is_valid_json_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            interactive.atomic_write_json(path, {"stage": "running", "pid": 5})
            self.assertEqual(
                json.loads(path.read_text()),
                {"stage": "running", "pid": 5},
            )
            self.assertEqual(list(Path(directory).glob("*.tmp.*")), [])

    def test_fixed_capture_window_uses_monotonic_deadline(self):
        class FakeClock:
            now = 100.0

            def monotonic(self):
                return self.now

            def sleep(self, duration):
                self.now += duration

        class FakeProcess:
            def IsValid(self):
                return True

            def GetState(self):
                return 6

        class FakeLldb:
            eStateRunning = 6
            eStateStepping = 7
            eStateStopped = 5
            eStateExited = 10
            eStateCrashed = 8
            eStateInvalid = 0

        clock = FakeClock()
        with mock.patch.object(interactive.time, "monotonic", clock.monotonic), \
                mock.patch.object(interactive.time, "sleep", clock.sleep):
            result = interactive._wait_for_capture_window(
                FakeProcess(), FakeLldb(), 100.2, breakpoint_id=1
            )
        self.assertTrue(result["window_expired"])
        self.assertFalse(result["unexpected_stop"])
        self.assertEqual(result["reason"], "fixed capture window elapsed")
        self.assertAlmostEqual(clock.now, 100.2, places=6)

    def test_capture_window_aborts_on_stable_unexpected_stop_without_resume(self):
        class FakeThread:
            def GetStopReason(self):
                return 17

            def GetStopReasonDataAtIndex(self, index):
                return 17

        class FakeProcess:
            def IsValid(self):
                return True

            def GetState(self):
                return 5

            def GetSelectedThread(self):
                return FakeThread()

            def Continue(self):
                raise AssertionError("capture must never resume after a stop")

        class FakeLldb:
            eStateRunning = 6
            eStateStepping = 7
            eStateStopped = 5
            eStateExited = 10
            eStateCrashed = 8
            eStateInvalid = 0
            eStopReasonSignal = 17
            eStopReasonBreakpoint = 3

        old_active = interactive._ACTIVE
        stop_report = {}
        interactive._ACTIVE = {
            "lldb": FakeLldb,
            "report": stop_report,
        }
        try:
            result = interactive._wait_for_capture_window(
                FakeProcess(),
                FakeLldb(),
                interactive.time.monotonic() + 30,
                breakpoint_id=2,
            )
        finally:
            interactive._ACTIVE = old_active
        self.assertTrue(result["stopped"])
        self.assertTrue(result["unexpected_stop"])
        self.assertFalse(result["window_expired"])
        self.assertEqual(result["reason"], "stable process stop before capture deadline")
        self.assertEqual(stop_report["process_stop_observation"]["stop_reason_data"], [17])
        self.assertEqual(
            stop_report["process_stop_observation"]["stop_reason_name"],
            "eStopReasonSignal",
        )

    def test_owned_breakpoint_callback_stop_snapshot_does_not_end_window(self):
        class FakeClock:
            now = 0.0

            def monotonic(self):
                return self.now

            def sleep(self, duration):
                self.now += duration

        class FakeThread:
            def GetStopReason(self):
                return 3

            def GetThreadID(self):
                return 7

            def GetStopReasonDataCount(self):
                return 1

            def GetStopReasonDataAtIndex(self, index):
                return 2

        class FakeProcess:
            def __init__(self):
                self.states = [5, 6]

            def IsValid(self):
                return True

            def GetState(self):
                if self.states:
                    return self.states.pop(0)
                return 6

            def GetSelectedThread(self):
                return FakeThread()

        class FakeLldb:
            eStateRunning = 6
            eStateStepping = 7
            eStateStopped = 5
            eStateExited = 10
            eStateCrashed = 8
            eStateInvalid = 0
            eStopReasonBreakpoint = 3
            eStopReasonSignal = 5

        clock = FakeClock()
        old_active = interactive._ACTIVE
        interactive._ACTIVE = {
            "lldb": FakeLldb,
            "report": {"callback_stop_requested": False},
        }
        try:
            with mock.patch.object(interactive.time, "monotonic", clock.monotonic), \
                    mock.patch.object(interactive.time, "sleep", clock.sleep):
                result = interactive._wait_for_capture_window(
                    FakeProcess(), FakeLldb(), 0.15, breakpoint_id=2
                )
        finally:
            interactive._ACTIVE = old_active
        self.assertTrue(result["window_expired"])
        self.assertFalse(result["unexpected_stop"])

    def test_stopped_snapshot_with_ongoing_callbacks_does_not_end_window(self):
        class FakeClock:
            now = 0.0
            report = None

            def monotonic(self):
                return self.now

            def sleep(self, duration):
                self.now += duration
                if self.now <= 0.30:
                    self.report["total_callback_records"] += 1

        class FakeProcess:
            def IsValid(self):
                return True

            def GetState(self):
                return 5 if clock.now < 0.35 else 6

        class FakeLldb:
            eStateRunning = 6
            eStateStepping = 7
            eStateStopped = 5
            eStateExited = 10
            eStateCrashed = 8
            eStateInvalid = 0

        clock = FakeClock()
        report = {"total_callback_records": 0, "callback_errors": 0}
        clock.report = report
        old_active = interactive._ACTIVE
        interactive._ACTIVE = {
            "process": None,
            "lldb": FakeLldb,
            "report": report,
        }
        process = FakeProcess()
        interactive._ACTIVE["process"] = process
        try:
            with mock.patch.object(interactive.time, "monotonic", clock.monotonic), \
                    mock.patch.object(interactive.time, "sleep", clock.sleep):
                result = interactive._wait_for_capture_window(
                    process, FakeLldb(), 0.6, breakpoint_id=2
                )
        finally:
            interactive._ACTIVE = old_active
        self.assertTrue(result["window_expired"])
        self.assertFalse(result["unexpected_stop"])
        self.assertGreater(report["total_callback_records"], 0)
        self.assertAlmostEqual(clock.now, 0.6, places=6)

    def test_explicit_owned_breakpoint_callback_stop_ends_without_resume(self):
        class FakeThread:
            def GetStopReason(self):
                return 3

            def GetThreadID(self):
                return 7

            def GetStopReasonDataCount(self):
                return 1

            def GetStopReasonDataAtIndex(self, index):
                return 2

        class FakeProcess:
            def IsValid(self):
                return True

            def GetState(self):
                return 5

            def GetSelectedThread(self):
                return FakeThread()

            def Continue(self):
                raise AssertionError("must not resume a deliberate breakpoint stop")

        class FakeLldb:
            eStateRunning = 6
            eStateStepping = 7
            eStateStopped = 5
            eStateExited = 10
            eStateCrashed = 8
            eStateInvalid = 0
            eStopReasonBreakpoint = 3
            eStopReasonSignal = 5

        old_active = interactive._ACTIVE
        interactive._ACTIVE = {
            "lldb": FakeLldb,
            "report": {
                "callback_stop_requested": True,
                "callback_stop_reason": "callback exception",
            },
        }
        try:
            result = interactive._wait_for_capture_window(
                FakeProcess(),
                FakeLldb(),
                interactive.time.monotonic() + 10,
                breakpoint_id=2,
            )
        finally:
            interactive._ACTIVE = old_active
        self.assertTrue(result["breakpoint_stop"])
        self.assertFalse(result["unexpected_stop"])
        self.assertEqual(result["reason"], "callback exception")

    def test_running_observation_tolerates_stale_pre_continue_stopped_snapshot(self):
        class FakeProcess:
            def __init__(self):
                self.states = [5, 5, 6]

            def IsValid(self):
                return True

            def GetState(self):
                if len(self.states) > 1:
                    return self.states.pop(0)
                return self.states[0]

        class FakeLldb:
            eStateRunning = 6
            eStateStepping = 7
            eStateStopped = 5
            eStateExited = 10
            eStateCrashed = 8
            eStateInvalid = 0

        self.assertTrue(
            interactive._wait_for_running(FakeProcess(), FakeLldb(), 0.5)
        )

    def test_readiness_and_capture_deadline_are_explicitly_recorded(self):
        source = Path(interactive.__file__).read_text()
        self.assertIn('"stage": stage', source)
        self.assertIn("ready_state != lldb_api.eStateRunning", source)
        self.assertIn('"capture_deadline_monotonic": deadline_monotonic', source)
        self.assertIn("_wait_for_capture_window", source)
        self.assertNotIn("_wait_for_operator_ack", source)
        self.assertNotIn("select.select", source)
        self.assertNotIn("os.read(", source)
        self.assertIn("process.Stop()", source)
        tree = ast.parse(source)
        finalize = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_finalize"
        )
        calls = [
            node.func.attr
            for node in ast.walk(finalize)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        self.assertNotIn("Continue", calls)

    def test_operator_banner_and_final_summary_describe_fixed_window(self):
        banner = interactive._ready_banner(30, 29949)
        self.assertIn("MHFU CAPTURE READY", banner)
        self.assertIn("Process 29949 is RUNNING", banner)
        self.assertIn("Fixed capture window: 30 seconds", banner)
        self.assertIn("No Enter key or acknowledgement is required", banner)
        self.assertIn("stopped automatically", banner)

        summary = interactive._format_final_summary(
            {
                "status": "complete",
                "process_state_name": "eStateStopped",
                "capture_window_elapsed_seconds": 30.0,
                "capture_stop_reason": "fixed capture window elapsed",
                "observed_breakpoint_hits": 2,
                "stop_inferred_hits": 1,
                "callback_records": 2,
                "breakpoint_cleanup": {
                    "verified": True,
                    "remaining_breakpoint_ids": [],
                },
                "report_path": "attempts.jsonl",
            }
        )
        for expected in (
            "MHFU CAPTURE SUMMARY",
            "Final process state: eStateStopped",
            "Capture elapsed seconds: 30.0",
            "Capture stop reason: fixed capture window elapsed",
            "Observed breakpoint hits: 2",
            "Stop-inferred hits: 1",
            "Callback records: 2",
            "Breakpoint cleanup verified: yes",
            "JSONL report: attempts.jsonl",
        ):
            self.assertIn(expected, summary)
        failed_summary = interactive._format_final_summary(
            {
                "status": "incomplete: cleanup unverified",
                "process_state_name": "eStateRunning",
                "breakpoint_cleanup": {
                    "verified": False,
                    "remaining_breakpoint_ids": [2],
                },
            }
        )
        self.assertIn("Remaining owned breakpoint IDs: 2", failed_summary)
        self.assertIn("process interrupt", failed_summary)
        self.assertIn("breakpoint delete 2", failed_summary)
        self.assertIn("breakpoint list", failed_summary)

    def test_stage_snapshots_are_not_printed_to_operator_terminal(self):
        source = Path(interactive.__file__).read_text()
        publish = source[source.index("def _publish"):source.index("def _operator_print")]
        self.assertIn("atomic_write_json", publish)
        self.assertNotIn("print(", publish)
        self.assertNotIn("MHFU_RENDER_STAGE", source)

    def test_breakpoint_stop_preserves_evidence_and_cleans_without_resuming(self):
        class FakeThread:
            def GetStopReason(self):
                return 3

            def GetStopReasonDataAtIndex(self, index):
                return 1

        class FakeProcess:
            def __init__(self):
                self.states = [5, 6, 6]
                self.stop_calls = 0

            def IsValid(self):
                return True

            def GetState(self):
                if self.states:
                    return self.states.pop(0)
                return 5 if self.stop_calls else 6

            def GetProcessID(self):
                return 29949

            def GetSelectedThread(self):
                return FakeThread()

            def Stop(self):
                self.stop_calls += 1
                self.states.clear()
                return type(
                    "StopResult",
                    (),
                    {"Success": lambda self: True, "GetCString": lambda self: ""},
                )()

            def Continue(self):
                raise AssertionError("cleanup must never resume")

        class FakeBreakpoint:
            def __init__(self):
                self.valid = True

            def GetHitCount(self):
                return 1

            def IsValid(self):
                return self.valid

        class FakeTarget:
            def __init__(self, bp):
                self.bp = bp

            def BreakpointDelete(self, bp_id):
                self.bp.valid = False
                return True

            def FindBreakpointByID(self, bp_id):
                return self.bp if self.bp.valid else None

        class FakeLldb:
            eStateStopped = 5
            eStateRunning = 6
            eStateStepping = 7
            eStateExited = 10
            eStateCrashed = 8
            eStateInvalid = 0
            eStopReasonBreakpoint = 3

        bp = FakeBreakpoint()
        process = FakeProcess()
        report = {
            "run_id": "mock-run",
            "pid": 29949,
            "breakpoint_id": 1,
            "breakpoint_ids_owned": [1],
            "callback_records": 1,
            "total_callback_records": 1,
            "hits": [{"caller_return_unslid": "0x100123456"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            ctx = {
                "report": report,
                "process": process,
                "target": FakeTarget(bp),
                "breakpoint": bp,
                "lldb": FakeLldb,
                "status_path": Path(directory) / "status.json",
                "callback_lock": threading.RLock(),
            }
            old_active = interactive._ACTIVE
            interactive._ACTIVE = ctx
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    interactive._finalize(ctx)
            finally:
                interactive._ACTIVE = old_active
        self.assertEqual(report["observed_breakpoint_hits"], 1)
        self.assertEqual(report["stop_inferred_hits"], 1)
        self.assertEqual(report["hits"][0]["caller_return_unslid"], "0x100123456")
        self.assertTrue(report["breakpoint_cleanup"]["verified"])
        self.assertEqual(process.stop_calls, 1)
        self.assertFalse(bp.valid)
        self.assertTrue(report["stopped_verified"])

    def test_orphaned_breakpoint_callback_fails_closed(self):
        old_active = interactive._ACTIVE
        interactive._ACTIVE = None
        try:
            self.assertTrue(interactive.on_render_hit(None, None, None))
        finally:
            interactive._ACTIVE = old_active

    def test_callback_exception_fails_closed(self):
        class FakeBreakpointLocation:
            def GetBreakpoint(self):
                raise RuntimeError("mock callback access failure")

        with tempfile.TemporaryDirectory() as directory:
            ctx = {
                "report": {
                    "run_id": "mock-callback-error",
                    "callback_errors": 0,
                    "hits": [],
                },
                "status_path": Path(directory) / "status.json",
                "callback_lock": threading.RLock(),
            }
            old_active = interactive._ACTIVE
            interactive._ACTIVE = ctx
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertTrue(
                        interactive.on_render_hit(
                            None, FakeBreakpointLocation(), None
                        )
                    )
            finally:
                interactive._ACTIVE = old_active
        self.assertEqual(ctx["report"]["callback_errors"], 1)

    def test_cleanup_only_deletes_owned_breakpoints(self):
        class FakeProcess:
            def IsValid(self):
                return True

            def GetState(self):
                return 5

        class FakeBreakpoint:
            def __init__(self):
                self.valid = True

            def IsValid(self):
                return self.valid

        class FakeTarget:
            def __init__(self):
                self.breakpoints = {1: FakeBreakpoint(), 2: FakeBreakpoint()}
                self.deleted = []

            def BreakpointDelete(self, bp_id):
                self.deleted.append(bp_id)
                self.breakpoints[bp_id].valid = False
                return True

            def FindBreakpointByID(self, bp_id):
                bp = self.breakpoints.get(bp_id)
                return bp if bp and bp.valid else None

        class FakeLldb:
            eStateStopped = 5

        target = FakeTarget()
        with tempfile.TemporaryDirectory() as directory:
            ctx = {
                "report": {
                    "run_id": "mock-owned-breakpoint",
                    "breakpoint_ids_owned": [2],
                    "breakpoint_id": 2,
                },
                "process": FakeProcess(),
                "target": target,
                "lldb": FakeLldb,
                "status_path": Path(directory) / "status.json",
            }
            with contextlib.redirect_stdout(io.StringIO()):
                interactive._cleanup_breakpoint(ctx)
        self.assertEqual(target.deleted, [2])
        self.assertTrue(target.breakpoints[1].valid)
        self.assertFalse(target.breakpoints[2].valid)
        self.assertTrue(ctx["report"]["breakpoint_cleanup"]["verified"])

    def test_stop_recovery_attempts_are_finite(self):
        class FakeProcess:
            def __init__(self):
                self.stop_calls = 0

            def IsValid(self):
                return True

            def GetState(self):
                return 6

            def Stop(self):
                self.stop_calls += 1
                return type(
                    "StopResult",
                    (),
                    {"Success": lambda self: False, "GetCString": lambda self: "busy"},
                )()

        class FakeLldb:
            eStateRunning = 6
            eStateStepping = 7
            eStateStopped = 5
            eStateExited = 10
            eStateCrashed = 8
            eStateInvalid = 0

        process = FakeProcess()
        with tempfile.TemporaryDirectory() as directory:
            ctx = {
                "report": {"run_id": "bounded-stop"},
                "process": process,
                "lldb": FakeLldb,
                "status_path": Path(directory) / "status.json",
            }
            with contextlib.redirect_stdout(io.StringIO()):
                stopped = interactive._ensure_stopped(ctx, timeout=0.15)
        self.assertFalse(stopped)
        self.assertEqual(process.stop_calls, 2)
        self.assertLessEqual(
            len(ctx["report"]["stop_requests"]), 2
        )

    def test_cleanup_skips_running_process_but_reports_owned_id(self):
        class FakeProcess:
            def IsValid(self):
                return True

            def GetState(self):
                return 6

        class FakeLldb:
            eStateStopped = 5

        class FakeTarget:
            def __init__(self):
                self.deleted = []

            def BreakpointDelete(self, bp_id):
                self.deleted.append(bp_id)
                return True

        target = FakeTarget()
        with tempfile.TemporaryDirectory() as directory:
            ctx = {
                "report": {
                    "run_id": "cleanup-running",
                    "breakpoint_ids_owned": [2],
                },
                "process": FakeProcess(),
                "target": target,
                "lldb": FakeLldb,
                "status_path": Path(directory) / "status.json",
            }
            with contextlib.redirect_stdout(io.StringIO()):
                interactive._cleanup_breakpoint(ctx)
        self.assertEqual(target.deleted, [])
        cleanup = ctx["report"]["breakpoint_cleanup"]
        self.assertFalse(cleanup["verified"])
        self.assertEqual(cleanup["remaining_breakpoint_ids"], [2])

    def test_mocked_fixed_window_stops_and_cleans_owned_breakpoint(self):
        class FakeError:
            def Success(self):
                return True

            def GetCString(self):
                return ""

        class FakeCommandResult:
            def Succeeded(self):
                return True

            def GetOutput(self):
                return "Breakpoint 1 installed"

            def GetError(self):
                return ""

        class FakeAddress:
            def __init__(self, value):
                self.value = value

            def IsValid(self):
                return True

            def GetLoadAddress(self, target):
                return self.value + target.slide

            def GetFileAddress(self):
                return self.value

        class FakeFileSpec:
            def GetFilename(self):
                return "MH Unite"

        class FakeModule:
            def GetFileSpec(self):
                return FakeFileSpec()

            def GetUUIDString(self):
                return interactive.EXPECTED_UUID

            def GetObjectFileHeaderAddress(self):
                return FakeAddress(0x100000000)

            def ResolveFileAddress(self, value):
                return FakeAddress(value)

        class FakeBreakpoint:
            def __init__(self, bp_id):
                self.bp_id = bp_id
                self.valid = True
                self.enabled = True

            def GetID(self):
                return self.bp_id

            def IsValid(self):
                return self.valid

            def GetNumLocations(self):
                return 1

            def GetLocationAtIndex(self, index):
                del index
                return self

            def GetAddress(self):
                return self

            def GetLoadAddress(self, target):
                return interactive.COCKPIT_DISPATCHER_UNSLID + target.slide

            def IsHardware(self):
                return True

            def SetScriptCallbackFunction(self, spec):
                self.callback_spec = spec
                return None

            def GetHitCount(self):
                return 0

            def SetEnabled(self, enabled):
                self.enabled = enabled

        class FakeProcess:
            def __init__(self):
                self.state = 5

            def IsValid(self):
                return True

            def GetProcessID(self):
                return 29949

            def GetState(self):
                return self.state

            def Continue(self):
                self.state = 6
                return FakeError()

            def Stop(self):
                self.state = 5
                return FakeError()

            def GetSelectedThread(self):
                raise RuntimeError("no stop-inferred hit")

        class FakeTarget:
            slide = 0x498C000

            def __init__(self):
                self.process = FakeProcess()
                self.module = FakeModule()
                self.breakpoints = {}

            def IsValid(self):
                return True

            def GetProcess(self):
                return self.process

            def module_iter(self):
                return iter([self.module])

            def GetNumBreakpoints(self):
                return len(self.breakpoints)

            def GetBreakpointAtIndex(self, index):
                return list(self.breakpoints.values())[index]

            def FindBreakpointByID(self, bp_id):
                bp = self.breakpoints.get(bp_id)
                return bp if bp and bp.valid else None

            def BreakpointDelete(self, bp_id):
                self.breakpoints[bp_id].valid = False
                return True

        class FakeInterpreter:
            def __init__(self, target):
                self.target = target

            def HandleCommand(self, command, result):
                self.target.breakpoints[1] = FakeBreakpoint(1)
                return 2

        class FakeDebugger:
            def __init__(self):
                self.target = FakeTarget()
                self.async_enabled = False

            def GetSelectedTarget(self):
                return self.target

            def GetCommandInterpreter(self):
                return FakeInterpreter(self.target)

            def GetAsync(self):
                return self.async_enabled

            def SetAsync(self, value):
                self.async_enabled = value

        class FakeLldb:
            eStateStopped = 5
            eStateRunning = 6
            eStateStepping = 7
            eStateExited = 8
            eStateCrashed = 9
            eStateInvalid = 0
            eStopReasonBreakpoint = 3
            LLDB_INVALID_ADDRESS = (1 << 64) - 1

            class SBCommandReturnObject(FakeCommandResult):
                pass

        debugger = FakeDebugger()
        class FakeClock:
            now = 100.0

            def monotonic(self):
                return self.now

            def sleep(self, duration):
                self.now += duration

        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            status = Path(directory) / "status.json"
            report_path = Path(directory) / "attempts.jsonl"
            terminal = io.StringIO()
            with mock.patch.object(interactive.time, "monotonic", clock.monotonic), \
                    mock.patch.object(interactive.time, "sleep", clock.sleep), \
                    contextlib.redirect_stdout(terminal):
                report = interactive.capture_in_session(
                    debugger,
                    "--label hamburger-menu-opening --capture-seconds 5 "
                    "--status-file %s --report %s" % (status, report_path),
                    lldb_api=FakeLldb,
                )
            terminal_text = terminal.getvalue()
            self.assertEqual(
                report["status"], "complete",
                report.get("failure", "") + "\n" + report.get("traceback", ""),
            )
            self.assertTrue(report["ready"])
            self.assertTrue(report["capture_wait"]["window_expired"])
            self.assertAlmostEqual(report["capture_window_elapsed_seconds"], 5)
            self.assertEqual(report["capture_stop_reason"], "fixed capture window elapsed")
            self.assertNotIn("ack_received", report)
            self.assertEqual(report["observed_breakpoint_hits"], 0)
            self.assertEqual(report["callback_records"], 0)
            self.assertTrue(report["breakpoint_cleanup"]["verified"])
            self.assertIn("MHFU CAPTURE READY", terminal_text)
            self.assertIn("Fixed capture window: 5 seconds", terminal_text)
            self.assertIn("No Enter key or acknowledgement is required", terminal_text)
            self.assertNotIn("MHFU_RENDER_STAGE", terminal_text)
            self.assertEqual(debugger.target.process.state, FakeLldb.eStateStopped)
            self.assertEqual(report["process_state_name"], "eStateStopped")
            self.assertEqual(debugger.target.GetNumBreakpoints(), 1)
            self.assertFalse(debugger.target.breakpoints[1].valid)
            self.assertTrue(status.exists())
            self.assertEqual(json.loads(status.read_text())["stage"], "finished")
            records = [json.loads(line) for line in report_path.read_text().splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["run_id"], report["run_id"])


if __name__ == "__main__":
    unittest.main()
