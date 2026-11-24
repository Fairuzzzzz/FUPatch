# Archived: Interactive MH Unite rendering diagnostic

This is the historical operator workflow for the interactive diagnostic.
Current research status is in [research.md](../research.md); its JSONL output
is retained in [logs/mhfu-render-interactive-attempts.jsonl](../logs/mhfu-render-interactive-attempts.jsonl).

This workflow reuses an operator-established LLDB session. It does not launch
or attach to a process. It installs only the hardware breakpoint at
`cockpit_dispatcher` (`0x10037EDBC` unslid), verifies the executable UUID and
ASLR slide, collects read-only breakpoint/caller evidence, and removes only
the breakpoint it installed. The process remains attached and stopped when the
command completes so the same LLDB session can be reused.

The existing `tools/mhfu_render_diagnostics.py`, probe, and historical JSONL
reports are retained. This workflow writes to
`docs/logs/mhfu-render-interactive-attempts.jsonl` and publishes the current stage
to `~/.mhfu-render-interactive/status.json`.

## Operator commands

Use the already trusted device/PID from the current preflight. Start LLDB
interactively, select the device, and attach manually:

```text
xcrun lldb
(lldb) device select EB90DDE0-50FB-5593-A792-E211E636A9EC
(lldb) device process attach --pid 29949
```

Wait for LLDB to report the process stopped. Then import the command module
and execute one capture:

```text
(lldb) command script import /Users/kolynlin/Code/FUPatch4iPad/tools/mhfu_render_interactive.py
(lldb) mhfu-render capture --label hamburger-menu-opening --capture-seconds 30
```

Replace the PID only after independently confirming the currently running
`MH Unite` PID. Keep the hamburger visible and menu closed before starting.
When the large `MHFU CAPTURE READY` banner appears and explicitly says
`eStateRunning`, the fixed capture window has started. Perform the intended UI
interaction during the window if desired. No Enter key, terminal input, or
acknowledgement is required. The command automatically stops the process at the
monotonic deadline.

If LLDB output is not visible promptly, a second local terminal can inspect the
atomic stage snapshot directly:

```sh
cat ~/.mhfu-render-interactive/status.json
```

Proceed only when it reports `"stage": "ready"` and
`"state": "eStateRunning"`.

The command collects for the configured fixed duration (5–30 seconds) from
observed running, using a monotonic deadline. It then stops the process,
verifies the stopped state, reads the counters, deletes and verifies deletion
of its breakpoint, and returns to the LLDB prompt. It does not resume the
process or detach it.
The command's final summary includes `final_process_state` and
`breakpoint_cleanup_verified`; the process should be stopped at completion.
If either is unverified, do not resume or start another capture; inspect the
LLDB state manually.

Use `Ctrl-C` to abort the command. The abort path attempts a stop and cleanup
but never resumes. If the LLDB prompt becomes available with the target
running, use LLDB's `process interrupt` manually and verify it is stopped
before any further action.

## Diagnostics and safety

Each potentially blocking LLDB operation has a preceding stage snapshot
written atomically to `~/.mhfu-render-interactive/status.json`. Routine JSON
stage messages are intentionally suppressed from the LLDB terminal; concise
human-readable progress, the readiness banner, and the final summary are shown
instead. The stage remains at
`*_before` if LLDB blocks in that operation, which distinguishes preflight,
UUID/address resolution, breakpoint/callback installation, Continue/running
observation, fixed capture window, stop, evidence collection, and cleanup. The
terminal readiness message is emitted only after the process state is observed
running.

The command reads the selected process only. It does not write memory or
registers, alter the IPA or saves, launch/restart the game, install software
breakpoints, or try other candidates. Callback records include caller return
addresses when resolvable to the expected MH Unite module. Limits remain 512
total callback hits and 160 hits at the active site.

The import and capture command are the only diagnostic LLDB commands needed
after the manual device selection and attach. No separate supervising process
or buffered subprocess output is involved.
