# Phase 13 — Sort Button Geometry and Bottom-Edge Touch Support

## 1. Objective

Following the successful integration of native iPad Air (M2) support in Phase 12, two remaining UI issues were identified:

- The Sort button does not extend to the bottom edge of the display.
- The Loading text is partially clipped.

Phase 13 focuses on correcting the Sort button geometry and ensuring that its extended touch area remains responsive near the bottom screen edge.

The Loading text issue is deferred to Phase 14.

## 2. Research Environment

- Device: iPad Air (M2)
- System: iPadOS 18.7.3
- Architecture: ARM64
- Executable: `MH Unite`
- Baseline: Phase 12 production iPad patch
- Static analysis: Ghidra 12.2
- Runtime analysis: LLDB
- Branch: `feat/ipad-support`

The existing hamburger geometry and right-edge gesture deferral patches were active throughout the runtime investigation.

## 3. Ghidra Configuration Recovery

During the initial investigation, Ghidra became unresponsive. Existing scripts and newly created scripts failed to execute normally.

The following recovery attempts did not resolve the issue:

- Restarting Ghidra.
- Restarting the Mac.
- Launching Ghidra through different methods.
- Downloading a fresh Ghidra distribution.

The issue was resolved by assigning Ghidra a clean application settings directory.

```bash
mkdir -p "$HOME/Code/ghidra-clean-settings"

printf '\nVMARGS=-Dapplication.settingsdir=%s\n' \
  "$HOME/Code/ghidra-clean-settings" \
  >> support/launch.properties
```

Ghidra subsequently operated normally, and the atlas identification script executed successfully.

The existing application settings were implicated, although the exact problematic setting was not identified.

## 4. Atlas Identification

The Sort button background was identified in the `cock-5` texture atlas.

The measured artwork rectangle was:

```text
X:      576
Y:      580
Width:  308
Height: 160
```

A Ghidra script, `FindSortAtlas.java`, was used to search the existing atlas descriptor table.

The search used the atlas structure previously established during the hamburger investigation:

- Atlas table base: `0x10072E0FC`
- Record size: 12 bytes
- Coordinate multiplier: 4
- Flags: `0x8004`
- Resource key: `11`

### 4.1 Search Result

```text
FindSortAtlas.java> Running...
FindSortAtlas started.
Sort candidate | Index 556 (0x22C) |
Address 0x10072FB0C |
Atlas (144,144,77,41) |
Pixels (576,576,308,164)
Search complete.
Total candidates: 1
FindSortAtlas.java> Finished!
```

| Property | Value |
|---|---|
| Texture | `cock-5` |
| Atlas index | 556 (`0x22C`) |
| Record address | `0x10072FB0C` |
| Atlas rectangle | `(144,144,77,41)` |
| Pixel rectangle | `(576,576,308,164)` |
| Flags | `0x8004` |
| Resource key | 11 |

The atlas rectangle contains the measured artwork, including four additional pixels at the top.

Later runtime investigation demonstrated that this atlas entry represents a shared button background rather than a unique Sort button.

## 5. LLDB Attachment

The existing `tools/mhfu_attach.sh` utility was used to attach LLDB to the running game.

The executable-specific image query was identified as a more convenient alternative to listing all loaded images:

```lldb
image list -o -f "MH Unite"
```

The attachment utility can automatically execute this query by adding the following command after the process attachment command:

```bash
printf 'image list -o -f "MH Unite"\n' >> "$COMMANDS"
```

### 5.1 Runtime Addresses

The research session used the following ASLR slide:

```text
ASLR slide:      0x0222C000
Executable base: 0x10222C000
```

| Location | Unslid address | Runtime address |
|---|---|---|
| Layout conversion hook | `0x1003A35D0` | `0x1025CF5D0` |
| Hamburger helper | `0x10049E900` | `0x1026CA900` |
| Atlas record 556 | `0x10072FB0C` | `0x10295BB0C` |
| Low-level renderer | `0x100378D6C` | `0x1025A4D6C` |

Runtime addresses in this document are specific to the recorded debugging session. They must be recalculated after restarting the game.

## 6. Layout Conversion Investigation

The existing layout conversion hook from Phase 11 was reused for the investigation.

Disassembly confirmed that the permanent hamburger helper was active:

```asm
0x1025cf5d0: b      0x1026ca900
0x1025cf5d4: cmp    w8, #0x61
0x1025cf5d8: b.lt   0x1025cf620
0x1025cf5dc: add    x0, x19, #0x2c
```

