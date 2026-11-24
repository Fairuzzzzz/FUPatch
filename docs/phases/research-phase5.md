# MHFU iOS — Phase 5: Touch Input and UI Hitbox Reverse Engineering

**Status:** Hit-testing pipeline verified; left-arrow hitbox identification pending experimental confirmation  
**Target:** Monster Hunter Freedom Unite iOS v1.00.11  
**Device:** iPad Air M2 (`iPad14,8`), iPadOS 18.7.3  
**Debug session:** PID 29337  
**ASLR slide:** `0xF78000`  
**Mach-O UUID:** `58cc55c760ca3196b5d20c2aeb64b32b`

## 1. Executive Summary

We successfully traced the game's touchscreen input pipeline from UIKit touch events to native hit-testing routines.

The investigation established:

1. The game receives UIKit touch coordinates through `locationInView:`.
2. It scales both X and Y coordinates by `2.0`.
3. Scaled coordinates are stored in a five-slot input manager.
4. A per-frame update routine processes touch states.
5. The game maintains rectangular interactive regions.
6. A native function compares touch coordinates against those rectangles.
7. We identified a stored rectangle at `0x107070608`, matching the coordinates supplied to the hit-testing function.

The candidate rectangle is:

**X = 1809, Y = 109, Width = 102, Height = 76**

It is spatially consistent with the menu's left navigation arrow, whose visual coordinates were investigated in Phase 4.

**Important:** We have not yet verified that modifying this rectangle relocates the arrow's actual hitbox.

## 2. Confirmed Input Pipeline

```text
UIKit
  |
  v
locationInView:
  0x1013DB370
  |
  | CGPoint (double precision)
  v
Touch-coordinate handler
  0x1013DB28C
  |
  v
Input manager
  0x1013D8A24
  |
  | X *= 2.0
  | Y *= 2.0
  v
Touch-slot storage
  +0x60, +0x70, +0x80
  |
  v
Per-frame touch-state processing
  0x1013D86CC
  |
  v
UI interaction-region processor
  0x100F7F720
  |
  v
Touch-slot / rectangle evaluation
  0x1013D8C2C
  0x1013D8CB4
  |
  v
Point-in-rectangle comparison
  0x1013D8BD0
  |
  v
Interaction result / event flags
```

The diagram summarizes confirmed components of the input system. It does not imply that every function directly calls the next or that all listed functions have been proven to handle the left arrow specifically.

## 3. UIKit Touch-Coordinate Extraction

The native touch handler is located at:

| Address type | Address |
|---|---|
| Unslid | `0x10046328C` |
| Runtime | `0x1013DB28C` |

The relevant instructions are:

```asm
0x1013DB364: mov x0, x25
0x1013DB368: mov x1, x22
0x1013DB36C: mov x2, x20
0x1013DB370: bl  objc_msgSend
0x1013DB374: mov.16b v8, v0
0x1013DB378: mov.16b v9, v1
```

LLDB confirmed that the Objective-C selector at `0x1013DB370` is:

`locationInView:`

The returned coordinates were:

```text
d0 = 931.42117309570313
d1 = 75.263412475585938
```

These are UIKit view coordinates.

### Coordinate Conversion

The game forwards these coordinates to:

`0x1013D8A24` (unslid `0x100460A24`).

Inside this function:

```asm
0x1013D8A68: ldp  s0, s1, [x2]
0x1013D8A6C: ldr  s2, [x22, #0x5c]
0x1013D8A70: fmul s0, s0, s2
0x1013D8A74: fmul s1, s1, s2
```

The scaling factor at `InputManager + 0x5C` was verified as:

`2.0`

Therefore the captured touch position transforms to approximately:

```text
UIKit: (931.42, 75.26)
Game:  (1862.84, 150.53)
```

The input manager supports five touch slots, indexed from 0 through 4, with a stride of `0x60` bytes.

## 4. Input Manager Storage

The observed input manager base was:

`0x10B0002A0`

For touch slot 0:

| Offset | Observed address | Purpose |
|---|---|---|
| `+0x60` | `0x10B000300` | Current/copy coordinate pair |
| `+0x70` | `0x10B000310` | Scaled coordinate pair |
| `+0x80` | `0x10B000320` | Additional scaled coordinate pair |

The coordinate-copy helper:

`0x1013D9C0C` (unslid `0x100461C0C`)

is a straightforward two-float copy function:

```asm
ldr s0, [x1]
str s0, [x0]
ldr s0, [x1, #4]
str s0, [x0, #4]
ret
```

Read watchpoints confirmed copying from `0x10B000310` to `0x10B000300`.

### Per-Frame Input Processing

Watchpoints also identified:

`0x1013D86CC` (unslid `0x1004606CC`)

This function iterates over five touch slots, checking coordinates and updating touch-state fields.

The function `0x1013D87E8` resets touch slots by assigning `(-1.0, -1.0)` to coordinate pairs and clearing state fields.

A negative touch X coordinate is therefore used to identify inactive or invalid touch slots along the observed processing path.

## 5. UI Interaction-Region Processor

The most important subsequent discovery was:

`0x100F7F720`

Unlike the preceding touch-management helpers, this function processes rectangular input regions.

At its entry, the function receives an interaction-region pointer and a mode or count argument.

It loads four fields:

```asm
0x100F7F778: ldursh w8,  [x23, #-0x9]  ; X
0x100F7F77C: ldursh w9,  [x23, #-0x7]  ; Y
0x100F7F780: ldurh  w10, [x23, #-0x5]  ; Width
0x100F7F784: add    w10, w10, w8      ; Right
0x100F7F788: ldurh  w11, [x23, #-0x3]  ; Height
0x100F7F78C: add    w11, w11, w9      ; Bottom
```

The rectangle layout relative to the entry base is:

| Offset | Type | Meaning |
|---|---|---|
| `+0x00` | `int16` | Left X |
| `+0x02` | `int16` | Top Y |
| `+0x04` | `uint16` | Width |
| `+0x06` | `uint16` | Height |

The function converts the rectangle into four 32-bit boundaries:

`(Left, Top, Right, Bottom)`

It then calls touch-related evaluators such as:

- `0x1013D8C2C`
- `0x1013D8CB4`

The results are reflected in the associated interaction-region state fields.

## 6. Confirmed Point-in-Rectangle Function

**Runtime address:** `0x1013D8BD0`  
**Unslid address:** `0x100460BD0`

This function was verified through disassembly.

### Arguments

| Register | Meaning |
|---|---|
| `x1` | Pointer to touch X/Y (`float32[2]`) |
| `x2` | Pointer to rectangle boundaries (`int32[4]`) |
| `x8` | Pointer to result (`uint32`) |

### Comparison Logic

```asm
ldr   s0, [x1]          ; Touch X
ldr   s1, [x2]          ; Left
scvtf s1, s1
fcmp  s0, s1
b.lt  outside

ldr   s1, [x2, #8]      ; Right
scvtf s1, s1
fcmp  s0, s1
b.hi  outside

ldr   s0, [x1, #4]      ; Touch Y
ldr   s1, [x2, #4]      ; Top
scvtf s1, s1
fcmp  s0, s1
b.lt  outside

ldr   s1, [x2, #12]     ; Bottom
scvtf s1, s1
fcmp  s0, s1
b.ls  inside
```

The logic is equivalent to:

```python
inside = (
    left <= touch_x <= right
    and top <= touch_y <= bottom
)
```

The function writes `1` when the touch is inside the rectangle and `0` otherwise.

**This is a confirmed native UI hit-testing primitive.**

## 7. Candidate Left Navigation Arrow Hitbox

A breakpoint at `0x1013D8BD0` captured the following live invocation.

### Observed Touch Position

```text
Touch X = 1870.93726
Touch Y = 166.799988
```

### Observed Rectangle

```text
Left   = 1809
Top    = 109
Right  = 1911
Bottom = 185
```

The captured touch falls inside this rectangle.

