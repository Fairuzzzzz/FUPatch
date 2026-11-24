# Archived: Cockpit rendering investigation

Historical report originally labeled “Phase 4”. Current status is in
[research.md](../research.md); the curated technical material is in
[technical-reference.md](../technical-reference.md).

**Scope:** Static ARM64 analysis of the Cockpit render dispatcher and direct
rendering helpers. No IPA, executable, manifest, save data, or working game was
modified. Addresses below are unslid Mach-O virtual addresses for the
UUID-verified arm64 executable.

## Runtime observations supplied for this phase

The following are confirmed observations from the user's LLDB session, not
facts independently reproduced in this documentation-only update:

- The Cockpit singleton pointer was `0x10706D500` in that session only.
- `0x10036B960` received that same object pointer.
- `Cockpit + 0x544` read as `0x1000`; `Cockpit + 0x5B7` read as `0`.
- The renderer calculated an X anchor of `24`.
- Its bit-6-clear path called routines using text format strings including
  `"%s"`.
- A confirmed hamburger activation did **not** hit `0x10037D8EC`.

The object pointer and values are session-specific. The accepted-event path at
`0x10037D8EC` is deprioritized for this interaction.

## Render dispatcher

`0x10037EDBC` dispatches on Cockpit state:

1. It examines the byte at `this + 0x11B0`.
2. If that byte is `1`, it reads the selector at `this + 0x11B4`.
3. Selectors `0`–`12` enter the corresponding case below; selectors above
   `12` skip the case dispatch.
4. Afterward, bit 2 of the word at `this + 0x628` gates a shared tail call to
   `0x10036C60C`; otherwise the dispatcher returns.

| Selector | Direct callee | Static classification |
|---:|---:|---|
| 0 | `0x1003A614C` | Helper/state path; not classified as sprite drawing |
| 1 | `0x1003A6A08` | Helper/state path; not classified as sprite drawing |
| 2 | `0x10036B960` | Text-heavy HUD path; runtime confirmed for the Cockpit object |
| 3 | `0x10037F8F0` | Repeated text/layout drawing calls |
| 4 | `0x10037F790` | List/control path; draw responsibility uncertain |
| 5 | `0x10037EF14` | Text/list rendering path |
| 6 | `0x10037F06C` | Mixed UI drawing; includes typed element rendering and text |
| 7 | `0x10036C5F8` | Tail-dispatches to `0x1003AC858` |
| 8 | `0x1003A8024` | Helper called with constants `0x116` and `0x117` |
| 9 | `0x10036A04C` | Mixed element/layout rendering |
| 10 | `0x10037F530` | Text-heavy drawing path |
| 11 | `0x10037FB84` | Text/list drawing path |
| 12 | `0x10037F890` | Text/layout helper |

These labels describe visible control flow and helper use; the binary does not
provide symbols proving the user-facing name or purpose of every case.

## Sprite and element-rendering candidates

### 1. `0x10036A270` — Cockpit element descriptor dispatcher

**Priority: highest.**

- **Caller and condition:** `0x10036B960` calls it at `0x10036BC10` on the
  bit-6-clear path, which matches the supplied runtime value
  `Cockpit + 0x544 = 0x1000`. The other call at `0x10036BAE8` is in the
  bit-6-set path.
- **Evidence:** The function reads a descriptor through `x1`, including a
  type byte at descriptor offset `+0xB` and 16-bit fields at offsets
  `+0`, `+2`, `+4`, and `+6`. It applies display scale and branches on the
  descriptor type. Some branches call the atlas renderer
  `0x10036B42C`; another path calls a quad/primitive helper. It also invokes
  text-related helpers. This is evidence for a mixed, descriptor-driven UI
  renderer, not proof of a hamburger-specific object.
- **Unknown:** Which descriptor represents the hamburger; whether its touch
  target reuses the descriptor's geometry; and which state selector draws it.

**Targeted experiment:** Resolve addresses from the loaded image and stop once
at the descriptor-dispatch entry only when called from the confirmed
`0x10036B960` bit-6-clear callsite:

```lldb
script t=lldb.debugger.GetSelectedTarget(); m=next(t.GetModuleAtIndex(i) for i in range(t.GetNumModules()) if t.GetModuleAtIndex(i).GetFileSpec().GetFilename()=="MH Unite"); assert m.GetUUIDString().replace("-","").lower()=="58cc55c760ca3196b5d20c2aeb64b32b"; rt=lambda a:m.ResolveFileAddress(a).GetLoadAddress(t); err=lldb.SBError(); cockpit=t.GetProcess().ReadUnsignedFromMemory(rt(0x100732fc0),8,err); assert err.Success(); bp=t.BreakpointCreateByAddress(rt(0x10036a270)); bp.SetCondition("((unsigned long long)$x0 == 0x%X) && ((unsigned long long)$x30 == 0x%X)"%(cockpit,rt(0x10036bc14))); bp.SetOneShot(True); print("bp",bp.GetID(),"Cockpit",hex(cockpit))
```

At the stop, record `x1`–`x5`, the backtrace, and the descriptor bytes. The
condition compares against the runtime singleton pointer, not the historical
`0x10706D500` value.

### 2. `0x10036B42C` — atlas-sprite quad renderer

**Priority: high; nested under candidate 1.**

- **Caller and condition:** `0x10036A270` calls it at `0x10036A310` for
  selected descriptor-type masks. Those branches pass atlas index `0x40` or
  `0x9E` in `x6`.
- **Evidence:** The function indexes a 12-byte record table at
  `0x10072E0FC` using `x6`, reads source-region fields, scales destination
  coordinates, builds multiple quad/strip commands, and submits them through
  `0x10037662C`, `0x100377E34`, `0x100375FD4`, and `0x100377D80`. This is
  strong evidence for atlas-based sprite rendering.
- **Unknown:** The visual identity of atlas entries `0x40` and `0x9E`, and
  whether either one is the hamburger.

**Targeted experiment:** Stop once at the sprite renderer entry only when it
is called from the sprite branch in `0x10036A270`, and only for the two atlas
indices seen in that branch:

```lldb
script bp2=t.BreakpointCreateByAddress(rt(0x10036b42c)); bp2.SetCondition("((unsigned long long)$x0 == 0x%X) && ((unsigned long long)$x30 == 0x%X) && (((unsigned int)$w6 == 0x40) || ((unsigned int)$w6 == 0x9e))"%(cockpit,rt(0x10036a314))); bp2.SetOneShot(True); print("bp",bp2.GetID())
```

At the stop, record `x1`–`x6` and `bt 8`. `x1`–`x4` are the candidate
destination rectangle; `x6` is the atlas selector. A hit identifies an
atlas-sprite draw in the observed Cockpit branch, not necessarily the hamburger.

### Deprioritized alternate panel path (not in the priority list)

`0x10037A9B0` is a fixed multi-part atlas/panel renderer. It uses a separate
table based at `0x10072E7D8` and emits several quads. Its typed dispatcher is
`0x1003736E4`: descriptor type `4` reaches `0x37A9B0`; types `0`/`2` and
`1`/`3` reach `0x36B42C` with different atlas indices. The descriptor
dispatcher is called in other render states, including cases routed through
`0x37F06C` and `0x37FB84`. This looks more like panel/skin artwork than a
hamburger glyph, so it is not in the first two probes.

The helper `0x100377A84` constructs a generic render-queue quad and submits it
through `0x1001F56A8`; no specific hamburger asset or selector was identified.
It remains a possible background/primitive path, not a prioritized icon
candidate.

## Shared layout and remaining uncertainty

The strongest static link is that the confirmed text-heavy renderer
`0x10036B960` passes its Cockpit `this` pointer and layout data to
`0x10036A270`, which can route typed descriptors into `0x10036B42C`. The
sprite renderer consumes position/size arguments and atlas source-region data.
This supports a shared Cockpit element-rendering pipeline.

No evidence yet shows that the hamburger uses this descriptor, atlas entry, or
the same coordinates for hit-testing. The user-reported accepted-event
breakpoint miss at `0x10037D8EC` further deprioritizes that generic transition
path; it does not rule out other event dispatchers.

**Success criterion for the next capture:** identify a descriptor/atlas
selector and destination rectangle that correspond visually to the
half-visible hamburger, then determine whether the touch path references that
same element or geometry. Do not infer identity from the shared Cockpit object
alone, and do not patch until this link is demonstrated.

## Phase 4 — Cockpit UI Rendering and Visual Identification

### Objective