A conditional breakpoint was placed at the hook:

```lldb
breakpoint set --address 0x1025CF5D0 --condition '*(unsigned int *)($x20 + 4) == 556'
```

The breakpoint successfully triggered.

The following register roles were reused from the previous investigation:

| Register | Purpose |
|---|---|
| `x4` | Geometry record |
| `x19` | Destination descriptor |
| `x20` | Compact layout record |
| `x21` | Geometry table base |

## 7. Initial Geometry Experiment

The first matching compact record referenced geometry index 25.

```text
Compact record:  0x108334720
Geometry record: 0x10832D460
Destination:     0x1440C5800
Geometry index:  25
Geometry type:   105 (0x69)
```

The original vertical offsets were `-72.0` at geometry offsets `+0x14` and `+0x44`.

Both offsets were experimentally changed to `-52.0`.

The generated destination rectangles were inspected before and after the modification.

| Rectangle | Original | Modified |
|---|---|---|
| A | `(1072,1489,252,115)` | `(1072,1521,252,115)` |
| B | `(1097,1515,202,92)` | `(1097,1547,202,92)` |
| C | `(1072,1489,252,115)` | `(1072,1521,252,115)` |

All three rectangles moved downward by exactly 32 renderer pixels.

This established that:

- Both geometry Y fields participate in the layout calculation.
- The vertical displacement multiplier is 1.6.
- The modification affects generated destination rectangles without changing their dimensions.

However, the visible Sort button did not appear to move.

A larger downward displacement was also tested without producing the expected movement of the target Sort button.

The subsequent investigation established that the initial geometry record belonged to a different button position.

## 8. Renderer Investigation

The low-level rendering function was investigated using conditional breakpoints.

The atlas lookup was confirmed through the following instructions:

```asm
adrp  x9, ...
add   x9, x9, #0xfc
ldrsw x10, [x29, #0x18]
madd  x15, x10, x8, x9
```

The lookup corresponds to:

```c
atlas_record = atlas_base + atlas_index * 12;
```

The renderer preserves its destination coordinates in the following registers:

| Register | Value |
|---|---|
| `x19` | X |
| `x20` | Y |
| `x22` | Width |
| `x21` | Height |

Two conditional breakpoint strategies were attempted:

- Filtering the incoming atlas index at `SP + 0x08`.
- Filtering the resolved atlas record pointer in `x15`.

Both strategies introduced substantial runtime overhead. The game appeared unresponsive while the renderer breakpoints were enabled.

Disabling the breakpoints restored normal gameplay.

Consequently, the investigation returned to the less frequently executed layout conversion function.

The renderer investigation did not establish direct rendering ownership of the target Sort button.

## 9. Shared Atlas Instance Enumeration

The layout breakpoint condition was expanded to check both atlas fields:

```c
*(unsigned int *)($x20 + 4) == 556 ||
*(unsigned int *)($x20 + 8) == 556
```

Previously discovered compact record addresses were progressively excluded from the condition.

Four distinct matching compact layout records were identified.

### 9.1 Runtime Records

| Geometry index | Compact address | Geometry address |
|---|---|---|
| 25 | `0x108334720` | `0x10832D460` |
| 26 | `0x108334760` | `0x10832D4E0` |
| 27 | `0x1083347A0` | `0x10832D560` |
| 35 | `0x108334BE0` | `0x10832D960` |

### 9.2 Geometry Comparison

| Property | Index 25 | Index 26 | Index 27 | Index 35 |
|---|---:|---:|---:|---:|
| Identifier | `0x8000` | `0x8000` | `0x8000` | `0x8000` |
| Atlas index | 556 | 556 | 556 | 556 |
| Geometry type | 105 | 105 | 105 | 105 |
| Primary X | -734 | -573 | -412 | -165 |
| Secondary X | -734 | -575 | -420 | -165 |
| Primary Y | -72 | -72 | -72 | -72 |
| Secondary Y | -72 | -72 | -72 | -72 |
| Width | 158 | 158 | 158 | 150 |
| Height | 72 | 72 | 72 | 72 |
| Scale | 0.8 | 0.8 | 0.8 | 0.8 |

The first three records are adjacent in their respective tables.

Their primary X coordinates increase by exactly 161 layout units, suggesting a sequence of predefined horizontal button positions.

No additional matching records were observed during the subsequent enumeration attempt. This does not establish that only four instances exist throughout the game.

## 10. Identification of the Target Geometry

Visual investigation revealed that the button background is shared among several controls, including controls in the Guild Card menu.

