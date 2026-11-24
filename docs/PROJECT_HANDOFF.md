# FUPatch4iPad — Project Handoff

**Project:** FUPatch4iPad  
**Game:** Monster Hunter Freedom Unite (MH Unite), iOS 1.00.11  
**Target:** iPad Air 11-inch (M2), iPadOS 18.7.3  
**Status:** Active reverse engineering  
**Last reviewed:** November 24, 2026

---

## 1. Primary Objective

Relocate the persistent hamburger menu icon in Monster Hunter Freedom Unite to the appropriate position along the right edge of the iPad display.

The modification must:

1. Preserve the icon's original size.
2. Preserve its vertical position.
3. Preserve its partially clipped appearance.
4. Keep the functional touch region aligned with the icon.
5. Avoid altering unrelated menu controls.
6. Persist across application launches without LLDB intervention.

The final deliverable is a reproducible patch to a working copy of the iOS application.

**The primary objective has not yet been completed.**

## 2. Project Environment

| Property | Value |
|---|---|
| Repository | `E:\Archive\FUPatch4iPad` |
| Immutable IPA | `E:\Games\MHFU-iPad-baseline.ipa` |
| Bundle identifier | `jp.co.capcom.mhp2g` |
| Architecture | ARM64 |
| Mach-O UUID | `58cc55c760ca3196b5d20c2aeb64b32b` |
| Device | `iPad14,8` |
| Debugging | Xcode, LLDB, CoreDevice |
| Offline analysis | REA 6.10.1, Ghidra 12.2 |

The executable SHA-256 recorded in the current research is:

`25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`

**Safety constraints:** Preserve the baseline IPA and save data. Use reversible runtime experiments and working copies for binary patches.

## 3. Documentation Organization

The documentation is intended to have the following structure:

```text
docs/
├── README.md
├── PROJECT_HANDOFF.md
├── research.md
├── technical-reference.md
│
├── phases/
│   ├── research-phase5.md
│   ├── research-phase6-cockpit-initialization.md
│   └── research-phase7-hamburger-state.md
│
├── archive/
│   └── Historical investigations
│
└── logs/
    └── Raw debugging and diagnostic output
```

This is the proposed organization, not confirmation that all files have already been moved.

### Document responsibilities

| Document | Responsibility |
|---|---|
| `README.md` | Documentation navigation |
| `PROJECT_HANDOFF.md` | Objective, current state, and continuation instructions |
| `research.md` | Concise, authoritative summary of current research |
| `technical-reference.md` | Detailed technical evidence, addresses, and hypotheses |
| `phases/` | Chronological investigation reports |
| `archive/` | Historical and superseded research |
| `logs/` | Raw debugging evidence |

Existing historical reports should be preserved rather than rewritten to match newer findings.

## 4. Current Research Status

### 4.1 Revised spatial texture reference

PVRTexTool 5.7.1 (Build `26.1@f61b9fab2511`, PVRTexLib v5.7.1) produced revised PNGs whose spatial layout appears correct, but colors remain abnormal. Use the unscaled images as provisional coordinate references, not replacement assets. The earlier bounds `(1804, 604, 187, 119)` and 2× vertical preview hypothesis are superseded.

| Artwork in `cock-5` | Visible bounds (X, Y, W, H) | Composition |
|---|---|---|
| Large hamburger | `(890, 593, 102, 142)` | Hamburger |
| Small hamburger | `(1544, 324, 43, 60)` | Hamburger |
| Large left navigation background | `(556, 745, 84, 84)` | Background only |
| Small left navigation button | `(1856, 4, 60, 60)` | Background plus arrow |

The larger/smaller variants are presumed iPad/iPhone assets, respectively; device selection is not verified. Hamburger size ratios are about 2.37×; navigation variants are 1.4× and differ in composition.

### 4.2 New leading atlas candidate: 527

| Index | Unslid record address | Atlas rectangle | Predicted pixels (4×) | Flags | Key |
|---:|---|---|---|---|---:|
| 527 (`0x20F`) | `0x10072F9B0` | `(221,147,27,38)` | `(884,588,108,152)` | `0x8004` | 11 |
| 564 (`0x234`) | `0x10072FB6C` | `(138,185,23,23)` | `(552,740,92,92)` | `0x8004` | 11 |

