#!/bin/bash
# Nightly run of the model-backed regression set, on the Mac that has the
# gateway key and the database. Not CI: every case sends real model calls,
# recorded under agent eval:<name> so the daily spend sees them.
#
#   scripts/regress-nightly.sh            run today's set, then compare it with
#                                         the newest after-* result
#   scripts/regress-nightly.sh --k 2      every case twice (pass^k)
#
# Writes backend/evals/results/nightly-<date>.json. Exits 1 when the compare
# finds a REGRESSION (a case the reference run passed and tonight's failed),
# so the launchd log and the exit status both say so. docs/deploy.md says how
# to install it as a launchd job.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT/backend"

LABEL="nightly-$(date +%F)"
uv run python -m hq.cli regress run "$LABEL" "$@"

# The reference is the newest accepted run: the after-<sha> file written when
# a prompt change was approved (docs/redesign-plan.md §11a). Newest by write
# time, so a re-approved run wins over an older label.
REF="$(ls -t evals/results/after-*.json 2>/dev/null | head -1 || true)"
if [ -z "$REF" ]; then
  echo "no after-*.json result to compare against; run recorded as $LABEL"
  exit 0
fi
REF="$(basename "$REF" .json)"
echo "compare $REF → $LABEL"
uv run python -m hq.cli regress compare "$REF" "$LABEL"
