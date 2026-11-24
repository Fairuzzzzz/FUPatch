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

### Corrected extraction and superseded geometry

The subsequent corrected PVRTexTool extraction identifies the hamburger in `cock-5` at `(890, 593, 102, 142)`. The earlier temporary-wrapper image was incorrectly decoded for coordinate analysis. The old 2× vertical preview convention is superseded; it does not establish a game rendering multiplier. Use corrected, unscaled images and coordinates. The exact PVRTexTool command, version, corrected image dimensions and output hashes were not supplied with this update; record them when available. The dimensions table above records the historical extraction.

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

Under the same unverified conversion, the corrected bounds in table units would be `(111.25, 74.125, 12.75, 17.75)` (X approximately 111–124, Y approximately 74–92). Search overlapping records under plausible mappings, allowing for padding and other coordinate systems. No new index is confirmed.

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
unresolved dynamic indices, or indirect calls. The hamburger-specific draw
call remains unknown. Reevaluate the table using the corrected bounds rather than prioritizing the former four indices; confirm resource mapping, draw-path usage, and ownership by a reversible position change.

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

### Corrected texture extraction and known limitations

The revised PVR texture decoding was performed using PVRTexTool 5.7.1 (Build `26.1@f61b9fab2511`), with PVRTexLib v5.7.1.

The resulting PNGs appear to preserve the correct spatial arrangement and proportions of the UI artwork. However, visible color abnormalities remain, and the decoding should not be considered fully accurate.

The hamburger's measured visible source bounds in `cock-5` are `(890, 593, 102, 142)`. These coordinates supersede the previous measurements but remain provisional until corroborated by atlas or rendering evidence.

The decoded textures are intended as spatial references for reverse engineering, not as production-ready replacement assets.

Because the current project objective is to relocate existing UI elements rather than reconstruct or replace their artwork, resolving the remaining color abnormalities is not a research priority.

Further decoding investigation is warranted only if additional evidence suggests that the remaining inaccuracies affect texture geometry, source coordinates, or atlas interpretation.