Both records use sub-index 4. Under a proposed 4× mapping, both rectangles contain the measured artwork with plausible margins. Record 564 is historically runtime-confirmed as moving the navigation background, and its archived six fields match the current Ghidra bytes. Record 527 is the strongest large-hamburger candidate, not runtime-confirmed. The 4× mapping and key 11 → `cock.tmh` → sub-index 4 → `cock-5` crosswalk are strongly suggested, not independently established.

The bounded Ghidra search of indices 527–610 with flags `0x8004` and key 11 returned only 527 and 564 for the four measured targets; no smaller variant matched. Zero direct references to record 527 were reported; dynamic indexing remains possible. Former candidates 204/205/208/209 and the old 8× fit are not priorities.

### 4.3 Static analysis progress

A standalone Ghidra 12.2 project on Intel macOS imported the baseline executable with matching SHA-256. The decompiled texture-selection and indexed-rendering functions corroborate the record structure and separate source/destination geometry. No source-coordinate scaling was observed in the inspected packing helpers. Analysis reported Objective-C analyzer errors and missing native GNU demangler components; the full warning list was truncated. See [technical-reference.md](technical-reference.md) for details.

## 5. Confirmed Cockpit and Input Findings

### Cockpit singleton

The singleton symbol is:

`Singleton<Cockpit>::objectPtr`

Unslid address:

`0x100732FC0`

Runtime address:

`0x100732FC0 + ASLR slide`

The pointer value gives the active Cockpit object.

### Input-region array

The Cockpit input-region array begins at:

`Cockpit + 0x2D70`

Records occupy 20 bytes each.

The rectangle fields are:

| Offset | Type | Meaning |
|---|---|---|
| `+0x00` | int16 | X |
| `+0x02` | int16 | Y |
| `+0x04` | uint16 | Width |
| `+0x06` | uint16 | Height |

### Confirmed left navigation arrow

Entry 46 is the left navigation arrow's hitbox:

`Cockpit + 0x3108`

Original rectangle:

`(1809, 109, 102, 76)`

Changing X from `1809` to `1209` successfully moved its functional touch area 600 game-coordinate units left.

This was verified experimentally in two separate debugging sessions.

Its graphics did not move automatically.

**The left arrow is a reference control, not the hamburger icon.**

### Rendering findings

An earlier menu-renderer experiment moved menu visuals by changing a resolved X coordinate from `1821` to `1221`.

The touch regions remained unchanged.

A lower-level atlas-564 modification moved only the left navigation arrow's circular background, not the hamburger.

These findings establish that relevant visual and input positions can be controlled independently.

They do not establish the hamburger's own rendering path.

## 6. Hamburger State Investigation

Phase 7 established the following UI behavior:

- The hamburger is visible when the menu is closed.
- Opening the menu hides it.
- A separate lower-right close button dismisses the menu.
- Closing the menu restores the hamburger.

The Cockpit field at `+0x11B4` changes reproducibly:

| Menu state | Value |
|---|---:|
| Closed | 0 |
| Open | 256 |
| Closed again | 0 |

A watchpoint caught this change inside the function at unslid address:

`0x10037DBB0`

The relevant instruction writes to `Cockpit + 0x11B5`, causing the observed four-byte value to become `256`.

The function also updates other menu-related state.

This is a **confirmed menu-opening transition**, not a confirmed hamburger hitbox or rendering routine.

It may be useful for comparing draw behavior between the hamburger-visible and menu-open states.

## 7. Important Debugging Procedure

The installed game can be launched suspended before initialization:

```bash
xcrun devicectl device process launch \
  --device <DEVICE_ID> \
  --start-stopped \
  jp.co.capcom.mhp2g
```

Then locate the PID:

```bash
xcrun devicectl device info processes \
  --device <DEVICE_ID>
```

Start LLDB:

```bash
xcrun lldb
```

Attach:

```lldb
device select <DEVICE_ID>
device process attach -p <PID>
```

A successful suspended attachment previously stopped at `dyld::_dyld_start`.

Determine the current slide with:

```lldb
image list -o -f
```

Never reuse runtime pointers or ASLR slides from earlier processes.

