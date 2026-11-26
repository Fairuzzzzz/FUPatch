# MHFU Patcher


Turn the **original** Monster Hunter Freedom Unite IPA (iOS 1.00.11) into a
patched build with: safe area/HUD, analog, loading text & background, map
position, coating frame aligned with the bar, and MFi controller support.

The patch also supports **native iPad gameplay on iPad Air (M2)**, with an
enlarged hamburger button, taller shared bottom-row buttons, corrected loading
text size and position, and gesture deferral at the bottom and right edges.


The web UI patches the IPA **entirely in the browser**: the file never leaves
the machine, nothing is uploaded, and no server CPU is used. A Python CLI is
included for automation.

### Disclaimer

This repository contains extracted assets from the original game, published solely for **research and educational purposes**.

All rights, titles, and interests in the original game and its assets belong to their respective copyright holders.

**Full credit goes to Capcom and the original developers and creators.**

This project is unofficial and is not affiliated with, endorsed by, or sponsored by the original copyright holders.

## What the patch changes

| feature                                  | example change |
| ---------------------------------------- | -------------- |
| UI scale & render constants              | 8 byte ranges  |
| Safe area, right HUD, submit button      | 15 byte ranges |
| Analog rect & radius                     | 4 byte ranges  |
| Loading text/background & map            | 5 byte ranges  |
| Coating frame aligned with the bar (A/B) | 4 byte ranges  |


**36 ranges / 1,008 bytes** in the base `arm64` patch, plus package changes.

- The iPhone 11 / XR profile adds three null-guard ranges (39 total).
- Other iPhone profiles override the safe-area and UI-scale constants.
- The iPad Air 11-inch profile adds five ranges covering 368 bytes
  (41 ranges / 1,376 bytes total). It also overrides one byte within
  the common `safe-area.34` replacement for the loading text origin.
- binary becomes **thin arm64** (8,593,744 B)
- `Info.plist`: profile-specific `UIDeviceFamily` (`[1]` for iPhone profiles,
  `[1, 2]` for the iPad profile), `UILaunchStoryboardName`,
  2 Bluetooth permission keys (MFi controller), `UIFileSharingEnabled` and
  `LSSupportsOpeningDocumentsInPlace` (save data visible in the Files app),
  patch marker
- 11 old members removed (`LaunchImage*`, `_CodeSignature/*`, `iTunesArtwork`,
  `iTunesMetadata.plist`, `.ZipComment`)
- 1 member added (`LaunchScreen.storyboard`)
- the other 14,201 member payloads are copied as-is

The source version is kept; `--version` can override it for CLI builds.

Normal patching preserves ZIP local extra fields. The optional
`mhfu_patch.ziprewrite.rewrite(..., normalize_local_extras=True)` operation is
for explicit archive maintenance only; it is not used by patching or native
iPad conversion and is not required for the verified MHFU iPad baseline.
ZIP64 archives are unsupported.

## Requirements

- A modern browser (desktop Chrome, Edge or Chromium recommended)
- The source IPA must be decrypted (not a direct App Store download)
- Node.js only if you want to rebuild the UI
- Python 3.10+ with FastAPI + uvicorn only for the optional local server / CLI

## Using the web UI

The built UI lives in `mhfu_patch/web` and is a static site. Serve it with any
static file server, for example:

```bash
python3 -m http.server 8765 --directory mhfu_patch/web
```

Or use the included launcher (it sets up the venv, serves the UI and opens the
browser):

```bash
./run.sh
```

For UI development:

```bash
cd ui && npm run dev
```

Single-card UI (React + shadcn/ui, black & white, English copy):

1. click **Choose IPA** and pick the original IPA in the file dialog
2. choose the **device profile** that matches your iPhone or iPad
3. click **Patch**
4. when it finishes you get **Patch complete** and a **Download IPA** button

There is no path input and no upload. The browser reads the file with the File
API, applies the patch, and offers the result as `MHFU_patched.ipa`
(812.9 MB).

Patching uses `File.slice()` for every unchanged member, so the 813 MB archive
is never loaded into memory as a single buffer; only the arm64 slice (~8.6 MB)
and `Info.plist` are decompressed. Results are kept as a browser `Blob` until
the tab is closed.

Notes:

- A desktop Chromium browser is the safest choice for an 813 MB `Blob`.
  Safari and mobile browsers may hit memory limits.
- Opening `index.html` directly from disk (`file://`) does not work; serve the
  folder over HTTP.
- The build uses relative asset paths, so it also runs under a subpath
  (GitHub Pages, etc.).


## Device profiles

Both the Python and browser patching engines use one shared manifest.
Device profiles can override base binary patches, add device-specific
binary patches, and customize `Info.plist` settings.