The Del button in the Guild Card menu occupies the same position as the Sort buttons in the Items and Combine menus.

Geometry index 27 was therefore selected for an isolated positioning experiment.

Both Y offsets were changed from `-72.0` to `-172.0`:

```lldb
memory write --size 4 0x10832D574 0xC32C0000
memory write --size 4 0x10832D5A4 0xC32C0000
```

Visual testing confirmed that all three buttons moved upward:

- Items — Sort
- Combine — Sort
- Guild Card — Del

This established that the three controls share geometry index 27.

### 10.1 Control Mapping

| Geometry index | Associated control | Status |
|---|---|---|
| 25 | Guild Card Type | Visual evidence |
| 26 | Guild Card Comments | Inferred |
| 27 | Items Sort, Combine Sort, Guild Card Del | Confirmed |
| 35 | Unknown | Unresolved |

## 11. Target Record Structure

### 11.1 Compact Layout Record

Runtime address:

```text
0x1083347A0
```

Unslid address:

```text
0x1061087A0
```

Original contents:

```text
+0x00: 00008000 0000022C 0000022C 0000001B
+0x10: 00000001 00000000 00000000 00000000
+0x20: 431E0000 42900000 00000000 00000000
+0x30: 00000000 00000000 00000000 00000000
```

Relevant fields:

| Offset | Value | Purpose |
|---|---|---|
| `+0x00` | `0x8000` | Compact identifier |
| `+0x04` | `0x22C` | First atlas index |
| `+0x08` | `0x22C` | Second atlas index |
| `+0x0C` | `0x1B` | Geometry index |
| `+0x20` | 158.0 | Width |
| `+0x24` | 72.0 | Height |

### 11.2 Geometry Record

Runtime address:

```text
0x10832D560
```

Unslid address:

```text
0x106101560
```

Original contents:

```text
+0x00: 00000069 00000000 00000000 00000000
+0x10: C3CE0000 C2900000 00000000 00000000
+0x20: 431E0000 42900000 00000000 00000000
+0x30: 3F4CCCCD 3F4CCCCD 00000000 00000000
+0x40: C3D20000 C2900000 00000000 00000000
+0x50: 431E0000 42900000 00000000 00000000
+0x60: 429E0000 42A00000 00000000 00000000
+0x70: 00000000 00000000 00000000 00000000
```

Relevant fields:

| Offset | Original value |
|---|---:|
| `+0x00` | 105 (geometry type) |
| `+0x10` | -412.0 |
| `+0x14` | -72.0 |
| `+0x20` | 158.0 |
| `+0x24` | 72.0 |
| `+0x30` | 0.8 |
| `+0x34` | 0.8 |
| `+0x40` | -420.0 |
| `+0x44` | -72.0 |
| `+0x50` | 158.0 |
| `+0x54` | 72.0 |

## 12. Successful Height Extension

Instead of moving the entire button downward, extending its height was selected as the preferred visual correction.

The original Y offsets were restored:

```lldb
memory write --size 4 0x10832D574 0xC2900000
memory write --size 4 0x10832D5A4 0xC2900000
```

The height was increased from 72.0 to 128.0 in the compact layout record and both geometry height fields.

```lldb
memory write --size 4 0x10832D584 0x43000000
memory write --size 4 0x10832D5B4 0x43000000
memory write --size 4 0x1083347C4 0x43000000
```

The game was resumed and the modified button was visually tested.

The resulting appearance was accepted.

### 12.1 Final Runtime Geometry Values

| Property | Original | Modified |
|---|---:|---:|
| Primary X | -412 | -412 |
| Secondary X | -420 | -420 |
| Primary Y | -72 | -72 |
| Secondary Y | -72 | -72 |
| Width | 158 | 158 |
| Height | 72 | 128 |
| Scale | 0.8 | 0.8 |

The height increased by approximately 77.8%, while the original positioning offsets, width, and scale remained unchanged.

### 12.2 Required Field Modifications

| Record | Offset | Original | Replacement |
|---|---|---|---|
| Geometry | `+0x24` | `0x42900000` | `0x43000000` |
| Geometry | `+0x54` | `0x42900000` | `0x43000000` |
| Compact | `+0x24` | `0x42900000` | `0x43000000` |

Little-endian representation:

```text
Original:    00 00 90 42
Replacement: 00 00 00 43
```

These modifications represent the successful runtime experiment. The generated rectangles were not independently dumped again after the final height extension.