Identify the rendering path responsible for the always-visible hamburger icon in Monster Hunter Freedom Unite iOS v1.00.11, with the eventual goal of moving it horizontally toward the physical right edge of the iPad display.

The intended modification must preserve the icon's size, vertical position, partially visible appearance, and functional touch target.

**Status:** The hamburger rendering path remains unidentified. However, we successfully traced and experimentally identified a menu navigation graphic.

### Environment

- Device: iPad Air 11-inch M2 (`iPad14,8`)
- OS: iPadOS 18.7.3
- Target binary: `MH Unite`
- Mach-O UUID: `58CC55C7-60CA-3196-B5D2-0C2AEB64B32B`
- Observed process ID: `29337`
- Observed ASLR slide: `0xF78000`
- Cockpit singleton pointer: `0x10706D500`

Runtime addresses and pointers are specific to the observed debugging session. Resolve unslid addresses against the loaded module in future sessions.

### 1. Confirmed Cockpit Descriptor Rendering

An LLDB breakpoint at unslid `0x10036A270` successfully captured a call from the Cockpit renderer at `0x10036B960`.

The descriptor at `0x16F78ECC8` contained:

| Field | Value |
|---|---|
| `+0x00` | 1488 |
| `+0x02` | 112 |
| `+0x04` | 464 |
| `+0x06` | 448 |
| `+0x0B` | Type 1 |

The dispatcher uses the low nibble of the type byte:

- Types 0, 2, 4, 6 select atlas index `0x40`.
- Types 1, 3, 5 select atlas index `0x9E`.

Type 1 was confirmed to invoke atlas renderer `0x10036B42C`.

The associated atlas record for index `0x9E` contained:

`0000 00E8 0010 0008 8001 0000`

This path appears compatible with multi-part panel rendering, but its specific visual identity was not established.

### 2. Discovery of the "Menu" Text Renderer

A separate invocation of the descriptor renderer was captured with:

- Descriptor pointer: `0x16F78ECF8`
- Additional data pointer: `0x16F78ED28`
- Caller return address: unslid `0x1003A5A04`

The descriptor contained:

| Field | Value |
|---|---|
| `+0x00` | 1821 |
| `+0x02` | 112 |
| `+0x04` | 256 |
| `+0x06` | 288 |
| `+0x0B` | Type 3 |

The additional data contained the null-terminated string:

`20 20 4D 65 6E 75 00`

This decodes to `"  Menu"`.

The associated renderer begins at unslid `0x1003A5904` (runtime `0x10131D104`).

The Cockpit dispatcher at `0x10037EDBC` calls this renderer when the byte at `Cockpit + 0x11B0` equals zero.

Observed Cockpit state:

| Offset | Value |
|---|---|
| `+0x11B0` | `0x00` |
| `+0x11B4` | `0x02` |
| `+0x11B5` | `0x01` |

The function also constructs a page or selection indicator using the format string `%d/%d`.

**Interpretation:** The rendering path is associated with the menu UI. The presence of `"  Menu"` does not establish that the function renders the hamburger icon.

### 3. Additional Menu-Associated Graphics Path

The Menu renderer calls another UI function at:

`0x10036C870`

This function formats additional text and selects between a direct graphics call and an animated graphics wrapper.

The following path was confirmed dynamically:

```text
0x10037EDBC  Cockpit UI dispatcher
      |
      v
0x1003A5904  "Menu" renderer
      |
      v
0x10036C870  Additional UI renderer
      |
      v
0x100379100  Animation wrapper
      |
      v
0x1003788B8  Graphics helper
      |
      v
0x100378D6C  Lower-level graphics helper
```

The animation wrapper uses `sin()` to calculate an 8-bit rendering parameter. Its exact visual meaning remains unconfirmed.

The observed graphics-helper arguments were:

| Argument | Value |
|---|---:|
| `x1` | 1821 |
| `x2` | 134 |
| `x3` | 228 |
| `x4` | 32 |
| `x5` | 145 |
| `x6` | 32 |
| `x7` | 240 |

### 4. Coordinate Transformation

The helper at `0x100378C40` calculates three output coordinates using input anchors and a game-provided scale factor.

Observed outputs:

| Output | Value |
|---|---:|
| Vertical coordinate | 120 |
| Horizontal start | 1822 |
| Horizontal end | 2161 |

