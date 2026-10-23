# MHFU Patcher

Turn the **original** Monster Hunter Freedom Unite IPA (iOS 1.00.11) into a
patched build with: safe area/HUD, analog, loading text & background, map
position, coating frame aligned with the bar, and MFi controller support.

The web UI patches the IPA **entirely in the browser**: the file never leaves
the machine, nothing is uploaded, and no server CPU is used. A Python CLI is
included for automation.

## What the patch changes

| feature | example change |
|---|---|
| UI scale & render constants | 8 byte ranges |
| Safe area, right HUD, submit button | 15 byte ranges |
| Analog rect & radius | 4 byte ranges |
| Loading text/background & map | 5 byte ranges |
| Coating frame aligned with the bar (A/B) | 4 byte ranges |

**36 ranges / 1,008 bytes** total in the `arm64` slice, plus package changes:

- binary becomes **thin arm64** (8,593,744 B)
- `Info.plist`: `UIDeviceFamily = [1]`, `UILaunchStoryboardName`,
  2 Bluetooth permission keys (MFi controller), patch marker
- 11 old members removed (`LaunchImage*`, `_CodeSignature/*`, `iTunesArtwork`,
  `iTunesMetadata.plist`, `.ZipComment`)
- 1 member added (`LaunchScreen.storyboard`)
- the other 14,201 members are copied as-is

The source version is kept; `--version` can override it for CLI builds.

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
2. click **Patch**
3. when it finishes you get **Patch complete** and a **Download IPA** button

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

## Using the CLI

```bash
# inspect only
python3 -m mhfu_patch inspect --ipa original.ipa

# patch (keeps the source app version)
python3 -m mhfu_patch patch --ipa original.ipa --out MHFU_patched.ipa

# optional: give a test build its own version
python3 -m mhfu_patch patch --ipa original.ipa --out MHFU_patched.ipa \
    --version 1.00.12

# dry run, no file written
python3 -m mhfu_patch patch --ipa original.ipa --out /tmp/x.ipa --dry-run

# local server (serves the static UI + optional HTTP API)
.venv/bin/python -m mhfu_patch serve --port 8765
```

`patch` options: `--version` (override the app version; by default the source
version is kept), `--keep-fat` (keep the FAT binary), `--force` (overwrite the
output), `--patch-set ID`.

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

## Verification

The patcher verifies itself before writing the output:

1. the input arm64 slice sha256 must be a known source or intermediate binary
2. each of the 36 steps must match its expected bytes (or already be applied)
3. the patched slice sha256 **must** equal
   `25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`

The CLI additionally re-reads the executable and version from the written IPA.
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

## Troubleshooting

| message | meaning |
|---|---|
| `IPA is still encrypted` | App Store IPA; a decrypted copy is required |
| `unknown binary` | not a supported MHFU 1.00.11 IPA (or already modified elsewhere) |
| `step … does not match` | binary bytes differ from the expected ones; send the full message |
| `ZIP64 archives are not supported` | the IPA was packed as ZIP64; extract and re-zip without ZIP64 |
| `not enough disk space` | free about 1.7 GB in the target folder (CLI) |
| `XML Info.plist is not supported` | the browser engine expects the original binary Info.plist |

### Rebuilding the UI

The UI source lives in `ui/` (Vite + React + TypeScript + Tailwind + shadcn/ui
components). The build output is committed to `mhfu_patch/web`, so users do not
need Node.js.

```bash
cd ui && npm install && npm run build
```

Adding another shadcn component:

```bash
cd ui && npx shadcn@latest add dialog
```

## Development

```bash
# once: server dependencies
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# fast tests (no large files)
.venv/bin/python -m unittest discover -s tests -v

# full end-to-end test (needs the original IPA + golden build)
MHFU_E2E=1 .venv/bin/python -m unittest tests.test_cli_e2e -v

# regenerate the manifest from a binary pair
python3 tools/make_manifest.py \
  --original-ipa "original.ipa" \
  --final-bin ../re_mhfu/final-arm64 \
  --intermediate-bin ../re_mhfu/intermediate-arm64 \
  --patched-ipa ../reference-patched.ipa \
  --out patches/mhfu-ios.json
```

Layout:

```
ui/                UI source (Vite + React + shadcn/ui)
  src/lib/         browser patch engine (TS)
mhfu_patch/
  web/             built UI (static HTML/JS/CSS)
  macho.py         fat/thin, arm64 slice, cryptid
  manifest.py      load + validate patch sets, match shas
  engine.py        inspection, binary steps, write + verification
  package.py       remove/add members, Info.plist
  ziprewrite.py    rewrite the IPA (streaming, atomic)
  jobs.py          background jobs + SSE events (HTTP API)
  server.py        FastAPI: static UI + optional HTTP API
patches/           patch manifests (one file per build)
assets/            LaunchScreen.storyboard fixture
tools/             manifest generator, parity harness, IPA comparator
tests/             unit + e2e
requirements.txt   server dependencies (FastAPI + uvicorn)
run.sh             sets up .venv and opens the UI
```

To add a new patch build, run `tools/make_manifest.py` with the new binary pair;
`patches/index.json` selects the patch set automatically from the input IPA
slice sha. The browser engine bundles `patches/mhfu-ios.json`, so rebuild the UI
after changing it.

## Limitations

- Only works for IPAs whose decrypted arm64 binary sha matches the manifest.
- The patch is all-or-nothing (all 36 steps); per-feature toggles are not
  available because several code caves are shared between features.
- The output binary is thin arm64 by default; `--keep-fat` keeps the original
  armv7 slice (unpatched).
- The browser engine requires a binary `Info.plist` and does not support ZIP64
  input.
