# MHFU UI Reverse-Engineering Research

**Last updated:** November 24, 2026
**Status:** Ongoing; no hamburger-specific draw call, hitbox, or patch is
confirmed.

## Current result

The hamburger graphic is visually identified in the fifth decoded Cockpit
texture, `cock-5` (2048×2048). Its visible source bounds are **(1804, 604,
187, 119)**. This identifies the pixels in the texture, not the game call that
draws them or the input region that activates them.

The matching four candidate rows in the atlas table at `0x10072E0FC` are
indices **204, 205, 208, and 209**. They are separate 16×16 records with
resource field 11. An 8× mapping makes their combined region contain the
hamburger, but the scale and relationship to `cock-5` are not proven.

## Confirmed findings

- The target is the UUID-verified arm64 `MH Unite` executable, SHA-256
  `25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`.
- Offline analysis used REA 6.10.1 / Ghidra 12.2 on Intel macOS (`x86_64`).
- `cockpit/cock.tmh` was extracted read-only from the baseline IPA. Five
  embedded PVR v2 PVRTC 4-bpp textures were decoded to PNG using PowerVR's
  `PVRTDecompressPVRTC` routine in a temporary wrapper. No game binary was
  modified.
- Ghidra's `FUN_100375FD4` and `FUN_1003762B4` show that records with flags
  `0x8000` use a ResourceManager key and the low 12 flag bits as texture
  sub-index. For the four candidates this is key 11 and sub-index 0.
- The atlas-564 draw changed the circular background behind the left
  navigation arrow, not the hamburger. The generic rectangle-test candidate
  and accepted-event branch were not reached during the confirmed activation.

## Hypotheses

- Treating table coordinates as 8× texture pixels produces a 2×2 region at
  `(1792, 512, 256, 256)` that contains the hamburger. It also contains
  unrelated surrounding pixels. This is a coordinate-fit hypothesis, not
  proof of the renderer's sampling scale.
- The 16×16 records look like cells in a regular atlas grid. Existing evidence
  does not establish whether they are texture tiles, independent sprites, or
  another atlas representation.

## Blockers and next action

- **Resource ID 11 → `cock.tmh` → `cock-5` remains unresolved.** Ghidra shows a
  key lookup and texture sub-index selection, but not the resource registration
  that binds key 11 to the `.tmh` member and one of its five textures.
- The hamburger-specific draw call and touch region remain unidentified.
- **Next:** trace `cock.tmh` resource registration and determine how key 11 and
  texture sub-indices map to the five embedded textures. Then return to the
  candidate atlas rows and identify the icon-specific draw and input paths.

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
