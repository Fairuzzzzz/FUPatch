# MHFU UI Reverse-Engineering Technical Reference

This is the canonical detailed reference for the current research summary in
[research.md](research.md). Historical reports and raw logs remain in
[archive/](archive/) and [logs/](logs/); they preserve the original sequence of
observations, including inconclusive attempts.

## Target and analysis conventions

- Game: Monster Hunter Freedom Unite / `MH Unite`, iOS 1.00.11.
- Arm64 executable UUID: `58cc55c760ca3196b5d20c2aeb64b32b`.
- Working executable SHA-256:
  `25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`.
- Offline static analysis: REA 6.10.1, Ghidra 12.2, Intel macOS (`x86_64`).
- Addresses below are unslid Mach-O virtual addresses unless specified.
  Runtime pointers, PIDs, and slides are session-specific and must not be
  reused.

## Cockpit texture extraction

The IPA member `Payload/MH Unite.app/cockpit/cock.tmh` has SHA-256
`e711ab9a273168f80e0d2f9e3548fd5ae26e025c33671ec93595fcb7d8848cd6`. Five
embedded PVR v2 textures were reconstructed and decoded as PVRTC 4-bpp
(`flags=0x8019`, pixel type `0x19`):

| Extracted texture | Dimensions |
|---|---:|
| `cock-1` | 1024×1024 |
| `cock-2` | 512×512 |
| `cock-3` | 2048×2048 |
| `cock-4` | 1024×1024 |
| `cock-5` | 2048×2048 |

The historical decoder was Imagination/PowerVR's `PVRTDecompressPVRTC` C++ routine through
a temporary wrapper. The PNGs and a labeled contact sheet were kept in
temporary storage. The IPA, `.tmh`, and game binaries were not modified.

Previously unsuccessful or excluded conversion paths:

- `PVRTexToolCLI` was absent during the earlier conversion attempt; the later corrected extraction used PVRTexTool.
- ImageMagick, FFprobe, and macOS `sips` did not decode the PVR files.
- `texture2ddecoder` was not used in-process because its README warns of
  possible macOS crashes.
- No decoder dependency was installed in the project.

### Revised extraction and limitations

PVRTexTool 5.7.1 (Build `26.1@f61b9fab2511`), PVRTexLib v5.7.1, Qt 6.8.1. Spatial arrangement appears correct, but visible color abnormalities remain. Use unscaled PNGs as provisional spatial references only; fixing color is not a priority unless it affects geometry or identification. Exact extraction commands/settings, revised dimensions and output hashes are not recorded. The dimensions table above is historical. The prior `(1804,604,187,119)` bounds and 2× vertical stretching convention are superseded.

| Artwork in `cock-5` | Visible bounds (X, Y, W, H) | Composition |
|---|---|---|
| Large hamburger | `(890, 593, 102, 142)` | Hamburger |
| Small hamburger | `(1544, 324, 43, 60)` | Hamburger |
| Large left navigation background | `(556, 745, 84, 84)` | Background only |
| Small left navigation button | `(1856, 4, 60, 60)` | Background plus arrow |

Large/small hamburger ratios: 102/43 ≈ 2.372 and 142/60 ≈ 2.367; navigation ratio 84/60 = 1.4. Navigation composition differs. Device association is a hypothesis, not verified selection behavior.

## Hamburger source bounds and atlas records

The corrected visible bounds in `cock-5` are **(X=890, Y=593, width=102, height=142)**. These are not necessarily full sprite bounds. The earlier `(1804, 604, 187, 119)` measurement is superseded.

Four 12-byte records from the atlas table at `0x10072E0FC` were former candidates (historical evidence only):

| Index | Record address | X | Y | W | H | Flags | Resource field |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 204 | `0x10072EA8C` | 224 | 64 | 16 | 16 | `0x8000` | 11 |
| 205 | `0x10072EA98` | 240 | 64 | 16 | 16 | `0x8000` | 11 |
| 208 | `0x10072EABC` | 224 | 80 | 16 | 16 | `0x8000` | 11 |
| 209 | `0x10072EAC8` | 240 | 80 | 16 | 16 | `0x8000` | 11 |

