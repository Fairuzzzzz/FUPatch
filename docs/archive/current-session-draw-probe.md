# Archived: Current-session diagnostics and draw probe

The source filename called this “Phase 8” while its title called it “Phase 5”.
It is retained under a descriptive filename to avoid perpetuating that
numbering mismatch. Current status is in [research.md](../research.md).

**Scope:** Read-only device checks and local LLDB-script validation. No
breakpoint was installed on the iPad, no game memory was written, and no app,
save, or IPA was modified.

## Current environment observations

Observed in the current session:

- Connected device: iPad Air 11-inch M2 (`iPad14,8`), iPadOS `18.7.3`.
- MH Unite is installed as version `1.00.11`, bundle ID
  `jp.co.capcom.mhp2g`.
- The process listing showed `MH Unite` running as PID `29949` at the time of
  inspection. This PID is session-specific.
- Local LLDB reports version `1700.0.9.46`.
- The `docs/PROJECT_HANDOFF.md` mentioned in the request is not present in this
  checkout. `docs/research.md` and `docs/research-phase4.md` were available and
  read before investigation.

The bundle ID differs from the historical value `jp.co.capcom.mhp2gwd` in
`docs/research.md`. The process was identified by the installed-app listing and
executable path, but the loaded executable UUID, live ASLR slide, and resolved
breakpoint locations have **not** been confirmed in this session. Historical
PIDs/slides are not reused as current values.

## Explorer review and update

The previous untracked `tools/mh_layout_explorer.py` had these unsupported or
stale assumptions:

- It targeted `0x100378D14`, while the Phase 4 notes documented the successful
  visual experiment at `0x100378D6C`.
- It filtered on caller LR `0x1003A4158`, which is not established in the
  available research documents.
- It used `(w1, w2, w3, w4)` as an operation identity and changed `w3/w4`.
  Phase 4 instead records X/Y in `x1/x2` at the `0x100378D6C` operation.
- It derived slide from the loaded image header while assuming preferred base
  `0x100000000`, did not verify the executable UUID, and grouped arbitrary
  signatures into a grid rather than selecting a known operation.

The explorer now defaults to observe-only discovery at `0x100378D6C`, verifies
the expected UUID, resolves the unslid address through the loaded module, and
reports caller LR, atlas selector (read-only from entry `SP+8`), stable
arguments, current coordinates, and hit count. A discovery pass is bounded to
512 breakpoint callbacks and disables its breakpoint until `resume` is used.
It can optionally relocate a selected operation by setting invocation
registers `x1/x2` to absolute **renderer-coordinate** values; those values are
not yet mapped to physical screen pixels. `move-x` changes only X and preserves
the incoming Y. Relocation is off by default and requires `select`, `move` or
`move-x`, and then `on`; `off` or `restore` immediately disables it. The script
does not write target memory. The documented X/Y and atlas argument locations
remain historical evidence and must be rechecked before relocation in the
current process. Relocating a visual draw does not establish or relocate its
touch region.

Validation performed locally:

- Python AST syntax parse passed.
- `git diff --check` passed.
- Current local LLDB imported the script, registered `mhgrid`, and ran
  `mhgrid list` successfully without a target.

These checks do not test breakpoint resolution, callback behavior, current
process registers, or on-device performance.

## Proposed bounded runtime identification test

Pending an LLDB session attached to the already-running process:

1. Read the selected target's executable path, UUID, and process ID. Refuse to
   proceed if the UUID is not `58cc55c760ca3196b5d20c2aeb64b32b`.
2. Resolve `0x100378D6C` using the loaded module and report the current slide
   and runtime address.
3. Capture a short, menu-closed baseline with the explorer installed but
   relocation OFF. Inspect actual caller/atlas/argument records. Do not infer
   that a record is the hamburger from its coordinates alone.
4. Compare a captured candidate with the live screen. If a candidate is
   ambiguous, add a narrower caller/atlas filter based on the observed runtime
   values before continuing; do not guess a historical LR.
5. Only after the user identifies a specific draw call as the hamburger may a
   temporary register-only coordinate test be considered. The screen must be
   observed after each small test, and the old coordinates retained for
   immediate `off`/`restore`.
6. Investigate the touch region separately. Do not claim touch preservation
   from a visual-only move.

**Not yet performed:** LLDB attach, live UUID/slide/breakpoint checks, runtime
draw capture, screen comparison, user tap, or visual relocation.
