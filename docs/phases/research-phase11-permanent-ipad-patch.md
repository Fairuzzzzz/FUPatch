# Phase 11 — Permanent iPad Hamburger and Gesture-Deferral Patch

**Project:** FUPatch4iPad  
**Game:** Monster Hunter Freedom Unite iOS  
**Version:** 1.00.11  
**Device:** iPad Air 11-inch (M2)  
**iPadOS:** 18.7.3  
**Status:** Permanent patch device-tested and byte-for-byte reproducible

---

## 1. Research Objective

Convert the successful runtime modifications established during previous research phases into a permanent executable patch.

The objectives were to:

- Relocate the persistent hamburger menu to the right edge of the iPad display.
- Enlarge the hamburger to 150% of its original size.
- Enlarge the corresponding touch region.
- Resolve the delayed or ignored touch events near the right screen edge.
- Preserve the modifications across application launches.
- Eliminate the requirement for LLDB or external runtime intervention.

## 2. Baseline

The research was conducted against the existing patched ARM64 executable used by the native iPad baseline IPA.

### Baseline ARM64 SHA-256

```text
25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4
```

### Executable UUID

```text
58cc55c760ca3196b5d20c2aeb64b32b
```

### Device family

```text
UIDeviceFamily: [1, 2]
```

The baseline IPA was preserved unchanged throughout the experiments.

## 3. Persistent Layout Data Investigation

The original hamburger geometry and compact layout records were searched for in the executable using their known runtime byte patterns.

The search included:

- Original geometry position.
- Original geometry dimensions.
- Original geometry pivot.
- Compact hamburger layout record signature.

No exact matches were found.

A subsequent search across all 14,204 IPA members also returned no matches.

### 3.1 Runtime memory classification

LLDB memory-region inspection established that the records reside in the executable's writable `__DATA` segment rather than ordinary heap allocations.

Mach-O section inspection further identified the records as belonging to `__DATA.__common`, a zero-initialized section.

| Record | Unslid address |
|---|---|
| Shared geometry record | `0x106100860` |
| Closed-menu compact record | `0x1061037E0` |
| Open-menu compact record | `0x1061089E0` |

Because these records are populated at runtime and do not have corresponding initialized file bytes, they cannot be modified directly through the existing fixed-size binary replacement mechanism.

The original resource encoding and initialization source remain unidentified.

## 4. Layout Converter Hook

The layout converter was identified at:

```text
0x1003A35A4
```

A suitable interception point was found immediately before the converter evaluates the selected geometry type:

```asm
0x1003A35CC    add    x4, x21, x8, lsl #7
0x1003A35D0    ldrsw  x8, [x4]
0x1003A35D4    cmp    w8, #0x61
```

### 4.1 Register state

| Register | Purpose |
|---|---|
| `x19` | Destination layout descriptor |
| `x20` | Compact layout source record |
| `x21` | Geometry table base |
| `x4` | Selected geometry record |

The hook replaces the instruction at `0x1003A35D0` with a branch to a custom ARM64 helper.

### 4.2 Hamburger identification

The helper checks the following conditions before modifying any records:

| Record | Offset | Expected value |
|---|---|---:|
| Compact | `+0x00` | 8 |
| Compact | `+0x04` | 527 |
| Compact | `+0x08` | 527 |
| Compact | `+0x0C` | 1 |
| Geometry | `+0x00` | 99 |

These checks restrict the modification to the identified hamburger layout signature.

### 4.3 Final geometry and hitbox values

| Record | Offset | Original | Replacement |
|---|---|---:|---:|
| Geometry X | `+0x10` | -51.0 | 12.5 |
| Geometry width | `+0x20` | 51.0 | 76.5 |
| Geometry height | `+0x24` | 81.0 | 121.5 |
| Compact hitbox width | `+0x20` | 51.0 | 76.5 |
| Compact hitbox height | `+0x24` | 81.0 | 121.5 |

The geometry Y coordinate, scaling factors, pivot, and compact hitbox offsets remain unchanged.

The helper reproduces the displaced `ldrsw x8, [x4]` instruction before returning to the converter.

The original game remains responsible for calculating the final display and touch rectangles.

### 4.4 Shared geometry considerations

A conditional breakpoint was used to detect non-hamburger controls referencing geometry index 1.

No matching breakpoint events occurred during the tested menu transitions.

However, exclusivity across every game state has not been established. The permanent helper modifies the shared geometry record directly.

## 5. Code Cave Discovery and Validation

A zero-filled region was identified at:

```text
Start: 0x10049E8E4
End:   0x10049EFFF
Size:  1820 bytes
```

The region belongs to `__TEXT.__const`.

Validation established that:

