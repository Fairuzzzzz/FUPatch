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

### 4.1 Hamburger source image identified

The hamburger graphic has been visually identified in the fifth decoded Cockpit texture:

**Texture:** `cock-5`  
**Dimensions:** 2048 × 2048  
**Visible hamburger bounds:** `(1804, 604, 187, 119)`

The image was extracted from:

`Payload/MH Unite.app/cockpit/cock.tmh`

The `.tmh` resource contains five embedded PVR v2 textures, decoded using PowerVR's `PVRTDecompressPVRTC` routine.

The extraction and decoding process did not modify the baseline IPA.

**Important:** Identifying the source pixels does not identify the executable instruction that renders them.

### 4.2 Candidate atlas entries

Four records in the atlas table at unslid address `0x10072E0FC` have been identified as candidates:

| Index | X | Y | W | H |
|---|---:|---:|---:|---:|
| 204 | 224 | 64 | 16 | 16 |
| 205 | 240 | 64 | 16 | 16 |
| 208 | 224 | 80 | 16 | 16 |
| 209 | 240 | 80 | 16 | 16 |

Each record has resource field `11` and flags `0x8000`.

A hypothetical 8× coordinate conversion makes their combined region contain the hamburger's visible pixels.

However, the scale, record semantics, and relationship to the actual draw call remain unproven.

**Do not treat these records as confirmed hamburger sprites.**

### 4.3 Current ResourceManager blocker

Static analysis established that the flagged atlas-rendering path uses:

- ResourceManager key `11`.
- Texture sub-index `0`.
- Cockpit texture loading and caching routines.

Relevant functions include:

| Function | Role |
|---|---|
| `0x100375FD4` | Resource lookup and texture selection |
| `0x1003762B4` | Atlas record consumption |
| `0x1002C2138` | ResourceManager key lookup |
| `0x10035EE00` / `0x10035EE14` | Cockpit texture cache |
| `0x10035D968` | Texture sub-index retrieval |

The missing relationship is:

**ResourceManager key 11 → registered resource → `cock.tmh` → embedded texture**

Neither the association with `cock.tmh` nor the relationship between sub-index 0 and `cock-5` has been confirmed.

This is the main blocker in the latest static-analysis research.

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
3. Do atlas entries 204, 205, 208, and 209 contribute to hamburger rendering?
4. Which executable instruction draws the persistent hamburger?
5. Which touch-input region activates it?
6. Where does its horizontal coordinate originate?
7. Can its visual and touch positions be modified reliably?
8. What is the smallest persistent executable patch?

Do not infer answers from spatial coincidence or unrelated UI controls.

## 9. Recommended Research Direction

**Primary next step:** Resolve the ResourceManager registration chain for key 11 and determine its relationship to the Cockpit texture resource.

Then investigate whether the candidate atlas records participate in hamburger rendering.

If the static mapping proves inconclusive, use Phase 7's confirmed menu-state transition to perform targeted runtime comparisons between hamburger-visible and menu-open states.

Once a specific draw call has been identified, use a reversible coordinate modification to confirm its ownership.

Only then investigate the associated touch region and persistent patch design.

Avoid repeating already disproven atlas-564 experiments or spending time on generic state-machine disassembly without a specific hypothesis.

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

The hamburger's source pixels have been located in `cock-5`, and atlas entries 204, 205, 208, and 209 are candidates. However, the mapping between ResourceManager key 11, `cock.tmh`, and texture sub-index 0 remains unresolved.

The hamburger's actual rendering call and touch region have not been confirmed.

Please continue from these findings, avoid repeating ruled-out investigations, and favor evidence-driven reverse engineering with small, reversible experiments.

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
