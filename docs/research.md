# MHFU UI Reverse-Engineering Research

**Last updated:** November 24, 2026
**Status:** Runtime visual and functional relocation validated across menu cycles; permanent patch pending.

## Current result

**Atlas index 527 (`0x20F`) is runtime-confirmed to render the hamburger.** The proposed 4× source-coordinate mapping is supported by two tight spatial matches, including the historical runtime navigation-background reference (564).

| Index | Unslid record address | Atlas rectangle | Predicted pixels (4×) | Flags | Key |
|---:|---|---|---|---|---:|
| 527 (`0x20F`) | `0x10072F9B0` | `(221,147,27,38)` | `(884,588,108,152)` | `0x8004` | 11 |
| 564 (`0x234`) | `0x10072FB6C` | `(138,185,23,23)` | `(552,740,92,92)` | `0x8004` | 11 |


## Runtime milestone

Runtime proof of concept: changing geometry record 1 horizontal offset from -51.0 to -426.0 relocated the visible hamburger and functional touch region, and survived menu cycles (user-observed). Final right-edge placement, exclusive hitbox relocation, backing data and restart persistence remain unverified.

- Geometry record 1, `+0x10` Float32 horizontal offset: runtime address `0x106504870` in PID 30509, slide `0x404000`. Original `-51.0` (`0xC24C0000`); successful test `-426.0` (`0xC3D50000`).
- Descriptor initialization: `0x1003A35A4`; geometry calculator: `0x10039CFE0`; renderer: `0x1003A37C4`; vertex generator: `0x100378D6C` (unslid).
- Runtime descriptor 18 used atlas 527 in the observed closed layout. Original A/B/C rectangles: `(2165,169,81,129)`; source offset -150 initialized all three to `(2007,169,81,129)` and reached the draw call but did not visibly move the icon.
- Direct A.X=1565 moved graphics only. B/C independent edits and read watchpoints gave no useful results; their roles remain unresolved.
- Array replacement at `Cockpit + 0x12E8` explains loss of direct edits; watchpoint captured clear and reassignment in `0x1003A3280`.
- A larger upstream offset (-426) produced user-confirmed graphic movement, relocated touch functionality and survival across menu cycles. Exact resulting rectangle and original-hitbox inactivity were not tested.
- Apparent visual threshold between 1980 and 1990 is provisional; active descriptor addresses were not verified at every trial. No explicit clamp in inspected sprite generator/wrapper or packet pointer setter. Historical safe-area helper remains a lead despite negative API string search.

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
- Exact input consumer, original-hitbox exclusivity, final right-edge position, source backing data and restart-persistent patch remain unresolved.

## Next action

Verify that the original touch region no longer opens the menu, record the actual successful runtime rectangle, and check unrelated controls. Resolve right-edge placement using the existing game-specific safe-area helper `0x10049E4B4` as a bounded lead; do not assume it causes the apparent threshold. Locate the backing data or initialization source of geometry record 1, check sharing, then design a minimal reversible persistent patch on a working copy. Refresh PID, slide and pointers before any new session; preserve the baseline IPA and saves.

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