The four rectangles are adjacent cells in the table's regular 16-unit grid. Under the hypothetical 8× mapping, their union is `(1792, 512, 256, 256)`. This overlapped the incorrectly decoded image's hamburger bounds but does not overlap the corrected bounds. Their original justification is invalid; they are unsupported hamburger candidates, not universally excluded by runtime evidence.

Under the same unverified conversion, the corrected bounds in table units would be `(111.25, 74.125, 12.75, 17.75)` (X approximately 111–124, Y approximately 74–92). This is historical only; the current leading 4× candidate is described below. This was the state of the historical investigation; later runtime evidence confirms index 527.

The records are four distinct entries. Their semantics, whether they render together, the table's relationship to `cock-5`, and the coordinate conversion remain unverified.

## ResourceManager and texture selection

Relevant Ghidra functions:

| Function | Confirmed behavior |
|---|---|
| `FUN_100375FD4` | For flags with bit 15 set, looks up the resource field through the ResourceManager, uses the low 12 flag bits as texture sub-index, accesses/caches the Cockpit texture, then binds the selected sub-index. |
| `FUN_1003762B4` | Consumes a table record; the flagged path uses its resource field and low 12 flag bits in the same ResourceManager/Cockpit texture path. |
| `FUN_1002C2138` | Searches ResourceManager entries by integer key and returns the associated pointer. The function does not expose a filename or package path. |
| `FUN_10035EE00` / `FUN_10035EE14` | Look up or populate a Cockpit texture-manager cache slot selected by `resource_id & 0xF`; key 11 maps to slot 11. |
| `FUN_10035D968` | Retrieves a texture by sub-index from the loaded resource. |

For former candidate records 204/205/208/209, Ghidra establishes **ResourceManager
key 11 and texture sub-index 0**. It does not establish that key 11 is
`cock.tmh`, or that sub-index 0 is `cock-5`. The `.tmh` member's presence and
its five decoded textures do not provide that registration crosswalk. Key 11 and sub-index 0 are not established as the hamburger's resource or texture selection.

## Rendering helpers and call-site limits

| Function | Table selection / draw path |
|---|---|
| `FUN_10036C920` | Uses its `param_6` value as the table index; submits draw data through `FUN_10037D418`. |
| `FUN_100375804` | Uses the high 32 bits of its ninth argument as the table index; submits draw data through `FUN_1002195A4`. |
| `FUN_10036B42C` | The descriptor renderer's atlas-sprite helper; the existing runtime branch passed indices `0x40` or `0x9E`. |
| `FUN_10036A270` | Descriptor-driven Cockpit dispatcher; selected descriptor types reach `FUN_10036B42C`. |
| `FUN_10037A9B0` | Alternate panel/skin path with a separate table at `0x10072E7D8`; lower-priority hamburger candidate. |

The historical search of enumerated direct callers of `FUN_10036C920` and `FUN_100375804` did not
establish a selection of indices 204, 205, 208, or 209. This is a bounded
direct-call result; it does not rule out other table-indexing helpers,
unresolved dynamic indices, or indirect calls. At that stage the hamburger-specific draw call was unknown. Later runtime confirmation is documented below.

## Manual Ghidra investigation — November 24, 2026

Standalone GUI project `FUPatch4iPad`, Ghidra 12.2 on Intel macOS, using JDK 25 from a custom installation. The executable was extracted read-only from the Mac baseline IPA into `~/Code/FUPatch4iPad-analysis/MH Unite`. Terminal `file` reported Mach-O 64-bit arm64, and `shasum -a 256` matched the documented hash. Ghidra imported AARCH64 little-endian with minimum address `0x100000000`. Auto-analysis reported `ObjcMessageAnalyzer.findMessages` (`ArrayIndexOutOfBoundsException`, line 326) and missing `os/mac_x86_64` native demangler components; 1,381 messages were truncated. Analysis is usable for the inspected functions but not assumed complete.

### Observed decompiled behavior

