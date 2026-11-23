# Phase 6 — Cockpit Initialization and Runtime Hitbox Verification

**Project:** FUPatch4iPad  
**Game:** Monster Hunter Freedom Unite iOS  
**Version:** 1.00.11  
**Device:** iPad Air 11-inch (M2), `iPad14,8`  
**iPadOS:** 18.7.3  
**Status:** Runtime hitbox relocation confirmed; initialization writer not yet identified

**Suggested filename:** `docs/research-phase6-cockpit-initialization.md`

---

## 1. Research Objective

Identify where MH Unite initializes the Cockpit UI hitboxes, with the eventual goal of relocating the persistent hamburger menu icon and its associated touch region for the iPad display.

Previous research established:

- The Cockpit singleton and its layout renderer.
- The menu layout resolver and relevant descriptor entries.
- The touch-input conversion pipeline.
- The format of input-region rectangles.
- The left navigation arrow's hitbox at `Cockpit + 0x3108`.
- Independent runtime modifications of menu visuals and touch regions.

Phase 6 focuses on observing Cockpit initialization from application startup instead of attaching to an already initialized process.

## 2. Existing Baseline

The following addresses were established in the earlier debugging session.

| Component | Unslid address or offset |
|---|---|
| `Singleton<Cockpit>::objectPtr` | `0x100732FC0` |
| Cockpit dispatcher | `0x10037EDBC` |
| Menu renderer | `0x1003A5904` |
| Menu layout resolver | `0x10039DAD4` |
| Point-in-rectangle helper | `0x100460BD0` |
| Input-region array | `Cockpit + 0x2D70` |
| Left-arrow rectangle | `Cockpit + 0x3108` |

The rectangle is input-region entry 46:

```text
0x2D70 + (46 × 0x14) = 0x3108
```

Each input-region entry occupies 20 bytes. Its first eight bytes describe a rectangle:

| Offset | Type | Meaning |
|---|---|---|
| `+0x00` | int16 | X |
| `+0x02` | int16 | Y |
| `+0x04` | uint16 | Width |
| `+0x06` | uint16 | Height |

The remaining bytes contain region metadata and flags that have not been completely characterized.

## 3. Launching the Game Before Initialization

### 3.1 Initial LLDB launch failure

The existing LLDB session was attached to PID `29337`.

Attempting:

```lldb
process launch --stop-at-entry
```

detached the existing process but failed with:

```text
error: the platform is not currently connected
```

Subsequent inspection confirmed:

```text
Platform: remote-ios
Connected: no
```

This established that the original LLDB session could not directly relaunch the application in its disconnected state.

### 3.2 Confirming the device connection

From macOS Terminal:

```bash
xcrun devicectl list devices
```

The iPad appeared as connected.

Listing installed applications:

```bash
xcrun devicectl device info apps \
  --device EB90DDE0-50FB-5593-A792-E211E636A9EC
```

Confirmed:

```text
Name:              MH Unite
Bundle identifier: jp.co.capcom.mhp2g
Version:           1.00.11
Bundle version:    1.00.11
```

**Tooling note:** `devicectl device info apps --filter` expects an NSPredicate expression. Passing plain text such as `"MH Unite"` caused an Objective-C exception, so the application list was obtained without a filter.

### 3.3 Successful suspended launch

The following command successfully started the installed game in a suspended state:

```bash
xcrun devicectl device process launch \
  --device EB90DDE0-50FB-5593-A792-E211E636A9EC \
  --start-stopped \
  jp.co.capcom.mhp2g
```

Output:

```text
Launched application with jp.co.capcom.mhp2g bundle identifier.
```

The iPad displayed a black screen while the application was suspended.

This was expected because normal initialization had not resumed.

### 3.4 Attaching LLDB

A new LLDB session was created:

```bash
xcrun lldb
```

The device was selected:

```lldb
device select EB90DDE0-50FB-5593-A792-E211E636A9EC
```

An initial attach using the bundle identifier as a process name failed:

```lldb
device process attach -n jp.co.capcom.mhp2g
```

The process was subsequently located using the device process list:

```text
29459  .../MH Unite.app/MH Unite
```

Attaching by PID succeeded:

```lldb
device process attach -p 29459
```

