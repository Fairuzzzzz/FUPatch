# FUPatch4iPad — Project Objective & Session Handoff

**Project:** FUPatch4iPad  
**Target game:** Monster Hunter Freedom Unite (MH Unite), iOS v1.00.11  
**Target device:** iPad Air 11-inch (M2), iPadOS 18.7.3  
**Project status:** Active reverse engineering; input hitbox manipulation verified  
**Primary objective:** Correct the persistent hamburger menu icon's horizontal placement on iPad

---

## 1. Primary Objective

The goal of FUPatch4iPad is to modify the iOS version of **Monster Hunter Freedom Unite (v1.00.11)** so that its persistent, partially clipped hamburger menu icon appears at the appropriate position along the **right edge of the iPad display**.

The target is a precise UI-position correction, not a general UI redesign.

### Desired behavior

The hamburger menu icon must:

1. Move horizontally to the intended location at the right edge of the iPad display.
2. Preserve its original visual size.
3. Preserve its original vertical position.
4. Preserve its original partially clipped appearance.
5. Remain visually consistent with the original game.
6. Retain a correctly aligned, functional touch area.
7. Work reliably without requiring manual LLDB commands on each launch.

**The intended final result is a persistent modification to the game, not a temporary runtime memory edit.**

The current work is investigating the original executable's rendering and input systems to identify a reliable patch point.

### Important distinction

The hamburger icon is the final target.

The menu's left navigation arrow, which has been used extensively during experiments, is a **research reference object**.

Successfully moving the left arrow does not mean the project's main objective has been completed.

---

## 2. Project Environment

### Target application

| Property | Value |
|---|---|
| Game | Monster Hunter Freedom Unite |
| iOS application name | MH Unite |
| Bundle identifier | `jp.co.capcom.mhp2g` |
| Version | `1.00.11` |
| Architecture | ARM64 |
| Platform | iOS |
| Device | iPad Air 11-inch (M2), `iPad14,8` |
| OS version | iPadOS 18.7.3 |

### Development environment

**Windows repository:**

```text
E:\Archive\FUPatch4iPad
```

**Immutable baseline IPA:**

```text
E:\Games\MHFU-iPad-baseline.ipa
```

**macOS tools:**

- Xcode device services
- `xcrun devicectl`
- LLDB
- ARM64 disassembly and runtime memory inspection

### Device identifier used during testing

```text
EB90DDE0-50FB-5593-A792-E211E636A9EC
```

This is the device identifier observed during the documented debugging session. Reconfirm it when necessary.

### Important safety constraints

- Never modify the immutable baseline IPA.
- Do not overwrite or deliberately alter game save data.
- Keep experiments reversible.
- Use working copies for binary modifications.
- Do not reinstall the application unnecessarily.
- Record confirmed findings before attempting major changes.
- Do not confuse temporary runtime modifications with persistent patches.

---

## 3. Research Documentation

The project uses phase-specific research files.

| Document | Purpose |
|---|---|
| `docs/research.md` | Main research record |
| `docs/research-phase4.md` | Existing Phase 4 research |
| `docs/research-phase4-menu-layout.md` | Menu layout and rendering investigation |
| `docs/research-phase5-input-hitboxes.md` | Touch-input pipeline and region hitboxes |
| `docs/research-phase6-cockpit-initialization.md` | Startup initialization and hitbox verification |
| `docs/PROJECT_HANDOFF.md` | Project objective, continuity, and restart instructions |

**Documentation status:** Some later-phase documents were drafted during ChatGPT conversations. Their presence in the repository should be verified before relying on their filenames.

Do not overwrite existing research files merely because a new chat proposes a similar document.

---

## 4. Technical Architecture Discovered

The game's Cockpit subsystem manages relevant UI rendering and input regions.

### Cockpit singleton

LLDB resolved the symbol:

```text
Singleton<Cockpit>::objectPtr
```

Unslid address:

```text
0x100732FC0
```

For each process:

```text
Runtime singleton address = 0x100732FC0 + ASLR slide
```