- `0x100375FD4`: bit 15 clear selects CockpitTextureManager via `FUN_10035EE3C`, sub-index 0; bit 15 set selects ResourceManager key (third argument) and sub-index `flags & 0xFFF`. Both paths call `FUN_100208D14` to bind the selected texture. No source coordinate calculation here.
- `0x1003762B4`: reads six 16-bit fields. Packs dimensions as `0xF2000000 | ((H & 0xFFF) << 12) | (W & 0xFFF)` and position as `((Y & 0xFFF) << 12) | (X & 0xFFF)`. Calls `FUN_100208DC0`, `FUN_100208E10`, and texture binding. No source scaling observed in packing.
- `0x100208DC0`: links command blocks by copying existing command words to the end of the incoming block, encoding its address into two words and updating the pointer at `Ge + lane*8 + 0x170`. Does not interpret the rectangle.
- `0x10036C920`: uses `param_6 * 0xC` with base `0x10072E0FC`. Reads X/W as signed shorts and Y/H as unsigned shorts in the shown decompilation; flags/resource at offsets 8/10. Constructs source corners using X+W and Y+H, without visible source scaling. Destination endpoints are formed separately from `param_2/param_3` plus scaled `param_4/param_5`, using `FUN_100359D8C`; submits via `FUN_10037D418`. Destination semantics are provisional. Downstream texture-coordinate interpretation remains unverified.

### Atlas records and proposed 4× mapping

| Index | Unslid record address | Atlas rectangle | Predicted pixels (4×) | Flags | Key |
|---:|---|---|---|---|---:|
| 527 (`0x20F`) | `0x10072F9B0` | `(221,147,27,38)` | `(884,588,108,152)` | `0x8004` | 11 |
| 564 (`0x234`) | `0x10072FB6C` | `(138,185,23,23)` | `(552,740,92,92)` | `0x8004` | 11 |

Record 564 raw bytes: `8A 00 B9 00 17 00 17 00 04 80 0B 00`. These match the six fields in the archived runtime experiment at `0x100378D6C` (index at incoming stack +8; X changed in x1), providing independent corroboration of the reference record. Its predicted rectangle contains the measured background with margins L/R/T/B = 4/4/5/3 pixels. Record 527 contains the large hamburger with margins 6/0/5/5 pixels; padding is a plausible explanation, not proven. Both have resource key 11 and sub-index 4, consistent with zero-based fifth texture selection if extraction order matches runtime order. Registration crosswalk is still unverified.

### Bounded search and result

Ghidra memory search `04 80 0B 00` returned contiguous flag addresses `0x10072F9B8`–`0x10072FD9C` at stride 12. The read-only Java script `FindHamburgerAtlas.java` scanned corresponding record starts `0x10072F9B0`–`0x10072FD94` (indices 527–610 inclusive). It filtered flags `0x8004`, resource 11, multiplied X/Y/W/H by four, and tested rectangle overlap against all four measured targets. User-reported console output:

```text
FindHamburgerAtlas.java> Running...
Large hamburger | Index 527 | Address 0x10072F9B0 | Atlas (221,147,27,38) | Pixels (884,588,108,152)
Large arrow background | Index 564 | Address 0x10072FB6C | Atlas (138,185,23,23) | Pixels (552,740,92,92)
Search complete.
FindHamburgerAtlas.java> Finished!
```

Neither smaller variant matched within this range/filter; this does not exclude other records, resources or mappings. Show References To `0x10072F9B0` returned zero locations. Dynamic index access is a plausible explanation, not proof of usage. No new runtime experiment occurred during that static-analysis pass. The subsequent LLDB session is documented below.

### Historical planned runtime experiment (superseded)

Attach LLDB to a fresh game process, verify executable identity and obtain the current ASLR slide (`image list -o -f`). Start with a conditional breakpoint at `0x10036C920 + slide` for `$w5 == 527` (sixth integer argument at function entry). Inspect registers and backtrace before making changes. If there is no hit during a verified hamburger-visible state, test the other known indexed helpers, particularly the historically observed `0x100378D6C` path (index at incoming `sp+8` in the atlas-564 experiment; verify the calling convention for the new candidate). `0x100375804` is another candidate (high 32 bits of ninth argument). A missed breakpoint is bounded negative evidence, not a global exclusion. Once the actual draw is captured, verify the destination X argument and perform a reversible position-only experiment; observe whether the hamburger moves and restore debugger state. Do not modify the baseline IPA or investigate the hitbox until rendering ownership is established.

