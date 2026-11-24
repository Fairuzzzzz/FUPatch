# MHFU UI Reverse-Engineering Research

**Last updated:** November 24, 2026
**Status:** Ongoing; no hamburger-specific draw call, hitbox, or patch is
confirmed.

## Current result

**Atlas index 527 (`0x20F`) is the leading large-hamburger candidate**, not yet runtime-confirmed. The proposed 4× source-coordinate mapping is supported by two tight spatial matches, including the historical runtime navigation-background reference (564).

| Index | Unslid record address | Atlas rectangle | Predicted pixels (4×) | Flags | Key |
|---:|---|---|---|---|---:|
| 527 (`0x20F`) | `0x10072F9B0` | `(221,147,27,38)` | `(884,588,108,152)` | `0x8004` | 11 |
| 564 (`0x234`) | `0x10072FB6C` | `(138,185,23,23)` | `(552,740,92,92)` | `0x8004` | 11 |


## Current texture evidence

| Artwork in `cock-5` | Visible bounds (X, Y, W, H) | Composition |
|---|---|---|
| Large hamburger | `(890, 593, 102, 142)` | Hamburger |
| Small hamburger | `(1544, 324, 43, 60)` | Hamburger |
| Large left navigation background | `(556, 745, 84, 84)` | Background only |
| Small left navigation button | `(1856, 4, 60, 60)` | Background plus arrow |

PVRTexTool 5.7.1 (Build `26.1@f61b9fab2511`, PVRTexLib v5.7.1) yields spatially plausible PNGs with remaining color abnormalities. Visible bounds are provisional, not complete sprite rectangles. Device assignments (larger iPad, smaller iPhone) remain hypotheses; scaling ratios differ between controls. The previous `(1804,604,187,119)` bounds, 2× vertical preview convention and original 8× candidate justification are superseded. Former indices 204/205/208/209 are unsupported, not globally excluded.

## Confirmed static and historical findings

- Standalone Ghidra 12.2 import matches the documented ARM64 executable SHA-256 `25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`. Previous REA analysis used the same documented artifact. Ghidra auto-analysis had Objective-C and demangler errors; see technical reference.
- `FUN_100375FD4` selects textures; `FUN_1003762B4` packs source fields without scaling; `FUN_100208DC0` links command blocks; `FUN_10036C920` indexes the 12-byte table at `0x10072E0FC`, builds source corners directly, and separately scales destination dimensions.
- Records 527 and 564 use key 11 and flags `0x8004` (sub-index 4). The archived runtime atlas-564 bytes match the Ghidra record; the earlier visual experiment moved only the navigation background.
- Bounded search of records 527–610 with that flags/key pair found 527 and 564 as the only overlaps for the four targets under 4×. Neither smaller variant matched within that scope. Ghidra reports zero direct references to record 527, compatible with dynamic indexing.
- The generic rectangle predicate and accepted-event branch were not reached in earlier confirmed hamburger activation experiments.

## Hypotheses and blockers

- 4× source-coordinate conversion and key 11/sub-index 4 mapping to `cock-5` are strongly suggested by spatial and historical runtime evidence, but not independently verified in the graphics interpreter or resource registration.
- Hamburger draw call, destination-coordinate origin, touch region and persistent patch remain unresolved.

## Next action

Attach LLDB to a fresh game process, verify executable identity and obtain the current ASLR slide (`image list -o -f`). Start with a conditional breakpoint at `0x10036C920 + slide` for `$w5 == 527` (sixth integer argument at function entry). Inspect registers and backtrace before making changes. If there is no hit during a verified hamburger-visible state, test the other known indexed helpers, particularly the historically observed `0x100378D6C` path (index at incoming `sp+8` in the atlas-564 experiment; verify the calling convention for the new candidate). `0x100375804` is another candidate (high 32 bits of ninth argument). A missed breakpoint is bounded negative evidence, not a global exclusion. Once the actual draw is captured, verify the destination X argument and perform a reversible position-only experiment; observe whether the hamburger moves and restore debugger state. Do not modify the baseline IPA or investigate the hitbox until rendering ownership is established.

## Historical leads and exclusions

The atlas-564 navigation-arrow experiment, the descriptor/dispatcher candidates,
the generic touch rectangle predicate, and the accepted-event path are detailed
in the [technical reference](technical-reference.md). They remain historical
leads or excluded candidates—not evidence of the hamburger's draw call or
hitbox. Earlier PVR conversion failures and the reasons for choosing the
PowerVR decoder are also recorded there.

Older reports and their original experiment context are retained in
[docs/archive/](archive/); raw device/render diagnostics are under
[docs/logs/](logs/). Historical bundle-ID and LLDB-attempt discrepancies are
called out in the [technical reference](technical-reference.md).
