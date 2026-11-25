# MHFU UI Reverse-Engineering Research

**Last updated:** November 24, 2026
**Status:** Right-edge runtime proof of concept; touch responsiveness unresolved; clean baseline restart next; permanent patch pending.

## Current result

**Atlas index 527 (`0x20F`) is runtime-confirmed to render the hamburger.** The proposed 4× source-coordinate mapping is supported by two tight spatial matches, including the historical runtime navigation-background reference (564).

| Index | Unslid record address | Atlas rectangle | Predicted pixels (4×) | Flags | Key |
|---:|---|---|---|---|---:|
| 527 (`0x20F`) | `0x10072F9B0` | `(221,147,27,38)` | `(884,588,108,152)` | `0x8004` | 11 |
| 564 (`0x234`) | `0x10072FB6C` | `(138,185,23,23)` | `(552,740,92,92)` | `0x8004` | 11 |


## Runtime milestone

Runtime relocation succeeded across menu cycles. Later rightward tests reached the edge: +50 was too far, +42 reached the edge, and +35 was preferred provisionally. At +35, A/B/C were `(2303,169,81,129)` before hitbox expansion. Expanded C was verified at `(2239,169,145,129)` (bounds 2239,169–2384,298). Ordinary taps remained intermittent; a sustained press (~2 seconds, user estimate) could open the menu, and holding another finger first could make a subsequent hamburger tap respond immediately. Original baseline responsiveness, final alignment/clipping, exclusive hitbox behavior and restart persistence remain unverified.

- Atlas 527 draw path, shared geometry record 1, layout replacement and independent compact records for layouts 21/23 are established.
- A/B are visual geometry (B is read by rendering/interpolation); C is the actual input rectangle, consumed at unslid `0x1003BCDE0`.
- Touch search `0x100460CB4` rejects ended touches; a captured in-bounds tap `(2343.48,239.01)` had begin=1/end=1 and returned -1.
- Hamburger flags `0x00010001` disable the optional per-button delay (bit 26); shared counter +0x54 is not checked by initial search.
- Touch lifecycle is updated through UIKit and CADisplayLink on main thread; hamburger search runs on thread 13. Timing relationship is not established. Conditional breakpoint polling counts (38 idle, 55 additional held) are confounded and not proof of throttling.
- Earlier apparent X=1980–1990 clamp is not supported by later right-edge success; stale descriptors confounded tests.
- See [phase 8](phases/research-phase8-hamburger-input.md) for addresses, patches and evidence.

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
- Original baseline responsiveness, final edge placement, exclusive hitbox relocation, backing data and restart-persistent patch remain unresolved. No global touch patch is justified yet.

## Next action

Fully quit and relaunch MHFU without LLDB; test the original hamburger with ordinary taps. Detach/quit was requested but completion and clean relaunch have not been reported. If baseline is responsive, attach afresh, refresh PID/slide/pointers, apply only the shared geometry X offset (+35 as a starting point), regenerate the layout and retest. Add hitbox changes only if necessary. If baseline is already delayed, investigate input delivery separately. Preserve baseline IPA and saves; no permanent patch yet.

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
