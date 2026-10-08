#!/bin/sh
# Usage: ./scripts/ask.sh hr "How many days of annual leave do I get?"
set -e
docker compose exec -T api sh -c 'export DATABASE_URL="${DATABASE_URL%/*}/knowledge_eval" STORAGE_BUCKET=eval-documents
python -m app.scripts.ask --role "$0" "$1"' "$1" "$2"