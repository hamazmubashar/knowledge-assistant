#!/usr/bin/env bash
# The one authorised command for the acceptance run. Usage: ./scripts/acceptance_run.sh [models]
# Stops before running anything if the code is uncommitted or the fingerprint does not match.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "STOP: uncommitted changes. The acceptance run must use a committed, frozen configuration."
  exit 1
fi

python3 scripts/verify_acceptance.py eval/acceptance_v1.csv eval/acceptance_v1.sha256

MODELS="${1:-gemini:gemini-3.8-flash,qwen2.5:3b}"
mkdir -p eval/logs
LOG="eval/logs/acceptance-$(date -u +%Y%m%d-%H%M%S).log"
{
  echo "# Acceptance run log"
  echo "commit: $(git rev-parse HEAD)"
  echo "models: $MODELS"
  echo "started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$LOG"
./scripts/answer_eval.sh acceptance "$MODELS" 2>&1 | tee -a "$LOG"
echo "finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$LOG"
echo "Log saved: $LOG"