### 12.3 Expanded Height Correction

Following the successful height extension of geometry index 27, the remaining three discovered geometry records were investigated for a consistent button layout.

All four records originally shared the following properties:

- Primary Y offset: -72.0
- Secondary Y offset: -72.0
- Height: 72.0
- Scale: 0.8
- Geometry type: 105 (`0x69`)
- Compact identifier: `0x8000`
- Both atlas indices: 556 (`0x22C`)

The height correction was expanded to include geometry indices 25, 26, 27, and 35.

| Geometry index | Original height | Modified height | Y offset |
|---|---:|---:|---:|
| 25 (`0x19`) | 72.0 | 128.0 | -72.0 |
| 26 (`0x1A`) | 72.0 | 128.0 | -72.0 |
| 27 (`0x1B`) | 72.0 | 128.0 | -72.0 |
| 35 (`0x23`) | 72.0 | 128.0 | -72.0 |

The original X offsets, widths, and scale factors were preserved.

#### Runtime Modification Addresses

| Geometry index | Primary height | Secondary height | Compact height |
|---|---|---|---|
| 25 | `0x10832D484` | `0x10832D4B4` | `0x108334744` |
| 26 | `0x10832D504` | `0x10832D534` | `0x108334784` |
| 27 | `0x10832D584` | `0x10832D5B4` | `0x1083347C4` |
| 35 | `0x10832D984` | `0x10832D9B4` | `0x108334C04` |

All twelve height fields were assigned `0x43000000`, representing the IEEE 754 single-precision value 128.0.

The original Y offsets were also restored to ensure that no previous positioning experiments remained active.

The combined runtime modification was tested on the physical iPad and produced an acceptable visual result in the observed menus.

#### Expanded Control Mapping

| Geometry index | Associated controls | Identification status |
|---|---|---|
| 25 | Guild Card Type | Visual evidence |
| 26 | Guild Card Comments | Inferred |
| 27 | Items Sort, Combine Sort, Guild Card Del | Confirmed |
| 35 | Unknown | Unresolved |

Geometry index 35 may belong to an online multiplayer interface. However, this remains an unverified hypothesis.

Despite its unresolved ownership, index 35 was intentionally included in the proposed permanent correction because it shares the same original vertical offsets, height, scale, atlas indices, compact identifier, and geometry type as the other three records.

Its associated visible control has not yet been individually validated.

## 13. Bottom-Edge Touch Interference

After the successful height extension, the enlarged Sort button remained unresponsive near the extreme bottom screen edge.

Testing established that the enlarged button was responsive away from the edge.

This behavior was consistent with the system gesture interference previously encountered with the hamburger button.

The existing Phase 11 gesture helper implements:

```objc
preferredScreenEdgesDeferringSystemGestures
```

Its existing return value requests gesture deferral for the right edge only.

| Edge | Mask |
|---|---|
| Top | `0x01` |
| Left | `0x02` |
| Bottom | `0x04` |
| Right | `0x08` |

The proposed combined mask is:

```text
0x08 | 0x04 = 0x0C
```

This preserves the existing right-edge deferral while adding bottom-edge deferral.

## 14. Runtime Gesture Deferral Experiment

The existing Objective-C method was replaced at runtime using LLDB.

```lldb
expression -l objc++ -- @import ObjectiveC;
```

```lldb
expression -l objc++ -- (void)class_replaceMethod((Class)NSClassFromString(@"RootViewController"), @selector(preferredScreenEdgesDeferringSystemGestures), (IMP)imp_implementationWithBlock(^unsigned long(id self) { return 12UL; }), "Q@:")
```

UIKit was imported:

```lldb
expression -l objc++ -- @import UIKit;
```

The following commands were used for controller inspection, gesture mask verification, and requesting an update:

```lldb
expression -l objc++ -O -- [[[UIApplication sharedApplication] keyWindow] rootViewController]
```

```lldb
expression -l objc++ -- (unsigned long)[[[[UIApplication sharedApplication] keyWindow] rootViewController] preferredScreenEdgesDeferringSystemGestures]
```

```lldb
expression -l objc++ -- (void)[[[[UIApplication sharedApplication] keyWindow] rootViewController] setNeedsUpdateOfScreenEdgesDeferringSystemGestures]
```

The expected gesture mask was 12 (`0x0C`).

The game was resumed:

```lldb
continue
```

Physical device testing confirmed that the previously unresponsive bottom-edge area became responsive.

This supports system gesture interception as the cause of the remaining touch issue.

