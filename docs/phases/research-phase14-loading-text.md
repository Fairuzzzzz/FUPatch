# Research Phase 14 — Loading Text Position Correction

## 1. Overview

Phase 14 investigates the partially off-screen "NOW LOADING" artwork observed when running Monster Hunter Freedom Unite for iOS on the iPad Air (M2).

Unlike the shared button geometry issue addressed in Phase 13, this issue concerns animated loading artwork and does not require touch hitbox correction.

The objective is to reposition the loading lettering so that the complete phrase is visible within the native iPad display while preserving its original artwork, dimensions, spacing, and animation.

Production integration of Phase 13 and Phase 14 will be performed together after both permanent corrections have been validated on physical hardware.

**Status: Static research in progress. Candidate correction identified. Runtime validation pending.**

---

## 2. Research Environment

| Property | Value |
|---|---|
| Game | Monster Hunter Freedom Unite for iOS |
| Game version | 1.00.11 |
| Architecture | ARM64 |
| Device | iPad Air (M2) |
| Operating system | iPadOS 18.7.3 |
| Repository branch | `feat/ipad-support` |
| Executable image base | `0x100000000` |
| Runtime research baseline | Phase 13 patched executable |
| Static analysis tool | Ghidra |
| Runtime debugging tool | LLDB |

### 2.1 Phase 13 Checkpoint

The preceding Phase 13 implementation was validated on physical hardware and committed locally.

| Commit | Description |
|---|---|
| `5574845` | Permanent shared button height and gesture correction |
| `39e70ec` | Phase 13 implementation and device validation documentation |

Phase 13 production integration remains intentionally deferred.

### 2.2 Executable Baselines

Common patched ARM64 baseline:

```text
~/Code/FUPatch4iPad-analysis/MH Unite
```

SHA-256:

```text
25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4
```

Phase 13 device-validated executable:

```text
~/Code/FUPatch4iPad-analysis/MH Unite.phase13-patched
```

SHA-256:

```text
e2c04d018c032e027c3d6ab996f5843d2384903b3517d71f2488f8f0649587c1
```

Device test IPA:

```text
~/Files/MHFU/MHFU-iPad-phase13-test.ipa
```

The original common baseline must remain unchanged for reproducible permanent patch generation.

---

## 3. Observed Issue

The animated "NOW LOADING" lettering appears near the bottom-right corner of the loading screen.

On the iPad Air (M2), part of the phrase extends beyond the right display boundary.

Initial visual observations:

- Individual glyphs appear to retain reasonable dimensions.
- The visible glyphs have differing vertical positions.
- The loading background remains visible.
- The primary suspected issue is excessive horizontal positioning.
- No touch interaction is associated with the lettering.

These observations initially suggested that the complete phrase could be repositioned without changing individual glyph dimensions.

The exact off-screen extent and desired final right margin have not yet been measured.

---

## 4. Texture Resource Identification

The cockpit textures previously investigated during Phases 11 and 13 were inspected and did not contain the loading artwork.

Research from the PSP version suggested that the artwork might be associated with:

```text
system/resides/material00
```

This led to inspection of the corresponding system resources in the iOS IPA.

### 4.1 iOS Resource Discovery

Command:

```bash
unzip -Z1 "$HOME/Files/MHFU/MHFU-iPad-baseline.ipa" \
  | grep -Ei 'material00|resides|loading'
```

Relevant results:

```text
Payload/MH Unite.app/system/resides.tmh
Payload/MH Unite.app/system/Localize/eng/resides_e.tmh
Payload/MH Unite.app/system/Localize/fr/resides_f.tmh
Payload/MH Unite.app/system/Localize/ge/resides_g.tmh
Payload/MH Unite.app/system/Localize/it/resides_i.tmh
Payload/MH Unite.app/system/Localize/sp/resides_s.tmh
```

### 4.2 Research Workspace

The extracted resources were stored outside the repository:

```text
~/Code/FUPatch4iPad-analysis/phase14/textures/
```

The default and English resources were extracted for comparison.

```bash
unzip -j "$HOME/Files/MHFU/MHFU-iPad-baseline.ipa" \
  "Payload/MH Unite.app/system/resides.tmh" \
  "Payload/MH Unite.app/system/Localize/eng/resides_e.tmh"
```

