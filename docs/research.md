# MHFU UI Reverse-Engineering Research

**Last updated:** November 24, 2026
**Status:** Ongoing; no hamburger-specific draw call, hitbox, or patch is
confirmed.

## Current result

The corrected PVRTexTool extraction identifies the hamburger in `cock-5`, with visible source bounds **(890, 593, 102, 142)**. These are visible pixels, not necessarily the complete sprite rectangle, draw call, or hitbox.

The earlier extraction bounds `(1804, 604, 187, 119)` are superseded. Former atlas candidates **204, 205, 208, and 209** at `0x10072E0FC` no longer have a coordinate-fit justification. No replacement atlas index is confirmed.

## Confirmed findings

- The target is the UUID-verified arm64 `MH Unite` executable, SHA-256
  `25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`.
- Offline analysis used REA 6.10.1 / Ghidra 12.2 on Intel macOS (`x86_64`).
- `cockpit/cock.tmh` was extracted read-only from the baseline IPA. Five
  embedded PVR v2 PVRTC 4-bpp textures were identified. The earlier PNG decoding used PowerVR's `PVRTDecompressPVRTC` routine in a temporary wrapper; its image geometry is superseded by the corrected PVRTexTool extraction. The historical extraction did not modify the game binary.
- Ghidra's `FUN_100375FD4` and `FUN_1003762B4` show that records with flags
  `0x8000` use a ResourceManager key and the low 12 flag bits as texture
  sub-index. For the four former candidates this is key 11 and sub-index 0; neither is confirmed for the hamburger.
- The atlas-564 draw changed the circular background behind the left
  navigation arrow, not the hamburger. The generic rectangle-test candidate
  and accepted-event branch were not reached during the confirmed activation.

## Hypotheses

- Under the unverified 8× mapping, corrected visible bounds correspond to `(111.25, 74.125, 12.75, 17.75)` in table units (X approximately 111–124, Y approximately 74–92). Search overlapping records, allowing for padded bounds and other plausible mappings.
- The former four records map to `(1792, 512, 256, 256)` under that same assumption and do not overlap the corrected icon. They are unsupported, not universally excluded by runtime evidence.
- The table's relationship to `cock-5`, coordinate scale, and record semantics (tiles, independent sprites, or another representation) remain unverified.

## Blockers and next action

- **ResourceManager key 11 → `cock.tmh` → `cock-5` remains unresolved.** The known key/sub-index behavior is valid for the former records but does not establish the hamburger's resource.
- The hamburger-specific draw call and touch region remain unidentified.
- **Next:** conduct a fresh atlas candidate search using corrected bounds and independently trace resource registration and texture selection. Verify candidate usage during hamburger rendering and confirm ownership with a reversible draw-position change before pursuing the hitbox or persistent patch.

### Superseded texture aspect-ratio observation

The earlier 2× vertical preview convention was based on the incorrectly decoded texture. The corrected PVRTexTool extraction supersedes it. Do not use the old preview geometry or infer an intentional 2× renderer multiplier. Preserve historical images as historical evidence; use corrected, unscaled images for current analysis.

## Historical leads and exclusions

The atlas-564 navigation-arrow experiment, the descriptor/dispatcher candidates,
the generic touch rectangle predicate, and the accepted-event path are detailed
in the [technical reference](technical-reference.md). They remain historical
leads or excluded candidates—not evidence of the hamburger's draw call or
hitbox. Earlier PVR conversion failures and the reasons for choosing the
PowerVR decoder are also recorded there.

Older reports and their original experiment context are retained in
[docs/archive/](archive/); raw device/render diagnostics are under
[docs/logs/](logs/). Historical bundle-ID and LLDB-attempt discrepancies are
called out in the [technical reference](technical-reference.md).
