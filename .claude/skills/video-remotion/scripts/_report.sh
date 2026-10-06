#!/usr/bin/env bash
# Print the path plus what reading this image costs. Sourced by the image scripts.
# A normal API counts an image at ~1.1k tokens. A proxy that base64s it into the text
# prompt counts ~0.7 tokens per base64 char, which is ~150x more. Keep files small.
report_image() {
  local f="$1" b tok
  b=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
  tok=$(( b * 4 / 3 * 7 / 10 ))
  printf '%s  (%s KB; ~1.1k tokens as an image, ~%s k if the endpoint counts it as text)\n' \
    "$f" "$(( b / 1024 ))" "$(( tok / 1000 ))"
  if [ "$b" -gt 120000 ]; then
    printf '  WARNING: over 120 KB. Lower the width or raise -q:v before reading it.\n' >&2
  fi
}