The individual controller inspection and gesture-mask verification outputs were not retained in the research transcript.

## 15. Proposed Permanent Implementation

This section records the specification derived from the runtime experiments. Section 18 records the implemented and tested build.

### 15.1 Shared Geometry Helper

The existing hamburger layout helper is a suitable candidate for extension.

The proposed shared button matching conditions are:

```
Compact identifier == 0x8000
First atlas index  == 556
Second atlas index == 556
Geometry type      == 105

Geometry index must be one of:
    25 (0x19)
    26 (0x1A)
    27 (0x1B)
    35 (0x23)
```

Conceptually, the new helper logic is equivalent to:

```c
if (compact->identifier == 0x8000 &&
    compact->atlas1 == 556 &&
    compact->atlas2 == 556 &&
    geometry->type == 105 &&
    (compact->geometry_index == 25 ||
     compact->geometry_index == 26 ||
     compact->geometry_index == 27 ||
     compact->geometry_index == 35))
{
    geometry->primary_height = 128.0f;
    geometry->secondary_height = 128.0f;
    compact->height = 128.0f;
}
```

The following fields should be modified:

| Record | Offset | Replacement |
|---|---|---|
| Geometry | `+0x24` | `0x43000000` |
| Geometry | `+0x54` | `0x43000000` |
| Compact | `+0x24` | `0x43000000` |

All other geometry fields must remain unchanged.

The original Y offsets do not require permanent modification. Restoring them during runtime testing was only necessary to undo earlier positioning experiments.

The existing hamburger-specific matching conditions and modifications must be preserved.

The helper must explicitly whitelist the four discovered geometry indices rather than modifying every record using atlas index 556.

The inclusion of geometry index 35 is intentional despite its unresolved control ownership. Any additional matching geometry records discovered in the future must be investigated separately before expanding the whitelist.

### 15.2 Gesture Helper

The existing gesture helper should be updated from:

```asm
mov x0, #8
ret
```

To:

```asm
mov x0, #12
ret
```

| Property | Original | Proposed |
|---|---|---|
| Edge mask | `0x08` | `0x0C` |
| Instruction word | `0xD2800100` | `0xD2800180` |
| Little-endian bytes | `00 01 80 D2` | `80 01 80 D2` |

The proposed modification preserves right-edge gesture deferral and adds bottom-edge gesture deferral.

No additional Objective-C method or startup injection point is currently expected to be necessary.

### 15.3 Integration Requirements

Before production integration:

- Review the available code cave capacity.
- Extend the existing assembly helper.
- Verify all branch encodings and return addresses.
- Rebuild the patched ARM64 executable.
- Generate updated patch steps.
- Recalculate the expected executable SHA-256.
- Update the iPad Air (M2) manifest profile.
- Verify Python and TypeScript patcher parity.
- Run regression tests.
- Test the rebuilt IPA on the physical iPad.

## 16. Scope and Potential Side Effects

The expanded Phase 13 correction targets four shared button geometry records:

- Geometry index 25.
- Geometry index 26.
- Geometry index 27.
- Geometry index 35.

The currently identified or inferred affected controls include:

- Guild Card Type.
- Guild Card Comments.
- Guild Card Del.
- Items Sort.
- Combine Sort.

Additional controls may reuse these geometry records.

Geometry index 35 remains unidentified. It is suspected to belong to an online multiplayer interface, but this has not been verified. Its inclusion in the permanent patch is an intentional design decision based on its matching geometry characteristics.

The combined runtime modification produced acceptable results in the observed menus. However, this does not establish that every affected control has been visually or functionally validated.

Other geometry records using atlas index 556 must remain unchanged unless separately investigated.

Bottom-edge gesture deferral applies at the view-controller level rather than to individual buttons. Its effect on other gameplay controls and system gesture accessibility must be verified.

The runtime experiments do not establish compatibility with other iPad models or operating system versions.

## 17. Validation Checklist

### Runtime Research

- [x] Restore Ghidra functionality.
- [x] Identify the shared button atlas entry.
- [x] Identify the layout conversion path.
- [x] Enumerate observed shared atlas instances.
- [x] Establish the vertical displacement multiplier.
- [x] Identify geometry index 27.
- [x] Confirm shared ownership by both Sort buttons and Del.
- [x] Establish the successful height value of 128.0.
- [x] Visually validate the height extension.
- [x] Identify bottom-edge touch interference.
- [x] Test combined bottom/right gesture deferral.
- [x] Confirm restored bottom-edge responsiveness.

