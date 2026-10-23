# MHFU Patcher

Turn the **original** Monster Hunter Freedom Unite IPA (iOS 1.00.11) into a
patched build with: safe area/HUD, analog, loading text & background, map
position, coating frame aligned with the bar, and MFi controller support.

Everything runs on your own machine. The IPA is uploaded to a local server
(`127.0.0.1`), never to the internet.

## What the patch changes

| feature | example change |
|---|---|
| UI scale & render constants | 8 byte ranges |
| Safe area, right HUD, submit button | 15 byte ranges |
| Analog rect & radius | 4 byte ranges |
| Loading text/background & map | 5 byte ranges |
| Coating frame aligned with the bar (A/B) | 4 byte ranges |

**36 ranges / 1,008 bytes** total in the `arm64` slice, plus package changes:

- binary becomes **thin arm64** (8,593,744 B) — identical to the tested build
- `Info.plist`: new version, `UIDeviceFamily = [1]`, `UILaunchStoryboardName`,
  2 Bluetooth permission keys (MFi controller)
- 11 old members removed (`LaunchImage*`, `_CodeSignature/*`, `iTunesArtwork`,
  `iTunesMetadata.plist`, `.ZipComment`)
- 1 member added (`LaunchScreen.storyboard`)
- the other 14,201 members are copied as-is

## Requirements

- Python 3.10+ with FastAPI + uvicorn (installed automatically into `.venv` by
  `./run.sh`; see `requirements.txt`)
- Node.js only if you want to rebuild the UI
- About 1.7 GB of free disk while processing (input + output)
- Source IPA must be decrypted (not a direct App Store download)

The `inspect` and `patch` CLI commands only need the Python standard library;
FastAPI is required for `serve`.

## Using the web UI

```bash
./run.sh
```

Single-card UI (React + shadcn/ui, black & white, English copy):

1. click **Choose IPA** and pick the original IPA in the file dialog
2. click **Patch**
3. when it finishes you get **Patch complete** and a **Download IPA** button

There is no path input. The file is uploaded to the local server (loopback),
patched there, and offered back as a download. Progress shows both the upload
and the patch phases.

Patching runs in the FastAPI process, so the work happens on whichever machine
runs the server: your laptop with `./run.sh`, or the VPS if you deploy it
publicly. Working files live in `~/.cache/fupatch` (override with
`FUPATCH_WORKSPACE` or `--workdir`). The server keeps the last two results;
download the output before patching another IPA. The source IPA is never
modified.

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

# server only (no browser; needs the venv/FastAPI)
.venv/bin/python -m mhfu_patch serve --port 8765
```

`patch` options: `--version` (override the app version; by default the source
version is kept), `--keep-fat` (keep the FAT binary), `--force` (overwrite the
output), `--patch-set ID`.

The suggested output name is `MHFU_patched.ipa`; if it already exists the CLI
uses `MHFU_patched-2.ipa`, `MHFU_patched-3.ipa`, and so on.

Exit codes: `0` success · `2` unsupported input · `3` binary bytes do not match
· `4` not enough disk space.

## Installing on device

The output IPA is unsigned. Install it with **AltStore**, **Sideloadly**, or a
similar tool — the installer re-signs it with your Apple ID. The app keeps its
source version unless you pass `--version`; the version shown in Settings is
whatever was written to `Info.plist`.

## Verification

The patcher verifies itself:

1. the slice sha256 after the binary steps **must** equal
   `25ff0f7ea91f58b2e1531080d9a9c55e9363f7a66031b1da89abf193826f92b4`
2. after writing the IPA, the binary is extracted again and its sha is checked
3. the version in the output `Info.plist` is checked again

On any mismatch the `.part` file is removed and no output is left behind.

Check a result yourself:

```bash
python3 -m mhfu_patch inspect --ipa result.ipa --json
```

## Troubleshooting

| message | meaning |
|---|---|
| `IPA is still encrypted` | App Store IPA; a decrypted copy is required |
| `unknown binary` | not a supported MHFU 1.00.11 IPA (or already modified elsewhere) |
| `step … does not match` | binary bytes differ from the expected ones; send the full message |
| `ZIP64 archives are not supported` | the IPA was packed as ZIP64; extract and re-zip without ZIP64 |
| `not enough disk space` | free about 1.7 GB in the target folder |
| `not a readable IPA` | the uploaded file is not a valid IPA archive |

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
ui/              UI source (Vite + React + shadcn/ui)
mhfu_patch/
  web/           built UI (HTML/JS/CSS) served by the server
  macho.py       fat/thin, arm64 slice, cryptid
  manifest.py    load + validate patch sets, match shas
  engine.py      inspection, binary steps, write + verification
  package.py     remove/add members, Info.plist
  ziprewrite.py  rewrite the IPA (streaming, atomic)
  jobs.py        background jobs + SSE events
  server.py      FastAPI on 127.0.0.1: upload, patch, SSE, download
patches/         patch manifests (one file per build)
assets/          LaunchScreen.storyboard fixture
tools/           manifest generator (dev)
tests/           unit + e2e
requirements.txt server dependencies (FastAPI + uvicorn)
run.sh           sets up .venv and opens the UI
```

To add a new patch build, run `tools/make_manifest.py` with the new binary pair;
`patches/index.json` selects the patch set automatically from the input IPA
slice sha.

## Limitations

- Only works for 1.00.11 IPAs whose decrypted binary sha matches the manifest.
- The patch is all-or-nothing (all 36 steps); per-feature toggles are not
  available because several code caves are shared between features.
- The output binary is thin arm64 by default; `--keep-fat` keeps the original
  armv7 slice (unpatched).