---

## 5. TMH Container Analysis

Both resources have the same file size but different SHA-256 hashes.

| Resource | File size |
|---|---:|
| `resides.tmh` | 2,621,624 bytes |
| `resides_e.tmh` | 2,621,624 bytes |

### 5.1 Resource Hashes

`resides.tmh`:

```text
8dedbe148fac479b5b893277c8a9354b033e2de10e64bb6dcac2cf23ec5577f0
```

`resides_e.tmh`:

```text
92017c80dd710c6b0a27243898e40af2c450953425d38d834d66737cb8377e57
```

The first observed difference occurs at one-based file position 2,107,763, within the second embedded texture.

### 5.2 Container Header

Both resources begin with:

```text
.TMH0.14
```

Each contains two embedded PVR v2 textures.

| Property | Texture 0 | Texture 1 |
|---|---:|---:|
| PVR header offset | `0x000030` | `0x200084` |
| PVR signature offset | `0x00005C` | `0x2000B0` |
| Compressed data offset | `0x000064` | `0x2000B8` |
| Header size | 52 bytes | 52 bytes |
| Width | 2048 | 1024 |
| Height | 2048 | 1024 |
| Compressed data size | 2,097,152 bytes | 524,288 bytes |
| Format flags | `0x8019` | `0x8019` |
| Compression | PVRTC 4bpp | PVRTC 4bpp |

### 5.3 Embedded Texture Comparison

The first embedded texture is byte-identical between the default and English resources.

The second embedded texture differs.

Three unique PVR files were therefore extracted:

```text
resides-0.pvr
resides-1.pvr
resides_e-1.pvr
```

The duplicate `resides_e-0.pvr` was not retained.

---

## 6. Texture Extraction and Decoding

The embedded PVR textures were extracted by locating each `PVR!` signature, subtracting 44 bytes to obtain the PVR header address, and using the header's declared payload size.

Extraction script:

```python
from pathlib import Path
import struct

seen = {}

for path in sorted(Path(".").glob("*.tmh")):
    data = path.read_bytes()
    offset = 0
    index = 0

    while (pos := data.find(b"PVR!", offset)) != -1:
        start = pos - 44

        header_size, height, width, mipmaps, flags, data_size, bpp = \
            struct.unpack_from("<7I", data, start)

        assert header_size == 52

        end = start + header_size + data_size
        assert end <= len(data)

        texture = data[start:end]
        output = Path(f"{path.stem}-{index}.pvr")

        if texture not in seen:
            output.write_bytes(texture)
            seen[texture] = output.name

        offset = end
        index += 1
```

The previous cockpit texture decoder was not located in the repository or analysis workspace.

A Python-based decoding approach was subsequently used with `texture2ddecoder` and Pillow.

```bash
python3 -m pip install texture2ddecoder Pillow
```

Decoding procedure:

```python
from pathlib import Path
from PIL import Image
import struct
import texture2ddecoder

for path in sorted(Path(".").glob("*.pvr")):
    data = path.read_bytes()

    header_size, height, width = struct.unpack_from("<3I", data)

    pixels = texture2ddecoder.decode_pvrtc(
        data[header_size:],
        width,
        height,
        False
    )

    image = Image.frombytes(
        "RGBA",
        (width, height),
        pixels,
        "raw",
        "BGRA"
    )

    image.save(path.with_suffix(".png"))
```

The resulting shared texture, `resides-0.png`, was successfully inspected.

Extracted game resources and decoded textures must remain outside the Git repository.

---

## 7. Loading Glyph Identification

The loading artwork was positively identified in:

```text
resides-0.png
```

Texture dimensions:

```text
2048 × 2048 pixels
```

The letters are stored as individual glyphs rather than a complete pre-rendered "NOW LOADING" phrase.

The first three visible glyphs were measured as follows:

| Glyph | X | Y | Width | Height |
|---|---:|---:|---:|---:|
| N | 3 | 1091 | 93 | 84 |
| O | 100 | 1090 | 91 | 87 |
| W | 195 | 1093 | 86 | 85 |

These measurements describe visible artwork boundaries rather than necessarily the complete texture sampling rectangles.

### 7.1 Uniform Glyph Grid Hypothesis

