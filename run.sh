#!/usr/bin/env bash
# Jalankan UI patcher di browser.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m mhfu_patch serve --open "$@"
