# Phase 9 — Hamburger Geometry and Hitbox Finalization

**Date:** 2026-11-24  
**Project:** FUPatch4iPad  
**Status:** Working runtime prototype; permanent patch pending.

## Objective

Resume from Phase 8 with a clean process, isolate the responsiveness problem, and establish a visually acceptable right-edge hamburger with matching touch bounds. Preserve the original vertical position and avoid changes to input-processing code.

## 1. Clean baseline and edge behavior

The game was relaunched without LLDB. The original hamburger responded normally. A fresh LLDB session then reproduced the poor responsiveness using only a change to the shared geometry X offset, without hitbox expansion or enabled diagnostic breakpoints during functional testing.

| Source X offset | Observed behavior |
|---:|---|
| -51 | Original; normal taps work |
| 0 | Normal taps work consistently |
| +20 | Normal taps work consistently |
| +35 | Long press needed; normal taps unreliable |

The user also observed that taps near the physical screen edge were ignored for menu activation. This supports a position-dependent touch restriction or delay, but does not establish whether iPadOS, the game, or their interaction is responsible. The earlier two-finger and touch-end observations remain historical evidence, not a proven root cause. No input eligibility checks or timers were patched.

At the intermediate position, all three descriptor rectangles were measured as `(2291, 169, 81, 129)`. A screenshot showed a visible gap at the right edge despite an estimated overlay implying clipping. The assumed direct mapping of internal coordinates to native screenshot pixels was not verified; do not use that overlay as proof of a rendering/input mismatch.

## 2. Scaling experiments

Changing the geometry horizontal scale field at `+0x30` from 1 to 2 was retained in memory but did not visibly double the button width. The field's precise role remains unverified. Restoring it to 1 and changing the base width at `+0x20` from 51 to 102 did visibly increase width. The base height at `+0x24` was then enlarged as well. A 2× button was judged too large; the user preferred 1.5× and approved the final horizontal position after small adjustments.

## 3. Final approved parameters

All values below are source floats, not screenshot pixels.

| Source | Field | Original | Final | Final IEEE-754 hex |
|---|---|---:|---:|---|
| Shared geometry record 1 | X offset +0x10 | -51 | 12.5 | 0x41480000 |
| Shared geometry record 1 | Y offset +0x14 | 106 | 106 | 0x42D40000 |
| Shared geometry record 1 | Width +0x20 | 51 | 76.5 | 0x42990000 |
| Shared geometry record 1 | Height +0x24 | 81 | 121.5 | 0x42F30000 |
| Shared geometry record 1 | Horizontal scale +0x30 | 1 | 1 | 0x3F800000 |
| Shared geometry record 1 | Vertical scale +0x34 | 1 | 1 | 0x3F800000 |
| Each hamburger compact layout record | Hitbox width +0x20 | 51 | 76.5 | 0x42990000 |
| Each hamburger compact layout record | Hitbox height +0x24 | 81 | 121.5 | 0x42F30000 |

The compact hitbox X/Y offsets were not modified in the fresh process. The final configuration enlarges the visual and hitbox dimensions by 50%, with the original Y source offset retained. Do not confuse these compact fields with the identically numbered offsets in the shared geometry record.

## 4. Runtime session and discovery

- PID: `30733`
- ASLR slide: `0x4E6C000`
- Converter: unslid `0x1003A35A4`, runtime `0x10520F5A4`
- Conditional breakpoint: unslid `0x1003A35D0`, runtime `0x10520F5D0`
- Condition: `*(unsigned int *)($x20 + 4) == 527`
- At the breakpoint: `x4` points to the shared geometry record, `x20` to the compact source, `x19` to the destination descriptor.
- Shared geometry record: `0x10AF6C860`
- Compact source records observed: `0x10AF6F7E0` and `0x10AF749E0` (first inferred from its observed width address minus 0x20).
- The prior phase identified two relevant layouts, open 21/index 11 and closed 23/index 18. The exact layout IDs were not independently reread during these Phase 9 compact-record captures.

All runtime addresses are session-specific. Rediscover them after restarting. No on-disk source offsets have been established in this phase.

### Runtime patch reference (PID 30733 only)

The following is a consolidated record of the successful edits, not a script to run blindly on a different process. Apply while stopped; allow layout regeneration afterward. The scale restore is included to undo the earlier experiment if necessary.

```lldb
memory write --size 4 0x10AF6C870 0x41480000
memory write --size 4 0x10AF6C880 0x42990000
memory write --size 4 0x10AF6C884 0x42F30000
memory write --size 4 0x10AF6C890 0x3F800000
memory write --size 4 0x10AF6F800 0x42990000
memory write --size 4 0x10AF6F804 0x42F30000
memory write --size 4 0x10AF74A00 0x42990000
memory write --size 4 0x10AF74A04 0x42F30000
```

## 5. Measured descriptor results

Descriptor rectangles consist of four 16-bit fields `(X, Y, W, H)` at offsets `+0x2C`, `+0x34`, and `+0x3C` respectively.

| Rectangle | After visual resize, before hitbox resize | After hitbox resize (second measured layout) |
|---|---|---|
| Primary visual | (2267, 169, 122, 194) | (2267, 169, 122, 194) |
| Secondary visual | (2267, 169, 122, 194) | (2267, 169, 122, 194) |
| Touch hitbox | (2267, 169, 81, 129) | (2267, 169, 122, 194) |

Before the hitbox resize, internal coverage was approximately 44% (81 × 129 / 122 × 194). Afterward, the measured layout had identical visual and touch bounds, with endpoints `(2267, 169)` and `(2389, 363)`. These are internal coordinates; physical screen coverage and edge delivery are not implied.

Verification procedure: break at the converter, save `x19` before stepping out, then read the descriptor:

```lldb
script desc = lldb.debugger.GetSelectedTarget().GetProcess().GetSelectedThread().GetSelectedFrame().FindRegister("x19").GetValueAsUnsigned()
thread step-out
script lldb.debugger.HandleCommand("memory read --format d --size 2 --count 12 %#x" % (desc + 0x2c))
```

Only execute this sequence after confirming the converter breakpoint actually stopped the process. Capturing registers from an unrelated stopped frame previously produced a null descriptor. Do not reuse destination descriptor addresses across layout regeneration.

Both compact source records were modified. The second record's generated output was explicitly verified. The first record's final generated output was not independently reread after its resize. Breakpoint 2 was disabled before normal functional testing, and the user reported that the resulting button worked. No quantified tap success rate or restart-persistence test was performed.

## 6. Decisions and remaining work

Freeze the approved 1.5× configuration; avoid unnecessary further visual or input changes. The larger inward extent appears to provide usable touch space despite the suspected edge restriction. This is a practical workaround, not proof that edge-touch delivery has been repaired.

Next milestone: permanent patch.

1. Verify both layout IDs and all three generated rectangles in each layout, ideally with read-only inspection of active descriptors.
2. Trace the original backing data or initialization path for shared geometry record 1 and both compact hamburger records. Do not assume heap addresses correspond directly to file offsets.
3. Check whether any other elements reference geometry record 1 or the affected compact records before choosing a permanent patch location.
4. Implement only the approved geometry and hitbox changes, with original-value checks, executable identity checks, and a rollback path. Preserve original input-processing logic.
5. Validate on a fresh launch of the patched game: visual alignment, open/close behavior, normal taps, other controls, and persistence across restart.

At the end of Phase 9, the runtime prototype was working and the permanent patch was not implemented. The exact screen-edge input mechanism, screenshot coordinate transform, and first layout's final calculated hitbox remain unverified.