The horizontal span between the calculated endpoints is 339 internal coordinate units.

These values are not confirmed physical screen coordinates.

A subsequent graphics operation at `0x100378D6C` received:

| Argument | Value |
|---|---:|
| X | 1822 |
| Y | 120 |
| Geometry argument 1 | 67 |
| Geometry argument 2 | 67 |
| Atlas index | 564 (`0x234`) |

### 5. Atlas Record 564

The atlas record was found at runtime address `0x1016A7B6C`.

Its six 16-bit fields were:

| Offset | Value |
|---|---|
| `+0x00` | `0x008A` |
| `+0x02` | `0x00B9` |
| `+0x04` | `0x0017` |
| `+0x06` | `0x0017` |
| `+0x08` | `0x8004` |
| `+0x0A` | `0x000B` |

The equal dimension fields initially made this a plausible small-icon candidate.

The visual experiment below identified the relevant element more precisely.

### 6. Reversible Runtime Position Experiment

A repeating breakpoint was installed at unslid address:

`0x100378D6C`

Observed breakpoint ID: `10`.

It was restricted to the call returning to runtime address `0x1012F0A3C` with atlas index 564 at incoming stack offset `+0x08`.

```lldb
breakpoint modify 10 --condition '($lr == 0x1012F0A3C) && (*(unsigned int *)($sp + 8) == 564)'
```

The Python breakpoint action replaced the incoming X coordinate:

```python
frame.FindRegister("x1").SetValueFromCString("1622")
```

Automatic continuation allowed repeated matching calls to execute with the modified coordinate.

**Original X:** 1822  
**Modified X:** 1622  
**Translation:** −200 internal coordinate units

#### Observed visual result

The user confirmed that the **small circular background behind the menu's left navigation arrow moved horizontally**.

The hamburger icon did not move.

This is the first confirmed visual identification of a specific graphics call through runtime coordinate modification.

The experiment demonstrates that the background graphic can be repositioned independently at this rendering callsite.

It does **not** establish that atlas record 564 is exclusively associated with this graphic or that its interactive hitbox moves with it.

#### Reversal

The temporary effect can be disabled by interrupting the process and disabling breakpoint 10:

```lldb
process interrupt
breakpoint disable 10
continue
```

This experiment does not modify the IPA, executable on disk, repository files, or save data.

### 7. Conclusions

**Confirmed findings**

1. The Cockpit UI uses a shared descriptor renderer at `0x10036A270`.
2. The renderer supports multiple descriptor types and atlas-selection paths.
3. A Cockpit-controlled rendering path constructs and renders `"  Menu"` text.
4. The associated UI renderer calculates scaled positions and invokes lower-level graphics functions.
5. A targeted, repeating LLDB coordinate modification successfully moved the left navigation arrow's circular background.
6. The hamburger icon remained unaffected.

**Unresolved questions**

- Which function draws the hamburger graphic?
- Which atlas entry or texture contains the hamburger?
- Is its position calculated by Cockpit code or a separate UI layer?
- Where is the hamburger's touch target defined?
- Can the visual position and input region be translated consistently without modifying the rest of the UI?

### 8. Recommended Next Investigation

Use the **menu-closed state**, where the hamburger remains visible, as the baseline.

Prioritize identifying rendering calls directly associated with that always-visible control.

Avoid repeating investigations of the now-identified menu navigation-arrow background unless needed for comparison.

A successful next milestone is a persistent, reversible LLDB coordinate modification that visibly moves the **hamburger itself**, without moving unrelated UI elements.

After that, investigate its touch-input path separately before implementing a permanent patch.

### 10. Offline asset and ResourceManager follow-up — November 24, 2026

This is a static, offline update using REA 6.10.1 / Ghidra 12.2 on the
UUID-verified arm64 executable (SHA-256
`25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`). It
does not replace or revise the historical runtime observations above.

#### Confirmed asset evidence

The IPA member `Payload/MH Unite.app/cockpit/cock.tmh` has SHA-256
`e711ab9a273168f80e0d2f9e3548fd5ae26e025c33671ec93595fcb7d8848cd6`. Five
embedded PVR v2 textures were reconstructed and decoded as standard PVRTC
4-bpp (`flags=0x8019`, pixel type `0x19`):