| profile id | models | safe area (px) | uiScale | status |
| --- | --- | --- | --- | --- |
| `iphone11-xr` | iPhone 11, XR | 88 / 88 / 0 / 42 | 1.0 | 2x; crash guard; needs device test |
| `iphone11-pro` | iPhone 11 Pro / Pro Max | 132 / 132 / 0 / 63 | 1.6 | 3x, 44 pt; needs device test |
| `iphone12-14` | iPhone 12 / 13 / 14, incl. mini, 14 Plus, 12/13 Pro Max | 141 / 141 / 0 / 63 | 1.6 | default; 3x, 47 pt |
| `iphone14pro-15` | iPhone 14 Pro, 15 | 177 / 177 / 0 / 63 | 1.6 | 3x, 59 pt; needs device test |
| `iphone14-15-promax` | iPhone 14 Pro Max, 15 Plus, 15 Pro Max | 177 / 177 / 0 / 63 | 1.764 | 3x, 59 pt; needs device test |
| `iphone16-17` | iPhone 16 / 17 (generic) | 177 / 177 / 0 / 63 | 1.6 | fallback, not per-model |
| `ipad-air-m2` | iPad Air 11-inch | inherited | inherited | production IPA validated on iPad Air (M2) |

The **iPhone 12 / 13 / 14** profile remains the default and is
binary-identical to the original patch.

Other iPhone profiles retain their previous compatibility status.
The iPhone 16 / 17 profile is deliberately a generic fallback; the
16 Pro / 17 Pro / 17 Air dimensions have not been measured.

### Native iPad support

The `ipad-air-m2` profile provides:

- Native iPad rendering through `UIDeviceFamily = [1, 2]`.
- Enlarged and repositioned hamburger button.
- Taller shared buttons in the Items, Combine, and Guild Card menus.
- System gesture deferral along the bottom and right edges.
- Smaller loading glyphs and a corrected starting horizontal position.
- All common binary and packaging patches.
- Permanent binary modifications without runtime injection or LLDB.

To use this profile, select **iPad Air 11-inch** in the web interface
and patch the original decrypted IPA. No intermediate IPA or additional
conversion tool is required.

The production executable matches the permanent Phase 14 build and the experimental v5 executable tested on iPad Air (M2). The tester also confirmed that the game is fully working on that device with the production-generated IPA. Rebuild from the original IPA when updating from Phase 12.
Compatibility with other iPad models and iPadOS versions is not
yet established.

The earlier experimental loading profiles have been retired.
Their research history remains available in the repository.

## Using the CLI

```bash
# inspect only
python3 -m mhfu_patch inspect --ipa original.ipa

# inspect with a device profile
python3 -m mhfu_patch inspect --ipa original.ipa --profile iphone11-xr

# patch (keeps the source app version)
python3 -m mhfu_patch patch --ipa original.ipa --out MHFU_patched.ipa

# patch for a specific device profile
python3 -m mhfu_patch patch --ipa original.ipa --out MHFU_patched.ipa \
    --profile iphone11-xr

# optional: give a test build its own version
python3 -m mhfu_patch patch --ipa original.ipa --out MHFU_patched.ipa \
    --version 1.00.12

# dry run, no file written
python3 -m mhfu_patch patch --ipa original.ipa --out /tmp/x.ipa --dry-run

# local server (serves the static UI + optional HTTP API)
.venv/bin/python -m mhfu_patch serve --port 8765

# patch for native iPad support
python3 -m mhfu_patch patch --ipa original.ipa --out MHFU_iPad.ipa \
    --profile ipad-air-m2
```

`patch` options: `--version` (override the app version; by default the source
version is kept), `--keep-fat` (keep the FAT binary), `--force` (overwrite the
output), `--patch-set ID`, `--profile ID` (defaults to `iphone12-14`).

The suggested output name is `MHFU_patched.ipa`; if it already exists the CLI
uses `MHFU_patched-2.ipa`, `MHFU_patched-3.ipa`, and so on.

Exit codes: `0` success · `2` unsupported input · `3` binary bytes do not match
· `4` not enough disk space.

The bundled server still exposes the original upload/job API for tooling, but
the web UI does not call it; patching happens in the browser.

## Installing on device

The output IPA is unsigned. Install it with **AltStore**, **Sideloadly**, or a
similar tool — the installer re-signs it with your Apple ID. The app keeps its
source version unless you pass `--version`; the version shown in Settings is
whatever was written to `Info.plist`.

The patch enables Documents file sharing, so on current iOS the app's data
container appears in the Files app as **MH Unite**. The game keeps its original
save path (`Documents/savedata` and `Documents/_savedata`); the patch does not
move or rewrite save data.

## Verification

The patcher verifies itself before writing the output:

1. the input arm64 slice sha256 must be a known source or intermediate binary
2. every base and profile step must match its expected bytes (or already be applied)
3. the patched slice sha256 **must** equal the selected profile's result sha;
   the default `iphone12-14` result is
   `25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`
   The production `ipad-air-m2` result is
   `ff26548f0e32f240e01c30e2e172bd005087b43ea1a517527bc84668339be10e`.

The CLI additionally re-reads the executable, version, and parsed Info.plist
contents from the written IPA.
The browser engine cannot re-read its own output stream, so it relies on the
verified slice plus the parity suite below.

Check a result yourself:

```bash
python3 -m mhfu_patch inspect --ipa result.ipa --json
```

## Browser engine

The UI bundles the patch manifest at build time and applies the same steps in
TypeScript:

```
ui/src/lib/macho.ts     Mach-O fat/thin, arm64 slice
ui/src/lib/zip.ts       ZIP index, raw member copy, deterministic rewrite
ui/src/lib/plist.ts     binary plist reader, XML writer
ui/src/lib/engine.ts    patch pipeline + verification
ui/src/lib/manifest.ts  bundled patch set + storyboard fixture
```

`Info.plist` is written as XML (iOS accepts both XML and binary plists). That
member therefore has a different CRC/size from a CLI build; the parsed keys are
identical, and every other member matches exactly. This is enforced by the
parity check:

```bash
# build the Node harness
ui/node_modules/.bin/esbuild tools/parity.ts --bundle --platform=node \
  --format=esm --outfile=/tmp/parity.mjs --external:node:*

# run both engines on the original IPA
node /tmp/parity.mjs original.ipa /tmp/js.ipa
python3 -m mhfu_patch patch --ipa original.ipa --out /tmp/py.ipa

# member set, member CRC, executable sha256, Info.plist keys
python3 tools/compare_ipa.py /tmp/py.ipa /tmp/js.ipa
```

Expected: identical member count (14,204), identical CRCs for every member
except `Info.plist`, identical executable sha256, identical plist keys.


To verify the production iPad profile, run both engines with the same
profile:

```bash
node /tmp/parity.mjs original.ipa /tmp/js-ipad.ipa ipad-air-m2

python3 -m mhfu_patch patch --ipa original.ipa --out /tmp/py-ipad.ipa \
    --profile ipad-air-m2

python3 tools/compare_ipa.py /tmp/py-ipad.ipa /tmp/js-ipad.ipa
```

The Python and browser engines have been verified to produce identical
iPad executable bytes, equivalent parsed Info.plist contents, and
identical archive member sets.

The complete IPA archives may differ in size or SHA-256 because of
ZIP compression and plist serialization differences.

## Troubleshooting

| message                            | meaning                                                           |
| ---------------------------------- | ----------------------------------------------------------------- |
| `IPA is still encrypted`           | App Store IPA; a decrypted copy is required                       |
| `unknown binary`                   | not a supported MHFU 1.00.11 IPA (or already modified elsewhere)  |
| `step … does not match`            | binary bytes differ from the expected ones; send the full message |
| `ZIP64 archives are not supported` | the IPA was packed as ZIP64; extract and re-zip without ZIP64     |
| `not enough disk space`            | free about 1.7 GB in the target folder (CLI)                      |
| `XML Info.plist is not supported`  | the browser engine expects the original binary Info.plist         |

## Limitations

- Only works for IPAs whose decrypted arm64 binary sha matches the manifest.
- The patch is all-or-nothing (base steps plus the selected profile); per-feature
  toggles are not available because several code caves are shared between
  features.
- Native iPad support has been verified on iPad Air (M2).
  Other iPad models are not yet validated.
- Non-default iPhone profiles retain their existing experimental or
  fallback compatibility status.
- Previously generated IPAs using retired experimental loading profiles
  are no longer recognized as supported profile results.
- The output binary is thin arm64 by default; `--keep-fat` keeps the original
  armv7 slice (unpatched).
- The browser engine requires a binary `Info.plist` and does not support ZIP64
  input.


## Research documentation

The shared production manifest includes the permanent layout, gesture, and loading text corrections for iPad.

- [Phase 11 — Permanent iPad patch](docs/phases/research-phase11-permanent-ipad-patch.md)
- [Phase 12 — Production integration](docs/phases/research-phase12-production-integration.md)
- [Phase 13 — Shared button geometry](docs/phases/research-phase13-sort-button.md)
- [Phase 14 — Loading text size and position](docs/phases/research-phase14-loading-text.md)
- [Research overview](docs/research.md)
- [Technical reference](docs/technical-reference.md)

Superseded reports are retained under [docs/archive/](docs/archive/),
and raw diagnostic output under [docs/logs/](docs/logs/).

Research utilities used to reproduce the permanent binary patches
remain under `tools/`. Superseded experimental tools are retained
under `tools/archive/`.
