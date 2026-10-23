#!/usr/bin/env bash
# Run the patcher UI in the browser.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "setting up .venv (one time)…"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python -m mhfu_patch serve --open "$@"