| Texture | Dimensions |
|---|---:|
| `cock-1` | 1024×1024 |
| `cock-2` | 512×512 |
| `cock-3` | 2048×2048 |
| `cock-4` | 1024×1024 |
| `cock-5` | 2048×2048 |

The hamburger is visually present in `cock-5`. Its tight visible bounds are
**(X=1804, Y=604, width=187, height=119)**. The decoder, intermediate files,
and contact sheet were confined to temporary storage; the IPA, `.tmh`, and
repository game binaries were not modified.

#### Atlas candidates and the scale hypothesis

Four 12-byte records at the table based at `0x10072E0FC` have these fields:

| Index | Record address | X | Y | W | H | Flags | Resource field |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 204 | `0x10072EA8C` | 224 | 64 | 16 | 16 | `0x8000` | 11 |
| 205 | `0x10072EA98` | 240 | 64 | 16 | 16 | `0x8000` | 11 |
| 208 | `0x10072EABC` | 224 | 80 | 16 | 16 | `0x8000` | 11 |
| 209 | `0x10072EAC8` | 240 | 80 | 16 | 16 | `0x8000` | 11 |

**Hypothesis, not a confirmed engine mapping:** interpreting the coordinates
at 8× scale makes these four adjacent cells cover `(1792, 512, 256, 256)` in
`cock-5`, which contains the visible hamburger bounds. The cells also include
surrounding image content, including part of an adjacent graphic. The
coordinate fit does not prove that the game samples this table against
`cock-5` with that scale.

The records are confirmed as four separate 16×16 table entries laid out on a
regular grid. Existing evidence does **not** establish whether they are texture
tiles, independent sprites, or another form of atlas subregion; nor that the
four are drawn together as the hamburger.

#### ResourceManager behavior established by Ghidra

- `FUN_100375FD4` and the table-record loader `FUN_1003762B4` use the high bit
  of the flags to select the ResourceManager path. For a candidate record,
  flags `0x8000` yield texture sub-index `flags & 0x0FFF = 0`; resource field
  `11` is passed to `FUN_1002C2138`.
- `FUN_1002C2138` searches ResourceManager entries by integer key and returns
  the associated pointer. Its body does not provide the resource filename or
  source package.
- `FUN_10035EE00` / `FUN_10035EE14` access or populate the Cockpit texture
  cache slot selected by `resource_id & 0xF`; ID 11 therefore selects slot 11.
  `FUN_10035D968(resource, 0)` retrieves the selected sub-index.

This proves the table records request **ResourceManager key 11, texture
sub-index 0**. It does **not** prove key 11 is `cock.tmh`, or that sub-index 0
is `cock-5`. The relationship between the ResourceManager registration entry
and the `.tmh` member remains unresolved.

#### Rendering-call limits and excluded paths

The existing Ghidra analysis identifies generic table-backed helpers:

- `FUN_10036C920` indexes the table with its `param_6` argument and submits
  draw data through `FUN_10037D418`.
- `FUN_100375804` indexes it using the high 32 bits of its ninth argument and
  submits draw data through `FUN_1002195A4`.

Ghidra’s enumerated direct callers of these two functions did not establish a
call selecting indices 204, 205, 208, or 209. This bounded check does not
exclude other table-indexing helpers, indirect calls, or unresolved dynamic
indices. **The hamburger-specific draw call and touch region remain
unidentified.**

Previously tested or excluded leads remain distinct from this asset match:

- Atlas index 564 was visually identified as the circular background behind
  the left navigation arrow; changing it moved that background, not the
  hamburger.
- The generic rectangle-test candidate at `0x100460D44` and the
  accepted-event branch at `0x10037D8EC` had no hits in the confirmed
  hamburger activation.
- PVRTexToolCLI was unavailable, and ImageMagick, FFprobe, and `sips` did not
  decode these PVR files. `texture2ddecoder` was avoided because of its
  documented macOS crash risk. The temporary PowerVR decoder succeeded.

#### Current next step

Trace the `cock.tmh` resource-registration/loading path and map its registered
ResourceManager key(s) and texture sub-indices to the five embedded PVR
textures. Specifically, determine whether key 11 is `cock.tmh` and which
sub-index, if any, corresponds to `cock-5`. Only after that link is established
should the atlas candidates be used to pursue the icon-specific draw call.

