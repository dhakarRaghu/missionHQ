#!/usr/bin/env bash
# Pull check frames from a render and tile them into ONE image.
# usage: frames.sh <video> <out_dir> <t1> <t2> ...
# Tile into one file and read that one file. Reading each frame separately multiplies the cost,
# and every image stays in context for the rest of the session.
set -euo pipefail
. "$(dirname "$0")/_report.sh"
v="$1"; out="$2"; shift 2
w="${SHEET_W:-420}"; q="${SHEET_Q:-6}"
if [ "$#" -gt 9 ]; then
  printf 'NOTE: %s frames requested. Prefer <=9 per round; check more only where a beat looks wrong.\n' "$#" >&2
fi
rm -rf "$out"; mkdir -p "$out"
for t in "$@"; do
  ffmpeg -hide_banner -loglevel error -y -ss "$t" -i "$v" -frames:v 1 -vf "scale=$w:-1" \
    -q:v "$q" "$out/$(printf '%07.2f' "$t").jpg"
done
n=$#; cols=3; rows=$(( (n + cols - 1) / cols ))
ffmpeg -hide_banner -loglevel error -y -pattern_type glob -i "$out/*.jpg" \
  -vf "tile=${cols}x${rows}" -frames:v 1 -q:v "$q" "$out/sheet.jpg"
report_image "$out/sheet.jpg"
