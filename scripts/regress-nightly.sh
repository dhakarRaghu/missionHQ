#!/usr/bin/env bash
# The nightly regression run: the model-backed set as nightly-<date>, then a
# compare with the newest accepted after-* result. It calls the models for
# real, so it runs where backend/.env has the gateway key, never in CI.
# Extra arguments go to `regress run` (for example `--k 2`).
set -euo pipefail
cd "$(dirname "$0")/../backend"
label="nightly-$(date +%Y-%m-%d)"
uv run python -m hq.cli regress run "$label" "$@"
latest=$(ls -t evals/results/after-*.json 2>/dev/null | head -1 || true)
if [ -z "$latest" ]; then
  echo "no after-* result to compare with; accept one with: regress run after-<sha>"
  exit 0
fi
uv run python -m hq.cli regress compare "$(basename "$latest" .json)" "$label"