The horizontal separation between the measured glyphs is approximately 96 pixels.

This suggested a fixed-size grid with an approximate origin of `(0, 1088)` and cell dimensions of `96 × 96`.

| Glyph | Hypothesized cell X | Hypothesized cell Y |
|---|---:|---:|
| N | 0 | 1088 |
| O | 96 | 1088 |
| W | 192 | 1088 |
| L | 288 | 1088 |
| A | 384 | 1088 |
| D | 480 | 1088 |
| I | 576 | 1088 |
| G | 672 | 1088 |

The horizontal grid hypothesis was subsequently supported by the discovery of a 24-unit texture-coordinate increment in the loading renderer.

The exact vertical sampling boundaries differ slightly from the initial grid hypothesis, as discussed in Section 13.

---

## 8. Static Atlas Discovery Experiments

### 8.1 Initial Search

A Ghidra script was created:

```text
tools/ghidra/FindLoadingAtlas.java
```

The initial version searched initialized executable memory for the 12-byte atlas record structure previously identified during cockpit research.

Assumed structure:

| Offset | Type | Field |
|---|---|---|
| `+0x00` | uint16 | X |
| `+0x02` | uint16 | Y |
| `+0x04` | uint16 | Width |
| `+0x06` | uint16 | Height |
| `+0x08` | uint16 | Flags |
| `+0x0A` | uint16 | Resource |

The script tested coordinate multipliers of 1, 2, and 4 with an 8-pixel boundary tolerance.

Result:

```text
Total matches: 0
```

### 8.2 Uniform Grid Search

The script was subsequently updated to search for uniform 96 × 96 glyph cells.

Search parameters:

- Grid origin: `(0, 1088)`.
- Cell size: `96 × 96`.
- Eight candidate glyphs.
- Coordinate multipliers: 1, 2, 4, and 8.
- Tolerance: 8 pixels.
- Assumed record size: 12 bytes.
- Consecutive record detection.
- Shared flags and resource verification for consecutive records.

Result:

```text
Total individual matches: 0
Total sequence matches: 0
```

### 8.3 Interpretation

Neither search identified records matching the assumed cockpit atlas format.

These negative results do not establish that no static loading glyph metadata exists.

Subsequent renderer analysis demonstrated that the texture coordinates are assembled into vertex data during rendering, providing a plausible explanation for the unsuccessful rectangle searches.

The scripts and negative results are retained as part of the research history.

---

## 9. System Resource Registry Investigation

Following the unsuccessful atlas searches, the executable's resource filename strings were investigated.

### 9.1 Localized Resource Strings

| Language | String address |
|---|---|
| English | `0x1005D28DE` |
| French | `0x1005D2900` |
| German | `0x1005D2921` |
| Italian | `0x1005D2942` |
| Spanish | `0x1005D2963` |

A Ghidra script was created to retrieve cross-references:

```text
tools/ghidra/FindResidesReferences.java
```

Each string had one recognized data reference.

| Language | Pointer address |
|---|---|
| English | `0x1006F4ED0` |
| French | `0x1006F4ED8` |
| German | `0x1006F4EE0` |
| Italian | `0x1006F4EE8` |
| Spanish | `0x1006F4EF0` |

No direct references were initially identified for these individual pointer entries.

### 9.2 Surrounding Resource Table

Inspection of the surrounding data revealed that these pointers belong to a larger resource filename registry.

Confirmed registry base:

```text
0x1006F4DE0
```

Entry size:

```text
8 bytes
```

The relevant file IDs are:

| File ID | Hexadecimal | Resource |
|---:|---|---|
| 24 | `0x18` | `system/connect.tmh` |
| 25–29 | `0x19–0x1D` | Localized demo textures |
| 30 | `0x1E` | English resides texture |
| 31 | `0x1F` | French resides texture |
| 32 | `0x20` | German resides texture |
| 33 | `0x21` | Italian resides texture |
| 34 | `0x22` | Spanish resides texture |
| 35 | `0x23` | `system/arcade.tmh` |

Two executable references to the registry base were identified:

| Reference instruction | Function |
|---|---|
| `0x10023D2FC` | `FUN_10023D2AC` |
| `0x10023CA8C` | `FUN_10023CA30` |

---

## 10. Resource Loading Function Identification

