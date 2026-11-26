#!/bin/bash
set -euo pipefail

DEVICE="EB90DDE0-50FB-5593-A792-E211E636A9EC"

# Discover current MH Unite process.
PROCESS_LIST=$(xcrun devicectl device info processes \
  --device "$DEVICE" \
  --filter "ExecutablePath CONTAINS 'MH Unite.app'" \
  --columns "PID,ExecutablePath")

PID=$(printf '%s\n' "$PROCESS_LIST" |
  awk '
    {
      sub(/\r$/, "")
      if ($1 ~ /^[0-9]+$/ && $0 ~ /\/MH Unite\.app\/MH Unite$/) {
        print $1
      }
    }
  ')

PID_COUNT=$(printf '%s\n' "$PID" | awk 'NF { count++ } END { print count + 0 }')
if [[ "$PID_COUNT" -eq 0 ]]; then
  echo "No running MH Unite process was found on the selected iPad." >&2
  exit 1
fi
if [[ "$PID_COUNT" -ne 1 ]]; then
  echo "Found $PID_COUNT matching MH Unite processes; refusing ambiguous attach." >&2
  exit 1
fi
if [[ ! "$PID" =~ ^[0-9]+$ ]]; then
  echo "The discovered MH Unite PID was invalid; refusing attach." >&2
  exit 1
fi

# Create temporary LLDB commands.
COMMANDS=$(mktemp)
trap 'rm -f "$COMMANDS"' EXIT

printf 'device select %s\n' "$DEVICE" > "$COMMANDS"
printf 'device process attach --pid %s\n' "$PID" >> "$COMMANDS"
printf 'image list -o -f "MH Unite"\n' >> "$COMMANDS"

echo "Starting interactive LLDB for MH Unite (PID $PID) on device $DEVICE..." >&2
xcrun lldb -s "$COMMANDS"
