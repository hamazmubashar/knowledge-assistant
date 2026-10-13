#!/usr/bin/env bash
# Freezes the approved acceptance configuration. Refuses to commit or tag unless every check passes.
# Approved by Alex Morgan on 14 Oct 2026: Gemini 3.8 Flash, evidence cut-off 0.35, reranker off.
set -euo pipefail
cd "$(dirname "$0")/.."
EXPECT="0.35"
TAG="v1-acceptance-freeze"

fail() { echo "STOP: $1"; exit 1; }

grep -q "ANSWER_MAX_DISTANCE:-${EXPECT}}" docker-compose.yml || fail "docker-compose.yml default cut-off is not ${EXPECT}"
grep -q "answer_max_distance: float = ${EXPECT}" app/core/config.py || fail "config.py default cut-off is not ${EXPECT}"
grep -q "RERANKER_ENABLED:-false" docker-compose.yml || fail "reranker must default to off in docker-compose.yml"
grep -q "reranker_enabled: bool = False" app/core/config.py || fail "reranker must default to off in config.py"
git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null && fail "tag ${TAG} already exists; delete it first"
echo "Files: cut-off ${EXPECT}, reranker off"

docker compose up -d >/dev/null
docker compose exec -T api python -c "
from app.core.config import settings
assert settings.answer_max_distance == ${EXPECT}, f'container cut-off is {settings.answer_max_distance}'
assert not settings.reranker_enabled, 'container has the reranker on'
print('Container: cut-off', settings.answer_max_distance, '· reranker off')"

docker compose exec -T api python -m pytest -q | tail -1

git add docker-compose.yml app/core/config.py
git diff --cached --quiet && fail "nothing staged to commit"
git commit -m "FREEZE: acceptance configuration — Gemini 3.8 Flash, evidence cut-off ${EXPECT}, reranker off (approved by Alex Morgan, 14 Oct)"
git tag -a "${TAG}" -m "Frozen configuration for the independent acceptance run"
git push
git push origin "${TAG}"
echo "Frozen at $(git rev-parse --short HEAD), tagged ${TAG}"