The singleton points to the live Cockpit object.

Cockpit object addresses are process-specific and must be read rather than assumed.

### Important functions

All addresses in this table are **unslid Mach-O addresses**.

| Function | Address | Role |
|---|---|---|
| Cockpit dispatcher | `0x10037EDBC` | Dispatches relevant Cockpit rendering |
| Menu renderer | `0x1003A5904` | Draws the investigated menu elements |
| Layout resolver | `0x10039DAD4` | Converts layout descriptors into positions |
| Graphics helper | `0x100378D6C` | Lower-level graphics rendering |
| Native touch handler | `0x10046328C` | Receives UIKit touch events |
| Input manager | `0x100460A24` | Processes touch coordinates |
| Point-in-rectangle helper | `0x100460BD0` | Tests touches against rectangles |
| Region processor | `0x100007720` | Processes input-region entries |

The region processor's runtime address in the earlier debugging session was `0x100F7F720`.

Do not mistake this runtime address for its unslid address.

### Layout information

The menu renderer calls the layout resolver for entry 98.

The investigated layout record contained:

```text
Base index: 99
X offset:   -266
Y offset:   +70
```

The resolver produced approximately:

```text
X = 1821
Y = 112
```

Changing the resolved X coordinate from `1821` to `1221` moved the menu's visuals left by 600 game-coordinate units.

However, the input hitboxes remained at their original positions.

**Conclusion:** Rendering coordinates and touch-region coordinates are independently controlled.

---

## 5. Confirmed Input-Region Structure

The Cockpit contains an array of input regions beginning at:

```text
Cockpit + 0x2D70
```

Each region occupies:

```text
0x14 bytes (20 bytes)
```

The first eight bytes contain:

```text
+0x00  int16   X
+0x02  int16   Y
+0x04  uint16  Width
+0x06  uint16  Height
```

The remaining fields contain additional region state and flags.

### Confirmed left navigation arrow

The left navigation arrow corresponds to region entry 46:

```text
0x2D70 + 46 * 0x14 = 0x3108
```

Thus:

```text
Left-arrow hitbox = Cockpit + 0x3108
```

Its original rectangle in the tested menu state is:

```text
X      = 1809
Y      = 109
Width  = 102
Height = 76
```

### Experimentally verified modification

Changing:

```text
X = 1809
```

to:

```text
X = 1209
```

moves the arrow's functional touch region **600 game-coordinate units left**.

This was confirmed by actual touch interaction in two separate debugging sessions.

The rendered arrow does not automatically follow the hitbox.

This is one of the project's strongest experimental findings.

---

## 6. Rendering Experiments

Two different visual modifications were investigated.

### Graphics-helper modification

A lower-level draw-coordinate modification moved only the circular background of the left navigation arrow.

It did not move the glyph or touch region.

Therefore, this graphics helper alone is not sufficient to relocate a complete interactive UI element.

### Menu-renderer layout modification

An LLDB breakpoint in the menu renderer at unslid:

```text
0x1003A51C0
```

modified the resolved layout coordinate on the stack.

Original:

```text
X = 1821
```

Modified:

```text
X = 1221
```

This moved the investigated menu visuals 600 game-coordinate units left.

The corresponding touch regions did not move.

**Conclusion:** A complete patch will likely require coordinating the visual and input paths, or identifying a higher-level source shared by both.

No shared source has yet been confirmed.

---

## 7. Touch-Input Pipeline

The input investigation established the following broad path:

```text
UIKit touch events
    |
    v
Native touch handler
    |
    v
locationInView:
    |
    v
Game input manager
    |
    v
Coordinate conversion
    |
    v
Touch slots
    |
    v
Input-region processor
    |
    v
Point-in-rectangle comparison
    |
    v
UI interaction
```

The input manager was observed multiplying UIKit touch positions by a scale factor of `2.0`.

The game maintains up to five touch slots, each with a stride of `0x60`.

The point-in-rectangle routine compares touch coordinates against integer rectangle boundaries.

A confirmed left-arrow rectangle used:

```text
Left   = 1809
Top    = 109
Right  = 1911
Bottom = 185
```

Equivalent to:

```text
X = 1809
Y = 109
W = 102
H = 76
```

This matches the Cockpit input-region record.

---

## 8. Startup Debugging Breakthrough

A previous LLDB session could not relaunch the app because its `remote-ios` platform was disconnected.

A working approach was discovered using `devicectl`.

### Launch suspended

From macOS Terminal:

```bash
xcrun devicectl device process launch \
  --device EB90DDE0-50FB-5593-A792-E211E636A9EC \
  --start-stopped \
  jp.co.capcom.mhp2g
```

The app launches in a suspended state. A black screen is expected.

### Attach LLDB

```bash
xcrun lldb
```

Inside LLDB:

```lldb
device select EB90DDE0-50FB-5593-A792-E211E636A9EC
device process attach -p <PID>
```

Obtain the PID from:

```bash
xcrun devicectl device info processes \
  --device EB90DDE0-50FB-5593-A792-E211E636A9EC
```

Attaching to the suspended game stopped at:

```text
dyld`_dyld_start
```

This allowed watchpoints to be installed before normal initialization.

### Confirmed process

During the Phase 6 session:

```text
PID:         29459
ASLR slide:  0x2338000
```

The runtime singleton address was:

```text
0x102A6AFC0
```

The singleton was initially zero.

An eight-byte write watchpoint caught its first assignment:

```text
Old: 0x0
New: 0x10842D500
```

The assignment occurred during dyld-managed static initialization.

The stopped code was:

```text
Runtime: 0x1026A104C
Unslid:  0x10036904C
```

Function:

```text
MH Unite`___lldb_unnamed_symbol13134
```

This provides a starting point for investigating Cockpit construction.

---

## 9. Hitbox Initialization Investigation

After the singleton was assigned, the hitbox at:

```text
Cockpit + 0x3108
```

was initially zeroed.

A write watchpoint was installed on its 16-bit X coordinate.

The first detected write occurred inside:

```text
libsystem_platform.dylib`_platform_memset
```

Called by:

```text
MH Unite`___lldb_unnamed_symbol13134 + 1108
```

Later, memory was observed containing:

```text
X = -437
Y = 0
W = 0
H = 0
```

The origin of this intermediate value is unknown.

After normal initialization, the rectangle contained:

```text
X = 1809
Y = 109
W = 102
H = 76
```

The watchpoint did not produce a reported stop for the transition to the final values.

**Important unresolved issue:** The exact instruction initializing the final rectangle has not been identified.

Do not assume the value `-437` is a confirmed layout parameter.

---

## 10. Latest Successful Experiment

In process PID `29459`:

```text
Cockpit singleton slot: 0x102A6AFC0
Cockpit object:         0x10842D500
Left-arrow hitbox:      0x108430608
```

The following LLDB command was executed:

```lldb
memory write --size 2 --format d 0x108430608 1209
```

The rectangle was verified as:

```text
1209, 109, 102, 76
```

The game was resumed.

The user tested the menu and confirmed that the touch area had moved 600 units left.

**This is the latest experimentally confirmed result.**

A subsequent recommendation was made to restore X to `1809`, but execution of that restoration has not been confirmed.

### Current runtime state

The last confirmed running state of PID `29459` has:

```text
Left-arrow X = 1209
```

The game may have since been restarted or the process may have terminated.

Never assume this address or process remains valid in a later session.

---

## 11. What Has Not Been Solved

Despite the progress, the primary objective is incomplete.

The following remain unresolved:

- The exact rendering path for the persistent hamburger icon.
- The hamburger icon's associated input-region entry.
- The correct final horizontal coordinate for the hamburger on the target iPad.
- The code or data responsible for initializing the relevant hitbox.
- A reliable method to relocate the hamburger's visuals and interaction together.
- A persistent binary patch that works without LLDB.
- Final testing across relevant menus, gameplay states, and application restarts.

The left-arrow investigation is valuable because it established how the game handles UI geometry and input.