### Backtrace

```text
0x1013D8BD0  Point-in-rectangle test
0x1013D8CB4  Touch-slot scanning
0x100F7F720  Interaction-region processing
0x1012E4D80  Higher-level interaction processing
0x1012E4C54  Higher-level caller
```

The rectangle is very close to the original menu visual coordinates documented in Phase 4:

| Property | X coordinate |
|---|---:|
| Menu descriptor origin | 1821 |
| Left-arrow circular background | 1822 |
| Captured hitbox left edge | 1809 |
| Captured hitbox right edge | 1911 |

This alignment makes the rectangle a strong candidate for the left navigation arrow's interactive area.

**Ownership remains unverified until a controlled hitbox-relocation experiment demonstrates the expected behavior.**

## 8. Verified Rectangle Storage Address

Using LLDB's frame selection, the interaction-region processor's registers were recovered:

```text
frame #2:
PC  = 0x100F7F8B0
x20 = 0x107070608
x23 = 0x107070611
```

The original rectangle begins at `x20`.

A direct memory read confirmed:

```text
0x107070608: 1809
0x10707060A: 109
0x10707060C: 102
0x10707060E: 76
```

This exactly matches the rectangle passed to the hit-testing function.

The record is stored in writable memory.

The address is specific to the current runtime session; its allocation lifetime and initialization source have not yet been established.

## 9. Pending Experiment — Relocate the Candidate Hitbox

The proposed experiment changes the rectangle's X coordinate by −600 while preserving the other fields.

| Field | Original | Proposed |
|---|---:|---:|
| X | 1809 | 1209 |
| Y | 109 | 109 |
| Width | 102 | 102 |
| Height | 76 | 76 |

Original hitbox:

`X = 1809–1911, Y = 109–185`

Proposed hitbox:

`X = 1209–1311, Y = 109–185`

### LLDB Test

With the process paused:

```lldb
memory write --size 2 --format d 0x107070608 1209
```

Verify:

```lldb
memory read --format d --size 2 --count 4 0x107070608
```

Then disable the generic hit-testing breakpoint:

```lldb
breakpoint disable 18
continue
```

Keep the Phase 4 visual modification (breakpoint 14) disabled.

### Expected Observations

If the candidate rectangle belongs to the left arrow and the write persists:

- The left-arrow graphics should remain at their original location.
- The original hitbox should no longer activate the arrow.
- The shifted region should activate the arrow instead.

The experiment may fail to move the hitbox if the game regenerates its interaction-region data each frame or if the identified rectangle belongs to another control.

### Restoration

Pause the process and restore the original X:

```lldb
memory write --size 2 --format d 0x107070608 1809
```

The modification is runtime-only and does not alter the IPA.

## 10. Remaining Questions

The next investigation should resolve:

1. Does the captured rectangle actually belong to the menu's left arrow?
2. Does modifying its stored X coordinate change the interactive region?
3. Does the stored rectangle persist between frames?
4. Which function creates or updates the rectangle?
5. Does the input rectangle originate from the same layout table used by the renderer?
6. Can the same method identify the always-visible hamburger control's hitbox?

## 11. Relationship to Phase 4

Phase 4 established that changing the resolved menu layout X coordinate moves the menu visually without moving its interactive hitboxes.

Phase 5 identifies a concrete input-coordinate pipeline and a likely corresponding interaction-region entry.

Together, these investigations provide two independent modification points:

| System | Identified control |
|---|---|
| Rendering | Resolved menu layout X at `0x10131D1C0` |
| Interaction | Candidate rectangle X at `0x107070608` |

The remaining challenge is establishing ownership and persistence, then identifying a stable modification strategy for both systems.

---

## Conclusion

**Milestone achieved:** We have identified and verified the game's generic point-in-rectangle hit-testing function and traced an actual touch evaluation to a stored UI rectangle.

**Next milestone:** Experimentally verify whether relocating that rectangle moves the left navigation arrow's hitbox.

This document intentionally distinguishes proven behavior from candidate control attribution and untested modifications.