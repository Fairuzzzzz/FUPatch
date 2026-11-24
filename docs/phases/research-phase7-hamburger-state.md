# Phase 7 — Hamburger Menu State and Cockpit Transition Analysis

**Project:** FUPatch4iPad  
**Target:** Monster Hunter Freedom Unite iOS v1.00.11  
**Device:** iPad Air 11-inch (M2), iPadOS 18.7.3  
**Research status:** Menu state transition verified; hamburger rendering and hitbox not yet identified  
**Suggested filename:** `docs/research-phase7-hamburger-state.md`

---

## 1. Objective

Identify the rendering path and touch-input region of the persistent hamburger menu icon in Monster Hunter Freedom Unite.

The project's final objective is to relocate this icon to the appropriate right-edge position on the iPad while preserving its original:

- Visual size
- Vertical position
- Partially clipped appearance
- Touch functionality
- Behavior across UI states

Phase 6 successfully demonstrated that Cockpit UI touch regions can be relocated independently of their visuals.

Phase 7 investigates the hamburger icon itself, using changes in the application's menu state to narrow down the relevant code.

## 2. Important UI Observations

The hamburger icon and the Cockpit menu are related but distinct elements.

### Menu closed

- The hamburger icon is visible near the upper-right edge of the iPad display.
- The hamburger can be tapped to open the Cockpit menu.
- The Cockpit menu's navigation controls are not displayed in their open-menu arrangement.

### Menu open

- The hamburger icon becomes visually hidden.
- The Cockpit menu appears in the upper-right area.
- The menu includes navigation arrows and other controls.
- A separate close button appears near the lower-right corner of the display.

### Closing the menu

- The lower-right close button dismisses the menu.
- The hamburger immediately reappears in its original position.

**Important:** The hamburger icon, the menu navigation arrows, and the lower-right close button must not be treated as the same UI element.

It is not yet confirmed whether the hamburger and menu controls use the same rendering or input-handling functions.

---

## 3. Debugging Environment

The application was already running when this research session began.

The device process list reported:

```text
PID: 29949
Executable: MH Unite
```

LLDB was attached using the CoreDevice debugging interface.

The executable's ASLR slide was obtained using:

```lldb
image list -o -f
```

Result:

```text
ASLR slide: 0x498C000
```

### Runtime address mapping

| Component | Address |
|---|---|
| Executable image base | `0x10498C000` |
| ASLR slide | `0x498C000` |
| Singleton symbol, unslid | `0x100732FC0` |
| Singleton symbol, runtime | `0x1050BEFC0` |
| Cockpit object | `0x10AA81500` |
| Cockpit input-region array | `0x10AA84270` |
| Known left-arrow hitbox | `0x10AA84608` |

LLDB confirmed the singleton pointer:

```lldb
memory read --size 8 --count 1 --format x 0x1050BEFC0
```

Output:

```text
0x1050befc0: 0x000000010aa81500
```

The symbol was independently verified with:

```lldb
image lookup --symbol "Singleton<Cockpit>::objectPtr"
```

The symbol's unslid address remains `0x100732FC0`.

**Address safety:** These runtime addresses belong to PID 29949. Recalculate them after relaunching the application.

---

## 4. Input-Region Investigation

The known Cockpit input-region array begins at:

```text
Cockpit + 0x2D70
```

Each record has a stride of 20 bytes:

```text
Entry address = Cockpit + 0x2D70 + index * 0x14
```

Its first eight bytes contain:

| Offset | Type | Meaning |
|---|---|---|
| `+0x00` | int16 | X |
| `+0x02` | int16 | Y |
| `+0x04` | uint16 | Width |
| `+0x06` | uint16 | Height |

### Previously confirmed navigation arrow

Entry 46 is the left navigation arrow's input region.

```text
Entry: 46
Offset: Cockpit + 0x3108
Rect: (1809, 109, 102, 76)
```

Its hitbox was previously moved 600 game-coordinate units left by changing X from `1809` to `1209`.

The change was confirmed through actual touch interaction.