However, the final patch should be scoped to the hamburger icon rather than shifting unrelated menu elements.

---

## 12. Recommended Next Steps

### Priority 1 — Locate the actual hamburger element

Stop treating the left navigation arrow as the final target.

Use the confirmed Cockpit rendering and input architecture to identify the persistent hamburger icon specifically.

Determine:

- Which draw calls render the hamburger background and glyph.
- Whether the icon shares a layout descriptor with other controls.
- Which input-region entry corresponds to its touch target.
- Whether the hamburger exists in multiple Cockpit modes or uses different paths.

### Priority 2 — Correlate visual and touch positions

Once the hamburger's rendering and input references are identified, experimentally move each independently.

Verify the results through direct observation and touch interaction.

Avoid assuming that moving one also moves the other.

### Priority 3 — Find persistent patch locations

Investigate whether the relevant coordinates originate from:

- Static layout descriptors.
- Runtime initialization routines.
- Device-dependent calculations.
- Shared layout logic.
- Separate rendering and input constants.

Prefer the smallest reliable modification that preserves the behavior of unrelated UI elements.

### Priority 4 — Validate the final patch

The completed patch should be tested for:

- Correct placement along the right edge.
- Original icon size.
- Original Y coordinate.
- Intended partial clipping.
- Correct touch interaction.
- Consistency between menu and gameplay states.
- Persistence after application restart.

Test against a working copy of the IPA while keeping the baseline untouched.

---

## 13. Instructions for Future ChatGPT or Codex Sessions

When continuing this project:

1. Read this handoff document first, followed by the phase-specific research documents.
2. Preserve the exact primary objective.
3. Distinguish confirmed experimental results from hypotheses.
4. Do not repeat already validated hitbox experiments unless necessary to verify a new environment.
5. Do not confuse the left navigation arrow with the hamburger icon.
6. Treat ASLR-adjusted addresses as process-specific.
7. Prefer short, sequential LLDB commands and inspect output before issuing further commands.
8. Avoid lengthy unrelated disassembly or speculative reverse engineering.
9. Preserve the baseline IPA and existing research files.
10. Document meaningful discoveries as research milestones.

### Important project preference

Work incrementally.

A good debugging step should answer one specific question, provide evidence, and inform the next step.

Avoid issuing long sequences of speculative LLDB commands without checking intermediate results.

The goal is a reproducible, maintainable patch—not merely a working one-off debugging trick.

---

## 14. Suggested Prompt for Resuming in a New Chat

I'm continuing the FUPatch4iPad project.

Read `docs/PROJECT_HANDOFF.md` and the relevant research-phase documents before proposing the next debugging step.

Our objective is to relocate the persistent, partially clipped hamburger menu icon in Monster Hunter Freedom Unite iOS v1.00.11 to the right edge of an iPad Air M2 display, preserving its size, vertical position, clipping, and functional touch area.

We have successfully reverse engineered the Cockpit singleton, menu layout resolver, touch-region array, and left navigation arrow hitbox. Both visual movement and touch-region movement have been verified separately.

The left arrow is only a research reference. The hamburger icon is the actual target.

We also discovered how to launch the game suspended with `devicectl --start-stopped` and attach LLDB before initialization.

Please continue from the documented findings rather than restarting the investigation. Use one or two targeted LLDB commands at a time, distinguish verified facts from hypotheses, and preserve the immutable baseline IPA.

Start by determining the most efficient next step toward identifying the hamburger icon's own rendering and input region.

---

## 15. Project Success Criteria

The project can be considered successful when:

- The hamburger icon appears at the intended right-edge position on the target iPad.
- Its original size and vertical placement are preserved.
- Its partial clipping is preserved.
- Its touch region follows the relocated icon.
- Other UI elements continue functioning normally.
- The modification survives application restarts.
- The result can be reproduced from documented patch steps.
- The original baseline IPA and save data remain protected.

**Current status: Research in progress. The final hamburger patch has not yet been implemented.**

---

*End of project handoff.*