- The region is file-backed.
- The enclosing Mach-O segment has read and execute permissions.
- The selected helper addresses are four-byte aligned.
- All 1,820 bytes were zero.
- Ghidra reported no incoming references to any address in the region.
- No overlap with known existing patch ranges was identified.

Zero bytes and absent recognized references do not conclusively establish that a region is unused. Indirect references remain possible.

### 5.1 Helper allocation

| Address | Purpose | Size |
|---|---|---:|
| `0x10049E900` | Hamburger helper | 100 bytes |
| `0x10049EA00` | Gesture registration helper | 156 bytes |

The two helpers occupy separate, non-overlapping regions.

## 6. Permanent Hamburger Patch

### Entry branch

```text
Address:     0x1003A35D0
Original:    880080b9
Replacement: ccec0314
Destination: 0x10049E900
```

### Return branch

```text
Address:     0x10049E960
Instruction: 0x17FC131D
Destination: 0x1003A35D4
```

### Hamburger-only executable SHA-256

```text
38c44095c7c65341d6dd89c6c66fec9e08127e4c49c4870a27f7ac8051f81b8f
```

### Device verification

The hamburger-only IPA successfully reproduced the enlarged and repositioned hamburger without LLDB.

However, touch events near the right screen edge remained unreliable.

This result was consistent with the previously identified UIKit system-gesture conflict.

## 7. Permanent UIKit Gesture Deferral

Previous runtime experiments demonstrated that adding the following Objective-C method to `RootViewController` resolved the right-edge touch problem:

```objc
- (UIRectEdge)preferredScreenEdgesDeferringSystemGestures {
    return UIRectEdgeRight;
}
```

The permanent patch reproduces this behavior by registering the method during application startup.

### 7.1 Objective-C metadata

| Component | Unslid address |
|---|---|
| RootViewController class object | `0x10069D158` |
| Instance method list | `0x100688280` |
| Class method list | `0x100688218` |

The existing instance method list contains four methods. Appending another method directly would overwrite adjacent metadata.

Runtime registration was therefore selected instead of relocating or extending the existing method list.

### 7.2 Existing runtime imports

The executable already imports the required runtime functions.

| Function | Stub address |
|---|---|
| `dlsym` | `0x100496CF8` |
| `class_addMethod` | `0x1004969EC` |

The helper dynamically resolves `sel_registerName` using `dlsym` with `RTLD_DEFAULT`.

No new dynamic library imports are required.

### 7.3 Startup hook

The application entry point creates an autorelease pool before calling `UIApplicationMain`.

The gesture registration hook is installed at:

```text
0x1003545D0
```

At this point, the autorelease pool is active and UIKit application initialization has not yet started.

The helper:

1. Preserves the frame pointer and return address.
2. Resolves `sel_registerName`.
3. Registers the gesture-deferral selector.
4. Computes the RootViewController class address using PC-relative addressing.
5. Calls `class_addMethod`.
6. Restores the stack and preserved registers.
7. Reproduces the displaced ADRP instruction.
8. Returns to the original startup sequence.

If selector lookup fails, registration is skipped and the original startup sequence resumes.

### 7.4 Custom method implementation

```asm
mov x0, #8
ret
```

The method uses the Objective-C type encoding:

```text
Q16@0:8
```

### 7.5 Gesture helper layout

| Address | Purpose |
|---|---|
| `0x10049EA00` | Registration helper |
| `0x10049EA4C` | Custom method implementation |
| `0x10049EA54` | Runtime function name |
| `0x10049EA65` | Gesture selector string |
| `0x10049EA91` | Method type encoding |

### 7.6 Address-dependent instructions

| Address | Instruction | Purpose |
|---|---|---|
| `0x1003545D0` | `0x1405290C` | Enter helper |
| `0x10049EA10` | `0x97FFE0BA` | Call dlsym |
| `0x10049EA2C` | `0xF0000FE0` | Resolve class page |
| `0x10049EA3C` | `0x97FFDFEC` | Call class_addMethod |
| `0x10049EA44` | `0xD0000FE8` | Reproduce displaced ADRP |
| `0x10049EA48` | `0x17FAD6E3` | Return to startup |

All external code and data addresses are accessed using PC-relative instructions, preserving compatibility with ASLR.

## 8. Combined Permanent Patch

The final combined executable contains four fixed-size binary replacements.

| Patch | Address | Size |
|---|---|---:|
| Hamburger entry branch | `0x1003A35D0` | 4 bytes |
| Hamburger helper | `0x10049E900` | 100 bytes |
| Gesture entry branch | `0x1003545D0` | 4 bytes |
| Gesture helper | `0x10049EA00` | 156 bytes |
| Total replacement ranges | | 264 bytes |

### Verified combined executable SHA-256

```text
1447d7909bce6466cceb9be6eb6341372839757de1a83176a16aa54683ea07c1
```

The executable was packaged into the existing native iPad baseline IPA, preserving its other member contents.

