#!/usr/bin/env bash
# Jalankan UI patcher di browser.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "menyiapkan .venv (sekali saja)…"
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python -m mhfu_patch serve --open "$@"
