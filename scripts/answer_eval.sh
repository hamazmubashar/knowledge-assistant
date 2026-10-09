#!/bin/sh
# Usage: ./scripts/answer_eval.sh dev
set -e
SET=${1:-dev}
MODELS=${2:-qwen2.5:3b,gemma3:1b}

docker compose exec -T db sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP DATABASE IF EXISTS knowledge_eval WITH (FORCE);"'
docker compose exec -T db sh -c 'psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE knowledge_eval;"'

docker compose exec -T api sh -c 'set -e
export DATABASE_URL="${DATABASE_URL%/*}/knowledge_eval" STORAGE_BUCKET=eval-documents
alembic upgrade head
python -m app.scripts.seed_eval_corpus
python -m app.scripts.run_answer_eval --set "$0" --models "$1"' "$SET" "$MODELS"