## 8. Remaining Technical Questions

The following are unresolved:

1. Does ResourceManager key 11 actually reference `cock.tmh`?
2. Which embedded texture corresponds to the relevant sub-index?
3. Does the proposed 4× mapping hold, and does record 527 actually draw the large hamburger?
4. Which executable instruction draws the persistent hamburger?
5. Which touch-input region activates it?
6. Where does its horizontal coordinate originate?
7. Can its visual and touch positions be modified reliably?
8. What is the smallest persistent executable patch?

Do not infer answers from spatial coincidence or unrelated UI controls.

## 9. Recommended Research Direction

**Primary next step: runtime confirmation of atlas index 527.**

Attach LLDB to a fresh game process, verify executable identity and obtain the current ASLR slide (`image list -o -f`). Start with a conditional breakpoint at `0x10036C920 + slide` for `$w5 == 527` (sixth integer argument at function entry). Inspect registers and backtrace before making changes. If there is no hit during a verified hamburger-visible state, test the other known indexed helpers, particularly the historically observed `0x100378D6C` path (index at incoming `sp+8` in the atlas-564 experiment; verify the calling convention for the new candidate). `0x100375804` is another candidate (high 32 bits of ninth argument). A missed breakpoint is bounded negative evidence, not a global exclusion. Once the actual draw is captured, verify the destination X argument and perform a reversible position-only experiment; observe whether the hamburger moves and restore debugger state. Do not modify the baseline IPA or investigate the hitbox until rendering ownership is established.

If needed, use the Phase 7 menu-state indicator for visible/hidden comparisons. Independently verify texture identity and coordinate semantics; do not resume old 8× candidates without new evidence.

## 10. Instructions for Future Sessions

When continuing FUPatch4iPad:

1. Read this document for the objective and project status.
2. Read `research.md` for the most recent concise findings.
3. Consult `technical-reference.md` for evidence and function addresses.
4. Read individual phase reports only when their experimental details are needed.
5. Preserve the distinction between confirmed findings, hypotheses, and excluded candidates.
6. Prioritize the hamburger icon, not the previously studied navigation arrow.
7. Use one or two targeted LLDB commands at a time and inspect their output.
8. Recalculate all runtime addresses after restarting the application.
9. Avoid unnecessary changes to the baseline IPA or save data.
10. Update the current research summary and this handoff after significant milestones.

The research reports contain historical observations. An older report describing an experiment as pending does not invalidate a later report that confirms it.

Likewise, the current research summary should not be treated as evidence that a candidate rendering or hitbox path has been experimentally verified.

## 11. Resume Prompt

I'm continuing the FUPatch4iPad reverse-engineering project.

Read `docs/PROJECT_HANDOFF.md`, `docs/research.md`, and `docs/technical-reference.md` before starting.

The objective is to relocate the persistent hamburger menu icon in Monster Hunter Freedom Unite iOS 1.00.11 to the appropriate right-edge position on an iPad Air M2 while preserving size, vertical position, partial clipping, and touch functionality.

The revised PVRTexTool extraction locates the larger hamburger in `cock-5` at `(890, 593, 102, 142)`; color abnormalities remain. Atlas index 527 (`0x20F`), rectangle `(221,147,27,38)`, flags `0x8004`, key 11, is the leading candidate under the proposed 4× mapping. Record 564 provides a runtime-backed navigation-background reference. Neither the mapping nor hamburger ownership is fully verified.

Next, attach LLDB, obtain the fresh ASLR slide and test a conditional breakpoint for index 527 at `0x10036C920`. Inspect the actual call before attempting a reversible X-position change. The hamburger hitbox and persistent patch remain unknown. Avoid repeating excluded investigations and preserve the baseline IPA and saves.

## 12. Completion Criteria

The project is complete only when the relocated hamburger:

- Renders at the intended horizontal position.
- Retains its original size, Y position, and partial clipping.
- Has a correctly aligned functional touch area.
- Behaves correctly across relevant application states.
- Survives application restarts.
- Can be reproduced through documented patch steps.
- Does not require modifying the immutable baseline IPA or game saves.

**Current status: Research ongoing; persistent hamburger relocation not yet implemented.**
