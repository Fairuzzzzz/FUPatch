
# Phase 12 — Production iPad Integration

## Status

Implementation complete, device-tested, and final regression
verification passed.

## Objective

Integrate the permanent iPad binary patches developed in Phase 11
into the production Python and TypeScript patching engines without
changing existing iPhone profile behavior.

## 1. Production profile

| Property | Value |
| --- | --- |
| Profile ID | `ipad-air-m2` |
| Display name | iPad Air (M2) |
| Default | No |
| Device family | `[1, 2]` |
| Base patch ranges | 36 |
| Additional patch ranges | 4 |
| Total patch ranges | 40 |
| Additional patch range bytes | 264 |
| Runtime injection required | No |

The existing `iphone12-14` profile remains the default.

### Executable hashes

Default iPhone baseline:

```
25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4
```

Production iPad result:

```
1447d7909bce6466cceb9be6eb6341372839757de1a83176a16aa54683ea07c1
```

The production iPad executable matches the device-tested permanent
patch produced during Phase 11.

## 2. Permanent binary patches

| Patch | Address | Range size |
| --- | --- | ---: |
| Hamburger hook | `0x1003A35D0` | 4 bytes |
| Hamburger helper | `0x10049E900` | 100 bytes |
| Startup gesture hook | `0x1003545D0` | 4 bytes |
| Gesture helper | `0x10049EA00` | 156 bytes |

All four ranges are stored directly in the shared patch manifest.

The hamburger helper corrects the geometry of the menu button.
The gesture helper registers an implementation of
`preferredScreenEdgesDeferringSystemGestures` to defer system gestures
along the right screen edge.

No new dynamic libraries, runtime injection, or debugger attachment
are required.

See [Phase 11](research-phase11-permanent-ipad-patch.md) for the
reverse-engineering evidence and implementation details.

## 3. Manifest integration

The production profile is defined in:

`patches/mhfu-ios.json`

Two device-specific features were added:

- `ipad-hamburger`
- `ipad-gestures`

Profiles can optionally define `info_changes` to customize the
shared Info.plist configuration.

The manifest schema version remains unchanged.

The iPad profile overrides only `UIDeviceFamily` in the shared
package configuration. All other common packaging settings
remain inherited.

Existing iPhone profile binary patches and package settings
remain unchanged.

## 4. Python engine integration

### mhfu_patch/manifest.py

- Added profile-specific Info.plist configuration resolution.
- Added validation for shared and profile-specific plist changes.
- Preserved the default profile configuration.
- Prevented mutation of the shared manifest during resolution.

### mhfu_patch/package.py

- Added profile-aware Info.plist patching.
- Preserved existing version and patch marker behavior.

### mhfu_patch/engine.py

- Passed the selected profile into package patching.
- Extended the already-patched check to include profile-specific
  Info.plist requirements.
- Enabled repair of an incorrect plist without reapplying
  binary patches.
- Added parsed Info.plist verification after writing the output IPA.

## 5. TypeScript engine integration

The browser engine implements equivalent profile-specific
Info.plist configuration resolution in:

`ui/src/lib/engine.ts`

Changes include:

- Shared InfoChanges type.
- Optional profile-specific plist configuration.
- Deterministic merging of shared and profile settings.
- Profile-aware plist patching.
- Recursive plist value comparison.
- Improved already-patched detection.

The browser remains a client-side patcher. IPA contents are not
uploaded to a server.

## 6. Cross-engine verification

Python and TypeScript production iPad outputs were compared.

Verified properties:

- Identical patched executable bytes.
- Identical executable SHA-256.
- Equivalent parsed Info.plist contents.
- Identical archive member sets.
- Correct native iPad device family `[1, 2]`.

The Python and browser engines use different plist serialization
formats. ZIP compression differences may also affect the final
archive size.

Therefore, complete IPA byte equality is not required.

## 7. Device verification

The production IPA generated through the web interface was
installed and confirmed working on iPad Air (M2).

The permanent hamburger correction and gesture deferral patch
were previously verified during Phase 11.

No claim is made that all gameplay paths or other iPad models
have been exhaustively tested.

## 8. Regression testing

Python regression suite after experimental profile cleanup:

| Result | Count |
| --- | ---: |
| Total | 157 |
| Passed | 154 |
| Skipped | 3 |
| Failed | 0 |

TypeScript profile configuration regression suite:

| Result | Count |
| --- | ---: |
| Total | 7 |
| Passed | 7 |
| Failed | 0 |

Coverage includes:

- Preservation of existing iPhone profile settings.
- Production iPad profile selection.
- Native iPad device family configuration.
- Shared and profile-specific plist merging.
- Removal and assignment precedence.
- Deterministic configuration resolution.
- Manifest immutability.
- Production executable verification.
- Plist-only repair.
- Already-patched detection.

The remaining skipped Python tests require separate review of
their fixture requirements.

## 9. Experimental profile retirement

The following experimental loading profiles were removed from
the production manifest:

- `ipad-air-m2-loading30-test`
- `ipad-air-m2-loading31-test`

Their associated active regression tests were retired.

The standalone native iPad family conversion utility and its
tests were archived:

- `tools/archive/enable_ipad_family.py`
- `tests/archive/test_enable_ipad_family.py`

The archived tests retain historical imports and profile
references and are not part of the maintained active test suite.

Previously generated experimental-profile IPAs are no longer
recognized as supported production profile results.

## 10. Retained research utilities

The permanent patch remains reproducible using:

- `tools/arm64_encoding.py`
- `tools/asm/hamburger_hook.s`
- `tools/asm/gesture_hook.s`
- `tools/build_ipad_patch.py`

Binary verification, code cave discovery, layout exploration,
and runtime touch tracing utilities are retained for future
device support research.

## 11. Remaining limitations

- Native iPad support is currently validated on iPad Air (M2).
- Other iPad models and iPadOS versions require testing.
- Existing experimental iPhone compatibility claims remain unchanged.
- Browser output verification differs from CLI output verification.
- Some legacy regression fixtures remain unavailable.

## 12. Release checklist

- [x] Permanent binary patch reproduced.
- [x] Production manifest profile added.
- [x] Python engine integrated.
- [x] TypeScript engine integrated.
- [x] Cross-engine parity verified.
- [x] Production IPA tested on iPad.
- [x] Experimental profiles retired.
- [x] Research tools organized.
- [x] Python regression suite passed.
- [x] TypeScript profile regression suite passed.
- [x] README updated.
- [x] Final regression verification.
- [x] Final production web build.
- [x] Git diff review.
- [ ] Commit and push.

## Subsequent production integration of Phases 13 and 14

The profile now displays as **iPad Air 11-inch**. Its ID remains `ipad-air-m2` and its device family remains `[1, 2]`. Five additional ranges (368 bytes) implement the hamburger and shared bottom-row button geometry, bottom/right gesture deferral, and the 20.0 loading glyph dimension. The horizontal origin instruction belongs to the common 456-byte `safe-area.34` range. Its iPad replacement override changes only byte `+0x177` from `0b` to `4b`, retaining the original source-byte expectation. The common step and six iPhone profiles retain their previous payloads. Rebuild from the original IPA for this revision.

Both production engines reproduced every profile's executable hash. The six iPhone comparisons used the verified original arm64 slice in a small fixture archive for TypeScript. Full original-IPA parity was checked for iPad: each archive contained 14,204 members. Reading every member verified ZIP integrity. All payloads matched byte for byte except Info.plist, whose parsed contents matched, including UIDeviceFamily. Different plist serializations produced different archive hashes.

The production executable matched the permanent Phase 14 executable and experimental v5 across all 8,593,744 bytes, SHA-256 `ff26548f0e32f240e01c30e2e172bd005087b43ea1a517527bc84668339be10e`. The experimental v5 was tested on iPad Air (M2). The tester subsequently confirmed that the game is fully working with the production-generated IPA on the physical iPad Air (M2). This completes production integration and validation for Phases 13 and 14 on that model. Compatibility with other iPad models and generations remains unverified.

Full regression passed all 163 Python tests, including the API and original-IPA CLI tests, and all seven TypeScript profile tests. The full run used a temporary, hash-verified reconstruction of the intermediate fixture. The production browser build passed TypeScript compilation and Vite bundling.