The resulting IPA was signed, installed, and tested on the iPad Air M2 without LLDB.

The user confirmed that the combined patch worked.

## 9. Reproducible Developer Toolchain

The successful experimental scripts were consolidated into repository-maintained tools.

| File | Purpose |
|---|---|
| `tools/arm64_encoding.py` | ARM64 branch and ADRP encoding |
| `tools/find_code_caves.py` | Zero-filled region discovery |
| `tools/ghidra/CheckCodeCave.java` | Code-cave inspection |
| `tools/asm/hamburger_hook.s` | Final hamburger assembly |
| `tools/asm/gesture_hook.s` | Final gesture assembly |
| `tools/build_ipad_patch.py` | Reproducible executable generation |
| `tests/test_arm64_encoding.py` | Instruction encoding tests |
| `tests/test_build_ipad_patch.py` | Builder regression tests |

### 9.1 Reproduction command

From the repository root:

```bash
python3 tools/build_ipad_patch.py \
    "/path/to/baseline/MH Unite" \
    --out "/path/to/MH Unite.reproduced" \
    --steps "/path/to/ipad_patch_steps.json"
```

The builder requires macOS and Xcode command-line tools.

It validates the source hash, assembles both helpers, rejects unresolved text-section relocations, verifies expected original bytes, applies the four binary replacements, and validates the final executable hash.

The optional JSON output contains the binary patch steps for future manifest integration.

The builder does not modify its input executable or package an IPA.

### 9.2 Reproducibility verification

The repository builder successfully produced the expected combined executable SHA-256:

```text
1447d7909bce6466cceb9be6eb6341372839757de1a83176a16aa54683ea07c1
```

A direct binary comparison using `cmp` confirmed that the reproduced executable was identical to the original device-tested combined executable.

## 10. Regression Tests

### ARM64 encoding

```bash
python3 -m unittest discover \
    -s tests \
    -p "test_arm64_encoding.py" \
    -v
```

Result: **24 tests passed.**

### Patch builder

```bash
python3 -m unittest discover \
    -s tests \
    -p "test_build_ipad_patch.py" \
    -v
```

Result: **34 tests passed.**

Total: **58 new passing tests.**

The tests cover:

- Known branch and ADRP encodings.
- Instruction range and alignment validation.
- Fixed-size patch construction.
- Original byte verification.
- Overlapping patch detection.
- Preservation of unrelated bytes.
- Mach-O object section extraction.
- Unresolved relocation rejection.
- Unsupported baseline rejection.
- Result hash validation.

The tests do not require the original game executable or Xcode. Actual assembly and full executable reproduction were verified separately on macOS.

The reusable Ghidra script's revised parameterized version remains unverified. Its original fixed-range version successfully validated the selected code cave.

## 11. Remaining Work

The permanent binary patch is implemented, device-tested, and reproducible.

The following work remains:

- Integrate the four binary replacements into a dedicated iPad profile.
- Support profile-specific `UIDeviceFamily` modifications.
- Maintain equivalent behavior between Python and TypeScript patching engines.
- Verify that existing iPhone profile hashes remain unchanged.
- Run the complete repository regression suite.
- Verify broader gameplay compatibility and application restart behavior.
- Test additional iPad models and iPadOS versions.
- Verify the updated parameterized Ghidra script.
- Update project handoff and technical reference documentation.

Production manifest integration remains separate from the developer toolchain.

## 12. Known Limitations

- The patch targets one verified baseline ARM64 executable.
- The helper modifies shared geometry data whose exclusivity has not been established across every game state.
- Indirect references to the selected code cave cannot be completely ruled out.
- Gesture registration does not currently expose a persistent diagnostic result.
- Right-edge gesture deferral changes the root controller's system-gesture behavior for the entire right edge.
- Device compatibility beyond the tested iPad Air M2 remains unverified.

Original game binaries, patched executables, IPA files, compiled object files, and local Ghidra databases must remain outside the public repository.

---

**Phase 11 conclusion:** The persistent hamburger relocation, enlargement, and right-edge gesture-deferral problem has been resolved through a reproducible permanent executable patch. The solution requires no LLDB intervention, injected dynamic library, new imports, or Objective-C method-list restructuring. Production patcher integration is the next development phase.

The updated parameterized CheckCodeCave.java script was
successfully verified.

Results:
- Bytes scanned: 1820
- Nonzero bytes: 0
- Incoming references: 0
- Non-executable bytes in Ghidra: 1820
- Result: CANDIDATE REQUIRES REVIEW

Ghidra classifies the __TEXT.__const memory block as
non-executable. However, Mach-O segment inspection and
LLDB runtime inspection independently confirmed r-x
permissions.

Successful on-device execution further confirmed the
selected region's suitability for the implemented hooks.