The decompiled functions contained assertions preserving original function names and source filenames.

Original source filename:

```text
no_fake_rofs.cpp
```

### 10.1 Filename Lookup

Function:

```text
0x10023D2AC
```

Original name:

```text
getFileName
```

Suggested research name:

```text
ROFS_getFileName
```

This function constructs a normalized resource path by indexing the filename registry using the supplied file ID.

The decompiled implementation confirms that the registry base is indexed directly, establishing the localized resides file IDs.

### 10.2 Split Filename Lookup

Function:

```text
0x10023CA30
```

Suggested research name:

```text
ROFS_getFileNameSplit
```

This function retrieves the resource path and separates the filename from its extension.

### 10.3 Caller Discovery

An additional Ghidra script was created:

```text
tools/ghidra/FindResidesCallers.java
```

The filename lookup function had data references but no recognized direct callers.

The split filename lookup function had two direct callers:

| Function | Call instruction |
|---|---|
| `0x10023CB68` | `0x10023CBD4` |
| `0x10023C7F4` | `0x10023C8D0` |

### 10.4 Resource Size Function

Function:

```text
0x10023CB68
```

Original name:

```text
size
```

Suggested research name:

```text
ROFS_size
```

This function obtains the resource's file size and performs alignment and extension-specific handling.

It also invokes a virtual method through offset `+0x90`, consistent with indirect filename lookup.

### 10.5 Asynchronous Resource Loader

Function:

```text
0x10023C7F4
```

Original name:

```text
loaderThread
```

Suggested research name:

```text
ROFS_loaderThread
```

This function processes queued asynchronous resource requests.

Inferred queue properties:

| Property | Value |
|---|---|
| Request record stride | `0x30` |
| Apparent request array offset | `0x48` |
| File ID field within request | `+0x02` |
| File ID type | uint16 |

The file ID access is represented in the decompiler as:

```c
*(uint16_t *)((long)param_1 + request_index * 0x30 + 0x4a)
```

The resource-loading investigation confirmed the file IDs and generic loading infrastructure but did not directly identify the loading artwork renderer.

---

## 11. Investigation Strategy Change

Runtime tracing of the resource loader was considered.

Potential breakpoint targets included:

```text
0x10023CB68
0x10023D2AC
0x10023CA30
```

A conditional breakpoint could filter for file IDs 30 through 34.

However, the resident system texture may be loaded before the debugger attaches, and loading artwork is only displayed transiently.

For these reasons, static analysis was prioritized.

A more direct investigation path became available through the inherited loading-related patches already present in the common patched executable.

---

## 12. Existing Loading Patch Analysis

The original patch feature grouping identifies five loading-related patch addresses:

```python
('loading', 'Loading text/background & map', [
    0x100441b58,
    0x1004420dc,
    0x100442240,
    0x100462a78,
    0x100462f14
])
```

These are existing common patches, not modifications introduced during the iPad research.

### 12.1 Manifest Entries

| Patch ID | Address | Original bytes | Replacement bytes |
|---|---|---|---|
| `loading.29` | `0x100441B58` | `09` | `89` |
| `loading.30` | `0x1004420DC` | `13814079` | `51710114` |
| `loading.31` | `0x100442240` | `4932fd97` | `00710194` |
| `loading.32` | `0x100462A78` | See manifest | See manifest |
| `loading.33` | `0x100462F14` | `e00313aae10315aadece00940309631e` | `0309631e2801781e6900781e68260e29` |

The second and third entries redirect execution into existing injected assembly within the `safe-area.34` patch allocation.

| Hook address | Instruction | Destination |
|---|---|---|
| `0x1004420DC` | `b` | `0x10049E620` |
| `0x100442240` | `bl` | `0x10049E640` |

### 12.2 First Existing Helper

Address:

```text
0x10049E620
```

Disassembly:

```asm
10049e620  ldrh    w19, [x8, #0x40]
10049e624  lsr     w9, w19, #2
10049e628  add     w19, w19, w9
10049e62c  b       0x1004420E0
```

Equivalent behavior:

```c
uint32_t value = *(uint16_t *)(x8 + 0x40);
value += value >> 2;
```

The helper increases the original value by approximately 25 percent.

More precisely:

```text
result = original + floor(original / 4)
```

The instruction at `0x10049E620` reproduces the original instruction displaced by the hook at `0x1004420DC`.

### 12.3 Second Existing Helper

Address:

```text
0x10049E640
```

Disassembly:

```asm
10049e640  adrp    x8, 0x10074b000
10049e644  ldr     s2, [x8, #0x994]
10049e648  mov     w9, #78
10049e64c  scvtf   s3, w9
10049e650  fmul    s2, s2, s3
10049e654  fcvtzs  w9, s2
10049e658  add     x1, x1, w9, sxtw
10049e65c  ldr     s2, [x8, #0x994]
10049e660  mov     w9, #56
10049e664  scvtf   s3, w9
10049e668  fmul    s2, s2, s3
10049e66c  fcvtzs  w9, s2
10049e670  add     w2, w2, w9
10049e674  bl      0x10038EB64
10049e678  b       0x100442244
```

Equivalent arithmetic:

```c
float scale = *(float *)0x10074B994;

x1 += (int32_t)(78.0f * scale);
w2 += (int32_t)(56.0f * scale);
```

The helper applies two scaled offsets before invoking the original function.

The exact semantics of the scale variable and downstream rendering arguments have not been fully established.

Subsequent analysis showed that this helper executes after the loading glyph loop. It is therefore not the direct horizontal-origin adjustment for the animated lettering.

---

## 13. Loading Glyph Renderer Discovery

The function beginning at:

```text
0x1004420E0
```

was examined following discovery of the first injected helper.

Ghidra represents this address as a separate function because of the inherited injected branch.

The original containing function appears to begin at:

```text
0x100441AFC
```

### 13.1 Dynamic Texture Coordinate Construction

The decompiled rendering loop contains the following expressions:

```c
uv0 = glyph | 0x1110000;

uv1 = ((glyph + 0x18) & 0xffff)
    | 0x1110000;

uv2 = glyph | 0x1280000;

uv3 = ((glyph + 0x18) & 0xffff)
    | 0x1280000;
```

These expressions appear to construct packed texture coordinates for the four corners of a glyph quad.

Relevant constants:

| Constant | Decimal | Pixel equivalent at 4× |
|---|---:|---:|
| `0x18` | 24 | 96 |
| `0x111` | 273 | 1092 |
| `0x128` | 296 | 1184 |

The horizontal sampling width corresponds to 96 pixels, supporting the earlier fixed-width glyph hypothesis.

The vertical coordinate difference is 23 units, corresponding to 92 pixels at the hypothesized 4× multiplier.

The initial `96 × 96` cell hypothesis therefore should not be treated as an exact description of the final sampling rectangle.

The vertical coordinate convention and texture sampling behavior remain to be verified.

### 13.2 Glyph Sequence

The rendering loop obtains glyph values from a sequence of unsigned 16-bit entries.

The loop terminates when it encounters:

```text
0xFFFF
```

Entries equal to:

```text
0xFFFE
```

do not produce a rendered quad but still advance the horizontal position.

These are consistent with an end-of-sequence marker and a spacing or skipped-glyph marker, respectively.

### 13.3 Quad Rendering

The glyph loop constructs packed texture coordinates, vertex positions, and color-related fields before invoking:

```text
FUN_1003E2A40
```

The decompiled call is represented as:

```c
FUN_1003e2a40(
    *unaff_x25,
    &uStack00000000000000a8,
    9
);
```

The precise downstream rendering interface and meaning of the final argument have not yet been independently established.

### 13.4 Horizontal Position

The current horizontal position is held in `w19`.

It is incorporated into the glyph vertex positions through expressions such as:

```c
packed_position = packed_y | (w19 & 0xffff);
```

The right-side vertex position is calculated using:

```c
right_x = glyph_size + (w19 & 0xffff);
```

Following each glyph or spacing entry:

```c
w19 = glyph_size + (w19 & 0xffff);
```

where the glyph size is obtained from:

```c
*(uint16_t *)x24
```

This identifies `w19` as the horizontal drawing origin and advancing glyph position.

### 13.5 Inferred Register Roles

| Register | Inferred role |
|---|---|
| `w19` | Current horizontal glyph position |
| `x22` | Glyph sequence pointer |
| `x24` | Glyph dimensions and animation parameters |
| `w23` | Animation index |
| `s9` | Vertical positioning base |
| `x25` | Rendering context pointer |