## Historical coordinate and input evidence

These findings are preserved for context; none identifies the hamburger's
specific geometry or hitbox:

- Safe-area helper `0x10049E4B4`; recorded insets left/right/top/bottom were
  `141/141/0/63`. The observed transform was
  `Xout = L + Xin * (W - L - R) / W`. Its hamburger relationship is unproven.
- UI-scale candidates: `0x100369584`, function `0x10036952C`, caller
  `0x100350710`, and `0x1003D93FC`. Reported test sessions had no hits.
- UIKit touch entry points: `touchesBegan` `0x10046328C`, `touchesMoved`
  `0x100463478`, `touchesEnded` `0x1004635F8`, and `getTouchInfoIndex`
  `0x1004637A4`. Conversion helpers: `0x100460A24`, `0x10046085C`, and
  `0x100461C0C`; five native input records were observed with `0x60` stride.
- A confirmed tap and an outside tap produced different menu behavior, but
  their UIKit coordinates are not proven to be game UI coordinates and were
  not a close hitbox-boundary pair.
- Generic rectangle predicate `0x100460D44` / return `0x100460D98` and caller
  `0x100007720` / callsite `0x100007874` were tested as candidates; the
  predicate had no events in the confirmed activation.
- The accepted-event branch `0x10037D8EC` had zero hits during the confirmed
  hamburger activation. The historical dispatch chain was
  `0x10037D718 → 0x10037D87C → 0x10037FFF4`; it remains generic.
- `FUN_10036B960` was observed on the Cockpit object during Quest Info
  interaction. Its anchor calculation and text-format paths did not establish
  hamburger identity.
- The menu-closed `"  Menu"` rendering path was captured through
  `0x1003A5904`, `0x10036C870`, `0x100379100`, `0x1003788B8`, and
  `0x100378D6C`. The atlas-564 draw was changed from X=1822 to X=1622; the
  user visually identified the moved graphic as the circular left-navigation
  arrow background. The hamburger did not move.

For exact selector conditions, session-specific values, and historical
experiment procedures, see the archived
[Cockpit rendering investigation](archive/cockpit-rendering-investigation.md).

## Runtime hamburger relocation — November 24, 2026

Session: PID 30509, slide `0x404000`. All heap/data runtime addresses below are session observations, not executable file offsets. The baseline executable and saves were not modified during these LLDB experiments.

### Rendering ownership

Conditional breakpoints at unslid `0x10036C920` and `0x100375804` did not hit for the tested conditions. A read watchpoint on atlas 527 at runtime `0x100B339B0` caught thread 13 at `0x10077CE00` (unslid `0x100378E00`); x15 addressed the record. Saved destination registers x19/x20/x22/x21 were 2165/169/81/129. Changing x19 to 1565 at that stop visibly moved the hamburger. Runtime ownership is confirmed; the texture registration/4× mapping remains independently unverified.

Call site `0x1007A8154` (unslid `0x1003A4154`) calls wrapper `0x10077CD14`; atlas index at `[sp+4]`. x1–x4 are destination X/Y/W/H. x19 is Cockpit, x21 descriptor index (18 in closed layout), x24 stride `0x70`. Wrapper passes coordinates unchanged to vertex generator. Generator packs destination corners directly into packet vertices; inspected paths contain no explicit horizontal clamp. `0x10060CE10` is `setPacketBufferPtr` (assertion in ge.cpp), validates and stores pointer only.

### Layout lifecycle and addresses

| Routine | Unslid | Session runtime |
|---|---|---|
| Menu transition | `0x10037DBB0` | `0x100781BB0` |
| Layout wrapper | `0x1003A49A0` | `0x1007A89A0` |
| Array replacement | `0x1003A3280` | `0x1007A7280` |
| Descriptor conversion | `0x1003A35A4` | `0x1007A75A4` |
| Geometry calculation | `0x10039CFE0` | `0x1007A0FE0` |
| Cockpit renderer | `0x1003A37C4` | `0x1007A77C4` |
| Render wrapper | `0x100378D14` | `0x10077CD14` |
| Vertex generator | `0x100378D6C` | `0x10077CD6C` |
| Packet pointer setter | `0x100208E10` | `0x10060CE10` |