### Nearby region records

During this session, entries 44–47 were read directly.

| Entry | X | Y | Width | Height |
|---|---:|---:|---:|---:|
| 44 | 1659 | 444 | 83 | 83 |
| 45 | 1840 | 189 | 371 | 357 |
| 46 | 1809 | 109 | 102 | 76 |
| 47 | 2141 | 109 | 102 | 76 |

Entry 47 remains a plausible right-arrow companion, but has not been verified through independent touch interaction.

### Wider region scan

The first 128 entries were scanned using LLDB Python, with a filter for rectangles near the upper portion of the coordinate space.

The scan found multiple sets of rectangles with similar dimensions.

Selected results:

| Entry | X | Y | Width | Height |
|---|---:|---:|---:|---:|
| 93 | 474 | 86 | 102 | 76 |
| 94 | 1817 | 86 | 102 | 76 |
| 96 | 486 | 162 | 224 | 51 |
| 97 | 710 | 162 | 313 | 51 |
| 98 | 1023 | 162 | 224 | 51 |
| 99 | 1247 | 162 | 313 | 51 |
| 100 | 1561 | 162 | 313 | 51 |
| 102 | 1415 | 73 | 102 | 76 |
| 103 | 2156 | 73 | 102 | 76 |

These records suggest multiple groups of UI elements, including small controls and wider menu options.

However, none has been confirmed as the hamburger icon.

**Research conclusion:** Searching region rectangles by coordinates and dimensions alone is insufficient because the game contains many different UI states and controls.

A more focused strategy is needed.

---

## 5. Discovering the Menu State Transition

Previous research identified two Cockpit fields associated with menu state:

```text
Cockpit + 0x11B0
Cockpit + 0x11B4
```

For PID 29949:

```text
Cockpit + 0x11B0 = 0x10AA826B0
Cockpit + 0x11B4 = 0x10AA826B4
```

The fields were measured across a complete open-and-close interaction.

### Experimental results

| UI state | `+0x11B0` | `+0x11B4` | Hamburger |
|---|---:|---:|---|
| Menu closed | 0 | 0 | Visible |
| Menu open | 0 | 256 | Hidden |
| Menu closed again | 0 | 0 | Visible |

The transition was verified by direct LLDB memory reads.

**Confirmed finding:** `Cockpit + 0x11B4` changes reproducibly from `0` to `256` when the hamburger menu opens and returns to `0` when it closes.

This provides a useful indicator of menu state.

**Not confirmed:** Whether this field directly controls the hamburger's visibility.

---

## 6. Catching the Menu-Opening Transition

With the menu closed, an LLDB write watchpoint was installed:

```lldb
watchpoint set expression -w write -s 4 -- 0x10AA826B4
```

The application was resumed, and the hamburger was tapped.

LLDB stopped with:

```text
Watchpoint 1 hit:

old value: 0
new value: 256
```

The stopping location was:

```text
0x104D09C54
MH Unite`___lldb_unnamed_symbol13386 + 164
```

### Register values

```text
x19 = 0x10AA81500
x20 = 0x1
```

The value in `x19` matches the independently confirmed Cockpit object.

### State bytes

Reading four bytes at the watched address returned:

```text
00 01 00 00
```

In little-endian representation, this corresponds to:

```text
0x00000100 = 256
```

---

## 7. Instruction Responsible for the State Change

Disassembly around the watchpoint revealed:

```asm
0x104D09C48: mov  w8, #0x11b5
0x104D09C4C: add  x8, x19, x8
0x104D09C50: strb w20, [x8]
0x104D09C54: strh wzr, [x19, #0x11b6]
```

The critical instruction is:

```asm
strb w20, [x8]
```

At this point:

```text
x19 = Cockpit object
x8  = Cockpit + 0x11B5
w20 = 1
```

Therefore, the instruction writes `1` to the second byte of the four-byte field starting at `Cockpit + 0x11B4`.

This explains the observed transition:

```text
00 00 00 00
    ↓
00 01 00 00
```

The following instruction clears the upper two bytes.

### Confirmed interpretation

The function updates menu-related state inside the Cockpit object.

The watchpoint identifies an actual code path executed during the observed hamburger-opening transition.

It does not, by itself, identify the hamburger's input region.

---

## 8. Menu-Opening Routine

The function containing the state-changing instruction begins at:

```text
Runtime: 0x104D09BB0
Unslid:  0x10037DBB0
```

LLDB identifies it as:

```text
___lldb_unnamed_symbol13386
```

The beginning of the routine includes:

```asm
ldr  w9, [x8, #0x8]
cmp  w9, #0xc
b.eq 0x104D09C88
```

The function checks whether another object's state equals 12.

If that condition is not met, the observed path includes:

```asm
mov  w20, #1
mov  w10, #12
strb w20, [x9, #0x10]
str  w10, [x8, #0x8]
str  wzr, [x19, #0x11b0]
```

It therefore:

1. Updates a separate object's state to 12.
2. Writes a one-byte flag to another object.
3. Resets `Cockpit + 0x11B0` to zero.
4. Performs additional state updates and a function call.
5. Writes the value `1` to `Cockpit + 0x11B5`.

The routine appears strongly associated with entering the Cockpit menu.

The exact meaning of state 12 is not fully established.

---

## 9. Additional State-Transition Operations

Further disassembly revealed:

```asm
mov  w8, #0x11b4
add  x8, x19, x8
strb w9, [x19, #0x646]
ldrb w8, [x8]
strh w8, [x19, #0x644]
```

This reads the byte at `Cockpit + 0x11B4` and stores its value as a 16-bit field at `Cockpit + 0x644`.

Other operations include:

```asm
strb w8, [x19, #0x647]
str  w8, [x19, #0x628]
```

A helper function is then called:

```asm
bl 0x104D309A0
```

After that call, the state byte at `Cockpit + 0x11B5` is written.

### Helper function

```text
Runtime: 0x104D309A0
Unslid:  0x1003A49A0
Symbol:  ___lldb_unnamed_symbol13564
```

The helper calls another function with an argument of `21` and conditionally clears bytes in an object reached through a pointer at offset `0x12E8`.

It also examines a state or count at offset `0x15A4`.

Observed conditional operations include:

| Condition | Operation |
|---|---|
| Value ≥ 1 | Clear byte at pointer `+0x6C` |
| Value ≥ 2 | Clear byte at pointer `+0xDC` |
| Value ≥ 3 | Clear byte at pointer `+0x14C` |
| Value ≥ 12 | Clear byte at pointer `+0x53C` |

This is consistent with cleanup or reset behavior involving several UI-related elements.

**Unconfirmed:** The actual identities and roles of those elements.

The helper has not been shown to initialize or reposition the hamburger icon.

---

## 10. Menu-Opening Call Stack

At the state-change watchpoint, the backtrace was:

```text
#0  0x104D09C54  ___lldb_unnamed_symbol13386 + 164
#1  0x104BBAD78  ___lldb_unnamed_symbol6961 + 148
#2  0x104BBD2E4  ___lldb_unnamed_symbol6976 + 804
#3  0x104CC7E5C  ___lldb_unnamed_symbol12305 + 100
#4  0x104CDC858  ___lldb_unnamed_symbol12505 + 288
#5  0x104CDF424  ___lldb_unnamed_symbol12639 + 136
#6  0x104CDF0A4  ___lldb_unnamed_symbol12629 + 12
#7  libsystem_pthread.dylib`_pthread_start
```

The direct caller's relevant instructions included:

```asm
0x104BBAD68: bl   0x104CDD2B4
0x104BBAD6C: tbnz w0, #0, 0x104BBAD78
0x104BBAD70: ldr  x0, [x20]
0x104BBAD74: bl   0x104BAA17C
```

The called function at `0x104BAA17C` was also inspected.

It contains a jump-table dispatch over values up to `0x3F`, suggesting a large state-handling function with up to 64 switch cases.

This appears to be part of a higher-level application state machine.

**Important limitation:** The observed call stack establishes an execution path to the menu-state routine, not a definitive chain from the hamburger touch rectangle to that routine.

Further investigation of general state-machine dispatch was intentionally deferred.

---

## 11. End-of-Session Debugger State

After recording the state transition:

```lldb
watchpoint disable 1
continue
```

The menu was closed on the iPad, restoring the hamburger icon.

LLDB was then interrupted:

```lldb
process interrupt
```

The last reported debugger state was:

```text
Process: 29949
State: stopped
Stop reason: SIGSTOP
Thread: main thread
```

The current UI was intended to be the hamburger-visible state.

A final memory read of `Cockpit + 0x11B0` and `+0x11B4` had been proposed but had not yet been performed.

The previously observed closed-state values were:

```text
+0x11B0 = 0
+0x11B4 = 0
```

No memory modifications were made to relocate or alter the hamburger icon during Phase 7.

---

## 12. Confirmed Findings

Phase 7 established the following:

1. The hamburger icon is visible when the menu is closed.
2. Opening the menu hides the hamburger visually.
3. The menu uses a separate close button near the lower-right screen corner.
4. Closing the menu restores the hamburger to its original position.
5. `Cockpit + 0x11B4` changes from `0` to `256` on menu opening.
6. That field returns to zero when the menu is closed.
7. A watchpoint caught the menu-opening state change in native ARM64 code.
8. The modifying function operates on the confirmed Cockpit singleton object.
9. The state change is performed using individual byte writes.
10. The menu-opening function also updates a separate application's state to 12.
11. The function calls another routine that performs conditional state cleanup or reset operations.
12. The hamburger's rendering function and hitbox remain unidentified.

---

## 13. Next Research Direction — Hamburger Rendering

The next investigation should focus on drawing operations that occur when the hamburger is visible and are absent, or behave differently, when the Cockpit menu is open.

We have an existing graphics helper from Phase 4:

```text
Unslid: 0x100378D6C
Runtime in PID 29949: 0x104D04D6C
```

Earlier experiments demonstrated that modifying a graphics-helper coordinate could move the circular background of the left navigation arrow.

This confirms that the helper participates in rendering UI components, although it has not been demonstrated to draw the hamburger icon.

### Proposed investigation

1. Verify the current menu-closed state.
2. Observe relevant draw calls while the hamburger is visible.
3. Compare them against the menu-open state.
4. Identify draw operations associated with the hamburger's background and glyph.
5. Determine the source of the icon's horizontal coordinate.
6. Trace the hamburger's touch-input handling separately.
7. Test temporary, reversible modifications to confirm both paths.

Avoid assuming that the hamburger is necessarily rendered by the same function as the menu navigation arrows.

### Research priority

Prefer narrowly targeted runtime evidence over broad disassembly of the game's state machine.

A meaningful next result would be identifying a specific draw call that disappears or changes when the hamburger is hidden.

---

## 14. Remaining Questions

- Which function renders the persistent hamburger icon?
- Does the hamburger use one draw call or multiple draw calls?
- Does it use the same graphics helper as the Cockpit navigation arrows?
- Which input region handles the hamburger's tap?
- Does its hitbox belong to the known Cockpit input-region array?
- Does menu state `0x100` directly control hamburger visibility?
- What determines the icon's horizontal placement?
- Can the icon's rendering and input coordinates be patched independently?
- What is the smallest reliable persistent modification that achieves the desired iPad placement?

---

## 15. Phase Conclusion

Phase 7 identified a reproducible Cockpit menu-state transition and the exact code responsible for writing its observed state value.

The confirmed field at `Cockpit + 0x11B4` distinguishes the tested hamburger-visible and menu-open states.

This provides a useful reference for comparing UI behavior.

**The primary hamburger relocation objective remains incomplete.**

The next research phase should prioritize isolating the persistent hamburger icon's rendering operation and functional touch region, rather than continuing general menu-state disassembly.

---

*End of Phase 7 research.*