### Permanent Implementation

- [x] Extend the existing layout assembly helper.
- [x] Update the gesture assembly helper.
- [x] Verify code cave capacity.
- [x] Generate updated binary patch steps.
- [x] Verify the patched executable.
- [x] Build a test IPA.
- [x] Confirm persistence after restarting the game.

### Device Regression Testing

- [x] Items Sort appearance.
- [x] Items Sort touch responsiveness.
- [x] Combine Sort appearance.
- [x] Combine Sort touch responsiveness.
- [x] Guild Card Del appearance.
- [x] Guild Card Del touch responsiveness.
- [x] Guild Card Type appearance.
- [x] Guild Card Type touch responsiveness.
- [x] Guild Card Comments appearance.
- [x] Guild Card Comments touch responsiveness.
- [ ] Verify consistent heights across the Guild Card bottom-row buttons.
- [ ] Verify that non-whitelisted geometry records remain unchanged.
- [ ] Verify the unidentified geometry index 35 when its associated interface becomes accessible.
- [x] Hamburger appearance remains unchanged.
- [x] Hamburger right-edge responsiveness.
- [x] Bottom system gesture remains accessible.
- [ ] Other gameplay controls remain functional.

### Production Integration

- [x] Update the iPad Air 11-inch profile (`ipad-air-m2`).
- [x] Update expected executable hashes.
- [x] Verify Python patcher.
- [x] Verify TypeScript patcher.
- [x] Verify patcher parity.
- [x] Run regression tests.
- [x] Build the production web interface.
- [x] Update README.
- [x] Validate the combined production IPA on iPad Air (M2).
- [ ] Release the combined Phase 13 and Phase 14 production patch.

## 18. Permanent implementation and validation

Verification reproduced the final arm64 executable from the original IPA by applying the 36 common ranges to its arm64 slice, then applying the four ranges exported by the developer builder. The common baseline SHA-256 is `25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`. The final executable is 8,593,744 bytes and its SHA-256 is **`e2c04d018c032e027c3d6ab996f5843d2384903b3517d71f2488f8f0649587c1`**.

| Range | Unslid start | Bytes |
|---|---:|---:|
| Layout entry branch | `0x1003A35D0` | 4 |
| UI layout helper | `0x10049E900` | 200 |
| Startup gesture entry branch | `0x1003545D0` | 4 |
| Gesture helper | `0x10049EA00` | 156 |
| **Total** | | **364** |

Renaming `hamburger_hook` to `ui_layout_hook` first reproduced the Phase 12 executable byte for byte. In Phase 13 the first hamburger identifier mismatch branches to the appended matcher at `0x10049E964`. The original five hamburger stores and return branch retain their Phase 12 encodings. The appended matcher requires compact ID `0x8000`, both atlas indices equal to 556, geometry type 105, and index 25, 26, 27, or 35. It writes 128.0f to geometry offsets `+0x24` and `+0x54` and compact offset `+0x24`. All paths use only `w8` as scratch and rejoin the displaced `ldrsw x8, [x4]` before returning to `0x1003A35D4`.

The layout helper leaves 56 bytes before the gesture helper. At `0x10049EA4C`, the gesture method now returns the bottom/right mask with `mov x0, #12` (bytes `80 01 80 D2`). The startup helper still replays the displaced ADRP and returns to `0x1003545D4`.

### Automated verification

162 Python tests and 7 TypeScript profile tests passed. Assembled-instruction tests exercised the hamburger, all four whitelisted indices, signature mismatches, rejected indices, and repeat conversion. They checked the complete synthetic records and signed load result. Disassembly confirmed the branch destinations. The builder verified the baseline bytes at all four ranges, and a separate comparison confirmed all 8,593,380 bytes outside those ranges matched the baseline.

### Physical device validation

The device tester confirmed that Items Sort, Combine Sort, and Guild Card Type, Comments, and Del worked on the iPad Air M2 with the experimental IPA. Bottom-edge taps registered, the hamburger retained its appearance and responded to right-edge taps, and the system home gesture remained accessible. The corrections persisted after restarting the game.

**Geometry index 35 still has no identified visible owner.** Its record passed the automated height tests. Its individual on-screen behavior remains unverified.

Phase 13 and Phase 14 production integration and validation are complete. The tester confirmed that the game is fully working with the combined production IPA on iPad Air (M2).

For the subsequent production integration and its verification results, see the [combined production integration record](research-phase12-production-integration.md#subsequent-production-integration-of-phases-13-and-14).