The animation index advances and wraps after index 11.

The per-glyph vertical position incorporates a floating-point value selected using that index, consistent with the visibly animated vertical movement of the letters.

---

## 14. Suspected Root Cause

The inherited helper at `0x10049E620` executes immediately before the glyph rendering loop.

It loads the original horizontal origin from:

```asm
ldrh w19, [x8, #0x40]
```

and increases it by approximately 25 percent:

```asm
lsr w9, w19, #2
add w19, w19, w9
```

The resulting position is passed directly into the glyph loop.

This adjustment moves the complete glyph sequence toward larger horizontal coordinates without reducing its dimensions or spacing.

The leading hypothesis is that the inherited adjustment was appropriate for the intended iPhone layout but places the lettering too far right on the native iPad display.

This hypothesis is supported by static analysis but has not yet been validated through runtime experimentation.

The source and original initialization of `[x8 + 0x40]` remain to be investigated.

---

## 15. Candidate Correction

A minimal experimental correction is to remove the additional 25-percent horizontal adjustment.

Candidate instruction address:

```text
0x10049E628
```

Current instruction:

```asm
add w19, w19, w9
```

Current bytes:

```text
73 02 09 0B
```

Proposed replacement:

```asm
nop
```

Replacement bytes:

```text
1F 20 03 D5
```

### 15.1 Candidate Patch Specification

| Property | Value |
|---|---|
| Address | `0x10049E628` |
| File offset relative to image base | `0x49E628` |
| Expected baseline bytes | `7302090b` |
| Candidate replacement bytes | `1f2003d5` |
| Modification size | 4 bytes |
| Additional code cave required | No |
| Additional hook required | No |

The resulting helper would be:

```asm
ldrh    w19, [x8, #0x40]
lsr     w9, w19, #2
nop
b       0x1004420E0
```

This preserves the original horizontal origin, the remaining helper instruction, and the existing return branch.

The candidate intentionally leaves the now-unused shift instruction intact to minimize the experimental modification.

### 15.2 Expected Behavior

If the suspected root cause is correct, removing the addition should shift the complete loading phrase left.

The expected displacement in the renderer's coordinate units is:

```text
floor(original_x / 4)
```

Glyph dimensions, spacing, sequence, and vertical animation should remain unchanged.

The actual screen displacement depends on the renderer's coordinate transformation.

### 15.3 Validation Status

The candidate has not been applied to an executable or tested on physical hardware.

Removing the complete adjustment may move the phrase farther left than desired. A smaller adjustment or another positioning calculation may be preferable after examining the original initialization logic.

---

## 16. Production Integration Considerations

The candidate instruction lies inside the existing common `safe-area.34` replacement range.

It must not be treated as an unrelated zero-filled code cave or blindly added as an overlapping manifest range.

The final integration approach must account for:

- Existing common patch expectations.
- Profile-specific replacement behavior.
- The common baseline executable.
- The Phase 13 experimental builder.
- Python and TypeScript engine parity.
- Preservation of every existing iPhone profile.
- Deterministic executable hashes.

The Phase 14 correction is intended to affect the iPad profile only.

No decision has yet been made regarding the final manifest representation.

Production integration of Phases 13 and 14 remains deferred until Phase 14 device validation succeeds.

---

## 17. Research Tools

The following Ghidra research scripts were created during this phase:

| Script | Purpose |
|---|---|
| `tools/ghidra/FindLoadingAtlas.java` | Search for fixed-size loading glyph atlas records |
| `tools/ghidra/FindResidesReferences.java` | Inspect localized resource references and surrounding filename registry |
| `tools/ghidra/FindResidesCallers.java` | Identify callers of resource filename lookup functions |

The scripts are read-only research utilities.

The atlas discovery script returned zero matches but remains useful for documenting the investigation and its assumptions.

---

## 18. Next Investigation Steps

The next static investigation should examine the original containing function:

```text
0x100441AFC
```

In particular, inspect the instructions preceding:

```text
0x1004420DC
```

Questions to resolve:

1. Where is `x8` initialized?
2. What structure contains the original horizontal origin at offset `+0x40`?
3. How is this original value calculated or initialized?
4. Does the origin already account for display dimensions or aspect ratio?
5. Does the original position provide an appropriate iPad right margin?
6. Is removing the entire 25-percent adjustment preferable to reducing it?

After resolving these questions, generate a separate Phase 14 experimental executable based on the validated Phase 13 executable.

Because the loading screen is transient, a standalone experimental IPA may be more convenient than modifying executable instructions through LLDB.

The final correction must be validated on physical hardware before permanent integration.

---

## 19. Validation Checklist

### Resource Research

- [x] Inspect cockpit textures for loading artwork.
- [x] Identify candidate system resources from PSP research.
- [x] Locate corresponding iOS TMH resources.
- [x] Extract default and English resources.
- [x] Identify embedded PVR headers and payloads.
- [x] Confirm duplicate first texture.
- [x] Decode shared system texture.
- [x] Identify individual loading glyphs.
- [x] Measure visible glyph coordinates.

### Static Analysis

- [x] Search for conventional cockpit atlas records.
- [x] Search for uniform glyph grid records.
- [x] Document negative atlas search results.
- [x] Identify localized resource string addresses.
- [x] Identify resource filename registry.
- [x] Confirm localized file IDs.
- [x] Identify generic filename lookup and loading functions.
- [x] Inspect inherited loading-related manifest entries.
- [x] Identify existing injected loading helpers.
- [x] Identify the loading glyph rendering loop.
- [x] Identify the horizontal glyph origin register.
- [x] Identify the inherited 25-percent horizontal adjustment.
- [x] Define a candidate four-byte correction.
- [ ] Inspect the original containing function.
- [ ] Identify the original horizontal origin initialization.
- [ ] Determine the preferred final positioning adjustment.

### Experimental Implementation

- [ ] Generate a separate Phase 14 experimental executable.
- [ ] Verify expected original bytes before modification.
- [ ] Verify the resulting instruction encoding.
- [ ] Verify unrelated executable bytes remain unchanged.
- [ ] Record experimental executable SHA-256.
- [ ] Package a separate experimental IPA.

### Physical Device Validation

- [ ] Verify complete "NOW LOADING" phrase visibility.
- [ ] Verify appropriate right-edge alignment.
- [ ] Verify glyph dimensions remain unchanged.
- [ ] Verify glyph spacing remains unchanged.
- [ ] Verify vertical animation remains unchanged.
- [ ] Verify loading background appearance.
- [ ] Verify loading-related map rendering.
- [ ] Verify loading transitions across multiple areas.
- [ ] Verify Phase 13 button corrections remain functional.
- [ ] Verify hamburger correction and edge gestures remain functional.
- [ ] Verify behavior after restarting the game.

### Permanent Implementation

- [ ] Select final permanent correction.
- [ ] Update reproducible patch builder.
- [ ] Add regression tests.
- [ ] Verify permanent executable.
- [ ] Validate permanent build on physical hardware.
- [ ] Update Phase 14 documentation.
- [ ] Commit implementation and research documentation.

### Production Integration

- [ ] Integrate Phase 13 and Phase 14 corrections.
- [ ] Preserve existing iPhone profile behavior and hashes.
- [ ] Verify Python and TypeScript parity.
- [ ] Rebuild production web patcher.
- [ ] Validate production-generated IPA on physical hardware.
- [ ] Update README and production integration documentation.

---

## 20. Conclusion

Phase 14 research successfully identified the shared system texture containing the animated loading glyphs.

Two static atlas discovery attempts returned no matches using the cockpit atlas record format.

The subsequent resource registry investigation established the localized system resource file IDs and generic loading infrastructure.

The most productive investigation path was ultimately provided by the inherited loading-related patch addresses.

Static analysis of the existing injected helpers and the loading glyph rendering loop identified the horizontal position register and an inherited adjustment that increases the initial horizontal origin by approximately 25 percent.

A minimal four-byte candidate correction has been identified at:

```text
0x10049E628
```

The proposed replacement removes the additional horizontal offset while preserving the original origin and glyph rendering logic.

The candidate requires further investigation and physical device validation.

**Phase 14 status: Loading renderer identified. Suspected root cause established through static analysis. Candidate correction identified but not yet tested.**