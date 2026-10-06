#!/usr/bin/env bash
# Contact sheet with burned-in timestamps, to write the beat list.
# usage: sheet.sh <file> [out_dir] [fps] [start] [duration]
# JPEG, not PNG: a PNG sheet of UI frames runs ~600 KB, which is ~550k tokens if the
# endpoint counts images as text. Override with SHEET_W and SHEET_Q.
set -euo pipefail
. "$(dirname "$0")/_report.sh"
f="$1"; out="${2:-./sheets}"; fps="${3:-1}"; start="${4:-}"; dur="${5:-}"
w="${SHEET_W:-420}"; q="${SHEET_Q:-6}"
mkdir -p "$out"
if [ -n "$start" ]; then
  ffmpeg -hide_banner -loglevel error -y -ss "$start" ${dur:+-t "$dur"} -i "$f" \
    -vf "fps=$fps,scale=$w:-1,drawtext=text='%{pts\\:hms\\:$start}':x=6:y=6:fontsize=26:fontcolor=white:box=1:boxcolor=black@0.8,tile=3x3" \
    -frames:v 1 -q:v "$q" "$out/fine_${start}.jpg"
  report_image "$out/fine_${start}.jpg"
else
  ffmpeg -hide_banner -loglevel error -y -i "$f" \
    -vf "fps=$fps,scale=$w:-1,drawtext=text='%{pts\\:hms}':x=6:y=6:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.7,tile=3x4" \
    -fps_mode vfr -q:v "$q" "$out/sheet_%02d.jpg"
  for s in "$out"/sheet_*.jpg; do report_image "$s"; done
  printf 'Read only the sheet covering the window you are working on, not all of them.\n'
fi