Cockpit `0x1064F9500`; menu flag byte `+0x11B5` (0 closed, 1 open in observed transitions; not a guarantee of visual state during transition). Array pointer `+0x12E8` at `0x1064FA7E8`. Observed bases include `0x1268EE800`, `0x122217200`, `0x122214000`. Old rectangle retained modified X after visible reset because active allocation changed. Watchpoint 6 caught pointer cleared at `0x1007A73E4`, then reassigned at `0x1007A74D0`. Old pointer passed to `0x1008643C4` before clearing (deallocation suspected). Layout pointer table `0x100B34AE8` runtime; layout 21 source pointer `0x10650C720`, count 13 in captured transition. Do not assume descriptor 18 exists in every layout. Array replacement initializes 0x70-byte records, converts 0x40-byte sources, and can append retained records by 0x6E-byte memcpy.

### Record structures

Runtime descriptor: flags +0x08, identifier +0x10, atlas indices +0x14/+0x18, scale floats +0x24/+0x28, rectangles A/B/C +0x2C/+0x34/+0x3C (four 16-bit fields each). Original all `(2165,169,81,129)`. A-only X edit to 1565 moves graphic, not touch; menu cycles replace allocation. B/C-only tests did not move graphic or hitbox; no read watchpoint hits in tested windows. Later evidence identifies B as rendering/interpolation geometry and C as input bounds. Earlier negative tests were confounded by stale allocations.

Compact source `0x10650C9E0`: +0x00 identifier 8; +0x04/+0x08 atlas 527; +0x0C geometry index 1; +0x10 flags `0x00010001`; +0x20/+0x24 floats 51/81; +0x30/+0x34 offsets 0/0. Geometry table `0x1065047E0`, stride 0x80, record 1 `0x106504860`.

| Geometry offset | Original value |
|---|---|
| +0x00 | 99 (int32) |
| +0x10/+0x14 | -51 / 106 (float32) |
| +0x20/+0x24 | 51 / 81 |
| +0x30/+0x34 | 1 / 1 |
| +0x40/+0x44 | -51 / 16 |
| +0x50/+0x54 | 51 / 81 |
| +0x60/+0x64 | 25.5 / 40.5 |

For type 99 and nonnegative scale multiplier, calculator uses `X = trunc(anchor_x + global_scale * (offset_x - (scale_x - 1) * pivot_x))`; analogous Y. A uses unit multipliers, B uses record +0x30/+0x34. C derives from A plus scaled compact offsets +0x30/+0x34 and scaled dimensions +0x20/+0x24. Negative multiplier branch uses secondary fields +0x40/+0x44/+0x50/+0x54. Exact anchor table semantics remain unverified. C input consumer is confirmed; see phase 8.

### Reversible source patch and evidence

At breakpoint `0x1007A75D0` condition `*(unsigned int *)($x20 + 4) == 527`, x19 destination, x20 compact record, x21 geometry table, x4 geometry record. Setting source offset -150 (`0xC3160000`) then stepping out yielded A/B/C `(2007,169,81,129)`; renderer call confirmed X=2007 both without menu filter and with flag byte 0. User reported no visible movement. Larger test -426 succeeded visually and functionally and survived menu cycles (user responses Yes/Yes/Yes). Exact final runtime rectangle, original hitbox inactivity, unrelated control effects, and restart persistence not yet verified.

```lldb
# Stop process and verify current record identity/address before writing.
# Session-specific example only:
memory write --size 4 0x106504870 0xC3D50000
# Restore original -51.0:
memory write --size 4 0x106504870 0xC24C0000
```

Regenerate layout by opening/closing menu after resuming. This was an intermediate test; later +35 geometry and compact hitbox expansion superseded it. Detach/relaunch requested, not confirmed. Breakpoint 3 has auto-continue register trace commands installed but was disabled for successful test; breakpoint 4 and watchpoint 6 were disabled in preceding steps. Confirm debugger state before further tests.