LLDB stopped at:

```text
dyld`_dyld_start
```

This confirmed that debugging began before the application's normal initialization.

**Important:** Prefer attaching using the actual PID or executable name. A bundle identifier is not necessarily a valid process name for LLDB's `-n` argument.

## 4. New Process Address Mapping

The new process was PID `29459`.

Running:

```lldb
image list -o -f
```

Returned the executable's slide:

```text
0x0000000002338000
```

Therefore:

```text
ASLR slide = 0x2338000
```

Runtime addresses are derived from the unslid addresses:

```text
Runtime address = Unslid address + ASLR slide
```

For the Cockpit singleton:

```text
0x100732FC0 + 0x2338000 = 0x102A6AFC0
```

| Property | Value |
|---|---|
| Executable slide | `0x2338000` |
| Singleton slot | `0x102A6AFC0` |
| Current Cockpit object | `0x10842D500` |
| Left-arrow hitbox | `0x108430608` |

These addresses are specific to PID `29459`. Recalculate them after another launch.

## 5. Catching Cockpit Singleton Initialization

An eight-byte write watchpoint was installed while the application remained stopped at its entry point:

```lldb
watchpoint set expression -w write -s 8 -- 0x102A6AFC0
```

Watchpoint 1 was created successfully.

Its initial reported value was zero.

After:

```lldb
continue
```

the debugger stopped:

```text
Watchpoint 1 hit:

old value: 0
new value: 4433564928
```

The decimal value corresponds to:

```text
0x10842D500
```

This is the Cockpit singleton's object address.

The stopping instruction was:

```text
0x1026A104C
MH Unite`___lldb_unnamed_symbol13134 + 28
```

Its unslid address is:

```text
0x10036904C
```

### 5.1 Call stack

The relevant stack frames were:

```text
#0  MH Unite`___lldb_unnamed_symbol13134 + 28
#1  MH Unite`___lldb_unnamed_symbol12664 + 764
#2  MH Unite`___lldb_unnamed_symbol12677 + 28
#3  dyld`findAndRunAllInitializers...
```

**Conclusion:** The Cockpit singleton pointer is assigned during a dyld-managed static initialization sequence.

This gives us a concrete starting point for locating the Cockpit constructor or initialization routine.

However, the singleton assignment alone does not prove which instruction initializes the input-region rectangles.

## 6. Watching the Left-Arrow Rectangle During Startup

The active hitbox was calculated as:

```text
Cockpit + 0x3108

0x10842D500 + 0x3108 = 0x108430608
```

At the singleton assignment stop, its rectangle contents were:

```text
X = 0
Y = 0
W = 0
H = 0
```

A second watchpoint was installed:

```lldb
watchpoint set expression -w write -s 2 -- 0x108430608
```

This monitored the hitbox's 16-bit X coordinate.

### 6.1 First watchpoint event

After continuing, watchpoint 2 stopped inside:

```text
libsystem_platform.dylib`_platform_memset
```

The caller was:

```text
MH Unite`___lldb_unnamed_symbol13134 + 1108
Runtime: 0x1026A1484
```

The watchpoint reported:

```text
old value: 0
new value: 0
```

The rectangle still contained four zeros.

**Interpretation:** This was a memory-clearing operation involving the watched address, not evidence that the final rectangle was initialized.

### 6.2 Subsequent observation

A later stop occurred at watchpoint 1, on thread 20:

```text
old value: 4433564928
new value: 4433564928
```

At that point, reading the rectangle returned:

```text
X = -437
Y = 0
W = 0
H = 0
```

This indicates the memory contents had changed since the earlier read.

The origin and meaning of `-437` remain unknown. It should not be treated as a confirmed layout offset or final coordinate.

Watchpoint 1 was disabled to focus on the rectangle.

After resuming, the game reached its normal UI, including the hamburger menu, without another reported stop from watchpoint 2.

### 6.3 Final live rectangle

After interrupting the running process, the singleton pointer still contained:

```text
0x10842D500
```

Reading the rectangle:

```lldb
memory read --size 2 --count 4 --format d 0x108430608
```

Returned:

```text
0x108430608: 1809
0x10843060a: 109
0x10843060c: 102
0x10843060e: 76
```

This matches the original left-arrow hitbox found in the earlier debugging session.

**Confirmed:** The Cockpit singleton and the `+0x3108` region mapping remain valid in the new process.

**Unresolved:** The watchpoint output did not expose the instruction that produced the final X coordinate. The reason that the write was not reported has not been established.

## 7. Independent Runtime Hitbox Relocation

To verify that the current rectangle was genuinely active, its X coordinate was modified directly.

Original rectangle:

```text
X = 1809
Y = 109
W = 102
H = 76
```

LLDB command:

```lldb
memory write --size 2 --format d 0x108430608 1209
```

Verification:

```lldb
memory read --size 2 --count 4 --format d 0x108430608
```

Returned:

```text
X = 1209
Y = 109
W = 102
H = 76
```

After resuming the game, the user tested the menu and confirmed that **the left-arrow touch region had moved 600 game-coordinate units to the left**.

This independently reproduces the successful hitbox relocation from the earlier session.

### Confirmed behavior

- The active hitbox X coordinate can be changed directly in memory.
- Moving X from `1809` to `1209` moves the functional touch region left by 600 game units.
- Y, width, and height are unchanged.
- The arrow's rendered visual position is not changed by this memory modification alone.
- The patch is runtime-only and has not been persisted to the executable.

### Restoration

To restore the original coordinate in PID `29459`:

```lldb
process interrupt
memory write --size 2 --format d 0x108430608 1809
```

The address must be recalculated if the process changes.

## 8. Confirmed Findings and Remaining Questions

### Confirmed

1. MH Unite can be launched suspended using `devicectl --start-stopped`.
2. LLDB can attach to the suspended application using its PID.
3. The Cockpit singleton pointer is assigned during dyld static initialization.
4. The singleton object can be located from `Singleton<Cockpit>::objectPtr`.
5. The left-arrow input rectangle exists at `Cockpit + 0x3108`.
6. Its normal values are `(1809, 109, 102, 76)` in the tested UI state.
7. Changing X to `1209` successfully relocates the touch region.
8. The rendered arrow and its touch rectangle can be modified independently.

### Not yet confirmed

1. Which instruction writes the final X coordinate `1809`.
2. Why watchpoint 2 did not report the later observed coordinate changes.
3. Whether `-437` represents meaningful initialization data or transient memory contents.
4. Whether the rectangle is initialized directly from a layout table, calculated dynamically, or copied from another structure.
5. The input rectangle and rendering path specifically belonging to the persistent hamburger icon.
6. The appropriate persistent patch for simultaneously relocating the hamburger visuals and touch area.

## 9. Recommended Next Research

The next experiment should prioritize locating the actual initialization writer rather than revisiting the previously confirmed hit-testing pipeline.

Suggested direction:

1. Preserve the current runtime findings.
2. On a future suspended launch, focus on the hitbox X coordinate and its neighboring fields.
3. Consider monitoring a wider region or investigating writes that may bypass the narrow watchpoint's observed behavior.
4. Inspect `___lldb_unnamed_symbol13134` and its relevant initialization calls, now that the singleton creation path has been captured.
5. Once the rectangle initialization is identified, determine its relationship to the layout descriptors and any persistent patch opportunities.

The eventual objective remains relocating the **persistent hamburger menu icon to the iPad's right edge**, preserving its original size, vertical position, partial clipping, and correct touch area.

Moving the left navigation arrow is an experimental stepping stone, not the final patch.

## 10. Safety and Reproducibility

- Preserve the immutable baseline IPA: `E:\Games\MHFU-iPad-baseline.ipa`.
- Do not modify game save data during experiments.
- Treat direct LLDB memory writes as temporary.
- Recalculate addresses after ASLR changes.
- Preserve existing research documents.
- Avoid assuming that a watchpoint's displayed `new value` proves an actual write unless execution stopped because of that event.
- Validate both visual and input behavior separately.

---

**Phase 6 conclusion:** We have reproduced and verified left-arrow hitbox relocation in a second process, and we have identified the static initialization path that assigns the Cockpit singleton. The remaining challenge is identifying the code that populates the active input-region rectangles and ultimately applying the findings to the persistent hamburger icon.