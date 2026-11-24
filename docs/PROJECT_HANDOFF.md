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

### 4.1 Corrected hamburger source image

The hamburger is visually identified in `cock-5`, the fifth texture extracted from `Payload/MH Unite.app/cockpit/cock.tmh`.

**Current visible source bounds:** `(890, 593, 102, 142)` (X, Y, width, height), measured on the corrected PVRTexTool extraction. These are visible pixel bounds, not necessarily the complete sprite rectangle.

The earlier bounds `(1804, 604, 187, 119)` came from an incorrectly decoded image and are superseded. The earlier 2× vertical preview convention is also superseded; it is not evidence of intentional renderer scaling. Use the corrected, unscaled extraction for visual and coordinate analysis.

Identifying the source pixels does not identify the rendering instruction. See [technical-reference.md](technical-reference.md) for historical extraction details.

### 4.2 Atlas candidates require reevaluation

The previous candidates 204, 205, 208, and 209 in the table at `0x10072E0FC` were selected using the incorrect source bounds. Their union under the hypothetical 8× mapping is `(1792, 512, 256, 256)`, which does not overlap the corrected bounds.

These entries are now unsupported hamburger candidates, not globally ruled out by runtime evidence. Do not prioritize them without independent evidence.

If the unverified 8× mapping applies, the corrected bounds correspond to approximately `(111.25, 74.125, 12.75, 17.75)` in table units. Use this only as a fresh search hypothesis; padded sprite bounds and other mappings remain possible.

### 4.3 ResourceManager mapping remains unresolved

Static analysis of the former candidates established ResourceManager key 11 and texture sub-index 0 for their flagged rendering path. This remains valid for those records, but does not establish that the hamburger uses either value.

The relationship **ResourceManager key 11 → registered resource → `cock.tmh` → embedded texture** remains unverified. Independently establish the actual resource and texture mapping and the atlas table's relationship to `cock-5`. Relevant functions and evidence are in the technical reference.

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
3. Does the atlas table describe source rectangles in `cock-5`, and which records, if any, match the corrected bounds?
4. Which executable instruction draws the persistent hamburger?
5. Which touch-input region activates it?
6. Where does its horizontal coordinate originate?
7. Can its visual and touch positions be modified reliably?
8. What is the smallest persistent executable patch?

Do not infer answers from spatial coincidence or unrelated UI controls.

## 9. Recommended Research Direction

**Primary next steps:** Perform a fresh atlas search using the corrected source bounds under explicitly labeled plausible coordinate mappings, and independently trace ResourceManager registration and texture selection, including key 11.

Prioritize records only when supported by texture mapping and draw-path evidence; do not resume the former four candidates solely because of their old coordinate fit.

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

The corrected PVRTexTool extraction locates the hamburger in `cock-5` at `(890, 593, 102, 142)`. The former atlas candidates 204, 205, 208, and 209 have lost their coordinate-fit justification; the earlier 2× vertical scaling hypothesis is superseded. Perform a fresh atlas search and independently verify resource-to-texture mapping. The 8× coordinate conversion and the mapping between ResourceManager key 11, `cock.tmh`, and texture sub-index 0 remain unresolved.

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