### Apparent boundary and remaining work

User-reported direct X trials: 1565 significantly left; 1800 left; 1900/1950/1980 slightly left; 1990/2000/2007/2165 original. Later trace repeatedly showed X=2007, descriptor 18, not the last manual X=1990. Since the active allocation was not verified for every test, a true clamp is not established. Negative safeArea selector/string search does not exclude game-specific safe-area calculations: existing helper `0x10049E4B4` and historical insets 141/141/0/63 are retained leads, not established causes. Search for viewport/scissor/projection strings returned only setPacketBufferPtr. Other draw sites and downstream transforms remain possible. Avoid speculative deep tracing until final geometry and hitbox verification.

## Latest runtime input and right-edge findings

See [phase 8: hamburger input](phases/research-phase8-hamburger-input.md) for the detailed address map, compact record edits, input lifecycle, confirmed rejection and clean-restart protocol. The following supersedes earlier unresolved input-consumer and boundary observations.

Runtime relocation succeeded across menu cycles. Later rightward tests reached the edge: +50 was too far, +42 reached the edge, and +35 was preferred provisionally. At +35, A/B/C were `(2303,169,81,129)` before hitbox expansion. Expanded C was verified at `(2239,169,145,129)` (bounds 2239,169–2384,298). Ordinary taps remained intermittent; a sustained press (~2 seconds, user estimate) could open the menu, and holding another finger first could make a subsequent hamburger tap respond immediately. Original baseline responsiveness, final alignment/clipping, exclusive hitbox behavior and restart persistence remain unverified.

## Historical contradictions and confidence

- Historical notes list bundle ID `jp.co.capcom.mhp2gwd`, while the later LLDB
  probe configuration lists `jp.co.capcom.mhp2g`. The executable UUID and
  SHA-256 are the stronger artifact identifiers in these notes; the bundle-ID
  discrepancy has not been resolved.
- LLDB reports represent separate attempts and tools. The archived logs include
  incomplete/unknown attachment outcomes, an interactive capture with an
  unverified breakpoint-cleanup outcome, and a later read-only inspection with
  verified detach. Do not combine them into one continuous session or reuse any
  PID, pointer, or slide; use each attempt's own cleanup fields.
- The former `research-phase8-draw-probe.md` filename contained a report
  titled “Phase 5”; it has been renamed descriptively. The historical title
  mismatch is noted in the archive copy.

## Source records

- [Archived research snapshot](archive/research-snapshot-2026-11-24.md)
- [Archived Cockpit rendering investigation](archive/cockpit-rendering-investigation.md)
- [Archived current-session draw probe](archive/current-session-draw-probe.md)
- [Touch tracer runbook](archive/touch-tracer-runbook.md)
- [Raw LLDB probe report](logs/lldb-readonly-probe-attempt.md)
- [Raw render diagnostic JSONL](logs/render-diagnostics-attempts.jsonl)
- [Raw interactive render JSONL](logs/mhfu-render-interactive-attempts.jsonl)

Selected REA evidence identifiers retained during the offline pass:

- `ev_b8b531b5e02bbf2b461d11ecb0b8505cc52e8eac3ad9052b5abd083dfdbbc924` —
  `FUN_100375FD4`
- `ev_3295165a6a1f60e00d4349455cf4e28d113779b0f53736d9cb77202febbcba28` —
  `FUN_1002C2138`
- `ev_9e871e197d6467b42822ead55855281d53a7579ce9a5241684f656484dbad270` —
  `FUN_1003762B4`
- Table records 204, 205, 208, 209:
  `ev_2b9faf481128e74587c3fa87d66c535642b824fcdd92f588a4e7ffe27dc3cff0`,
  `ev_6a815e9e1bb88000fb093ed2b6600bfe067747e67e4249e21eb4292efd21ad88`,
  `ev_62afcd3928c051477e80af57190236ca0327429d58ad018d7337ac369e865128`,
  `ev_bffb0dc2dac1096cc5ffc8d9a99a0b269b6e68c4f3b41dabd4fccebfb917e5a5`
