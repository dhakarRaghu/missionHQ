#!/usr/bin/env bash
# setup-kokoro.sh [project_root]
# Installs Kokoro, a local open-source neural voice (no API key, no cost), into <project_root>/tools/tts.
# Downloads ~350 MB of model files once. narrate.mjs uses it when the narration JSON says "engine": "kokoro".
set -euo pipefail
ROOT="${1:-.}"
DIR="$ROOT/tools/tts"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$DIR/models"
cp "$HERE/kokoro_batch.py" "$DIR/kokoro_batch.py"

if [ ! -x "$DIR/.venv/bin/python" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv -q --python 3.12 "$DIR/.venv"
    uv pip install -q --python "$DIR/.venv/bin/python" kokoro-onnx soundfile
  else
    PY="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || true)"
    [ -n "$PY" ] || { echo "Need Python 3.10+ (or uv) for kokoro-onnx" >&2; exit 1; }
    "$PY" -m venv "$DIR/.venv"
    "$DIR/.venv/bin/pip" install -q kokoro-onnx soundfile
  fi
fi

BASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  [ -s "$DIR/models/$f" ] || curl -sSL -o "$DIR/models/$f" "$BASE/$f"
done
ls -la "$DIR/models"
echo "Kokoro ready in $DIR. Add tools/tts/.venv and tools/tts/models to .gitignore."