### Research Integrity

These findings describe observed runtime behavior and static disassembly from the current investigation.

Do not interpret candidate geometry fields, atlas metadata, or speculative graphics semantics as established facts without additional validation.

Preserve the existing baseline IPA and research documents. Any future permanent patch should be developed and tested separately from the working baseline.

# Phase 4 — Menu Visual Layout and Hitbox Independence

## Summary

**Status: Experimentally verified**

We successfully modified the Monster Hunter Freedom Unite iOS menu's rendering coordinates through LLDB.

Changing the resolved X coordinate from `1821` to `1221` moved the **entire menu visually** by 600 coordinate units to the left.

However, the menu's touch hitboxes remained at their original positions.

This demonstrates that modifying the tested render-time layout coordinate does not automatically update the corresponding interaction regions.

## 1. Environment

| Property | Value |
|---|---|
| Application | Monster Hunter Freedom Unite iOS v1.00.11 |
| Device | iPad Air M2 |
| Operating system | iPadOS 18.7.3 |
| Process ID | `29337` |
| Mach-O UUID | `58cc55c760ca3196b5d20c2aeb64b32b` |
| ASLR slide | `0xF78000` |
| Runtime image base | `0x100F78000` |
| Debugger | LLDB |

All experiments modified temporary process memory. No IPA or executable changes were made.

Runtime addresses are valid for the recorded process and must be recalculated if the ASLR slide changes.

## 2. Relevant Functions and Addresses

| Function / location | Unslid address | Runtime address |
|---|---|---|
| Cockpit dispatcher | `0x10037EDBC` | `0x1012F6DBC` |
| Menu renderer | `0x1003A5904` | `0x10131D104` |
| Coordinate resolver | `0x10039DAD4` | `0x1013152D4` |
| Menu coordinate consumption | `0x1003A51C0` | `0x10131D1C0` |
| UI descriptor builder | `0x10039DB98` | `0x101315398` |
| Lower-level graphics helper | `0x100378D6C` | `0x1012F0D6C` |

### Layout entry 98

The Menu renderer requests layout entry `0x62` (decimal 98).

Table record address:

`0x1015405B0`

Recorded bytes:

`63 00 00 00 F6 FE 46 00`

Decoded fields:

- Base-position index: `99`
- X offset: `-266`
- Y offset: `+70`

The coordinate resolver combines a base position with scaled offsets to produce the coordinates consumed by the Menu renderer.

### Observed resolved coordinates

| Coordinate | Original value |
|---|---|
| X | `1821` |
| Y | `112` |

The returned coordinates are stored in the Menu renderer's stack frame.

At runtime `0x10131D1C0`, the relevant instructions are:

```asm
ldrsh w4, [sp, #0x1c]  ; Y coordinate
ldrsh w3, [sp, #0x1e]  ; X coordinate
```

This provides a convenient location for reversible coordinate experiments.

## 3. Experiment A — Individual Sprite Movement

**Target:** Lower-level graphics helper `0x100378D6C`

The earlier breakpoint targeted a draw operation with:

- Atlas index: `564` (`0x234`)
- Geometry: `67 × 67`
- Original X argument: `1822`
- Modified X argument: `1622`

### Observed result

Moving this draw operation shifted the **circular background of the menu's left navigation arrow**.

The arrow glyph itself did not follow the background movement.

The corresponding touch hitbox remained at its original location.

**Conclusion:** This graphics call controls an individual visual component rather than the entire interactive navigation control.

## 4. Experiment B — Entire Menu Visual Movement

**Target:** Menu renderer at runtime `0x10131D1C0`

Breakpoint ID: `14`

The breakpoint intercepts execution immediately after the coordinate resolver returns, before the resolved coordinates are loaded into registers for subsequent rendering operations.

### Original and modified coordinates

| Property | Original | Modified |
|---|---:|---:|
| X coordinate | 1821 | 1221 |
| Y coordinate | 112 | 112 (unchanged) |
| X displacement | — | −600 |

### Breakpoint configuration

The experiment used the following condition:

```lldb
breakpoint modify 14 --condition '*(unsigned long long *)($x29 + 8) == 0x1012F6E24'
```

This compares the saved return address rather than the live `x30` register, which may have been overwritten by an intervening function call.

The working breakpoint command was:

```lldb
breakpoint command add -s python -o 'p=lldb.debugger.GetSelectedTarget().GetProcess(); fs=[th.GetFrameAtIndex(0) for th in p if th.GetStopReason()==lldb.eStopReasonBreakpoint and th.GetNumFrames()>0]; fs=[f for f in fs if f.GetPC()==0x10131D1C0]; e=lldb.SBError(); n=p.WriteMemory(fs[0].GetSP()+0x1e,(1221).to_bytes(2,"little"),e) if fs else 0; print("Layout X write:",n,"bytes; success:",e.Success())' 14
```

The command selects a frame stopped at the target PC and writes a two-byte little-endian value to the stack location containing X.

### Successful LLDB verification

Recorded callback output:

```text
Layout X write: 2 bytes; success: True
```

Breakpoint stop:

```text
thread #4, stop reason = breakpoint 14.1
PC = 0x10131D1C0
```

Memory verification:

```lldb
memory read --format d --size 2 --count 1 `$sp+0x1e`
```

Result:

```text
0x16f78ecee: 1221
```

This confirms that the intended stack coordinate was successfully modified during execution.

### Repeating the modification

After validation, the breakpoint was configured to continue automatically:

```lldb
breakpoint modify --auto-continue true 14
continue
```

This reapplies the modified coordinate on subsequent matching breakpoint hits.

### Observed visual result

**The entire menu's visual content moved.**

Unlike Experiment A, which affected only the arrow's circular background, this higher-level coordinate change visibly displaced the menu as a whole.

### Observed interaction result

**The menu's touch hitboxes did not move with the visual elements.**

This was observed through user interaction with the displaced menu.

The visual displacement therefore does not constitute a complete relocation of the interactive interface.

## 5. LLDB Callback Troubleshooting

Two earlier Python callbacks failed or did not modify the intended coordinate.

### Attempt 1 — `lldb.frame`

The command relied on:

```python
f = lldb.frame
```

It repeatedly generated:

```text
AttributeError: 'NoneType' object has no attribute 'GetThread'
```

The callback did not have a valid frame through this variable.

### Attempt 2 — Selected thread

The next callback used:

```python
p.GetSelectedThread().GetFrameAtIndex(0)
```

Although breakpoint 14 triggered, inspection showed that the coordinate remained `1821`.

The selected thread was not a reliable substitute for the actual breakpoint-hit thread.

### Working approach

The successful callback searched process threads for a breakpoint stop reason and matched the current frame's PC against `0x10131D1C0`.

This located the appropriate frame in the observed execution.

**Important:** The callback was verified in this debugging session; it is not a universal guarantee for every LLDB thread-selection or simultaneous-stop scenario.

## 6. Interpretation

The combined experiments establish three useful facts:

1. Individual menu graphics can be repositioned by modifying arguments to lower-level drawing functions.
2. A higher-level resolved layout coordinate can control the visual position of the entire menu.
3. The tested drawing-coordinate modifications do not reposition the corresponding touch hitboxes.

The evidence is consistent with rendering and interaction using independently calculated or stored positioning information.

However, we have **not yet identified the function responsible for constructing or evaluating the menu hitboxes**.

It is therefore premature to conclude that the game universally uses two separate layout tables.

## 7. Remaining Questions

The next investigation should determine:

- Where the menu's interactive rectangles or touch regions are defined.
- Whether input handling retrieves layout entry 98 independently.
- Whether interaction coordinates are calculated from another table, from cached geometry, or from hardcoded constants.
- Whether a shared upstream value can reposition both visuals and hitboxes.
- How these findings relate to the always-visible hamburger menu control.

The hamburger control remains the ultimate target; the opened menu serves as an experimental case for understanding the UI architecture.

## 8. Reverting the Experiment

To stop repeatedly modifying the layout coordinate:

```lldb
process interrupt
breakpoint disable 14
continue
```

The original layout is recalculated during subsequent rendering calls.

No permanent modification to the application binary is required.

## 9. Final Finding

**Confirmed:** The menu's visual position can be changed at a high-level coordinate-consumption point without changing its hitboxes.

**Not yet resolved:** The input-side coordinate source required to relocate the interactive regions.

**Next research direction:** Trace menu hitbox calculation and determine its relationship, if any, to the existing layout-coordinate resolver.
