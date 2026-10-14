# Knowledge Assistant (V1)

Internal question-answering over company PDFs. Every answer sentence is checked against a passage on the cited page, and users only search the document groups their role allows.

**Status: Pending Independent Acceptance.** This is not a production release. The acceptance configuration is frozen at tag `v1-acceptance-freeze` (commit `16b6215`). Later commits add evidence and tooling only; `git diff v1-acceptance-freeze HEAD -- app/ docker-compose.yml Dockerfile requirements.lock` must be empty.

## What runs where

| Service | Image | Port | Role |
| --- | --- | --- | --- |
| api | built from `Dockerfile` (python:3.12-slim, pinned by digest) | 8000 | FastAPI app and web UI |
| worker | same image | none | extracts, checks and indexes uploaded PDFs |
| db | `pgvector/pgvector:pg16` | 5432 | documents, chunks, embeddings, users |
| storage | `rustfs/rustfs:latest` | 9000–9001 | S3-compatible PDF storage |
| Ollama (on the host, not in Compose) | — | 11434 | local answer model `qwen2.5:3b` |

The judge model (support and relevance checks) is Gemini 3.5 Flash Lite and needs `GEMINI_API_KEY`. **Use synthetic documents only**: with the judge enabled, passages from answered questions are sent to Google.

## Prerequisites

- Docker Desktop (or Docker Engine with Compose v2)
- [Ollama](https://ollama.com) running on the host, then `ollama pull qwen2.5:3b`
- A Gemini API key for the judge

## Setup

```bash
git clone https://github.com/hamazmubashar/knowledge-assistant.git
cd knowledge-assistant
git checkout v1-handover              # frozen code plus README and evidence

cp .env.example .env
# Fill in every value: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB,
#   STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY, GEMINI_API_KEY, and
#   JWT_SECRET (at least 32 characters; generate one with: openssl rand -hex 32).
# The API refuses to start if JWT_SECRET is missing or shorter than 32 characters.

docker compose up -d --build
docker compose ps                      # db should be "healthy"

# Create the database schema
docker compose exec api alembic upgrade head
```

The first build downloads the embedding model (`BAAI/bge-small-en-v1.5`) and the reranker model (disabled in V1) into the image. Expect several minutes.

## Create users

Passwords are prompted for and must be at least 12 characters.

```bash
docker compose exec api python -m app.scripts.create_user --email hr.admin@demo.test --role hr --admin-groups hr,general
docker compose exec api python -m app.scripts.create_user --email support@demo.test  --role support
docker compose exec api python -m app.scripts.create_user --email ops@demo.test      --role operations
```

Roles: `support`, `operations`, `hr`, `system_admin`. `--admin-groups` lets a user upload to and manage those groups (comma-separated).

## Use it

Open http://localhost:8000 and sign in.

- **Ask**: answers cite document, version and page. **Open PDF** opens the cited page.
- **Documents** (admins only): upload a PDF to a group. The status goes from processing to **Published** once text is extracted, checked and indexed. Scanned pages without a text layer are flagged rather than silently indexed.

A synthetic demo PDF works for a quick check: upload it to **General**, wait for **Published**, then ask a question it answers.

## Tests

```bash
docker compose exec api python -m pytest -q
```

Expected: `100 passed, 1 warning`. The warning is a Starlette deprecation raised when FastAPI's test client is imported. It affects tests only and is left alone because fixing it would change the frozen dependency lock.

## Evaluation

Evaluations run against a separate `knowledge_eval` database, which is rebuilt on every run. The demo database is never touched.

```bash
./scripts/eval.sh dev              # retrieval: Recall@1/@5, MRR, access leaks, superseded results
./scripts/answer_eval.sh dev       # answers: correctness, citations, unsupported claims, refusals
```

Reports are written to `eval/reports/`. Each report records the corpus version, question-file sha256, code version, prompt fingerprint and dependency fingerprint.

### Independent acceptance run

The acceptance question set is written by an independent reviewer. The development team does not see it before the run.

1. Place the sealed set at `eval/acceptance_v1.csv`. Place the fingerprint, delivered separately, at `eval/acceptance_v1.sha256`. Both paths are git-ignored.
2. Make sure the working tree is clean (`git status`).
3. Run `./scripts/acceptance_run.sh`.

The script refuses to run on uncommitted changes and verifies the fingerprint before anything else. Exit code 2 means a mismatch, 3 means a missing file. In either case **stop and escalate; do not edit the file.** The set can be run only once, and the log is saved to `eval/logs/`.

## Frozen configuration

| Setting | Value |
| --- | --- |
| Evidence cut-off (`ANSWER_MAX_DISTANCE`) | 0.35 |
| Reranker | off |
| Embeddings | BAAI/bge-small-en-v1.5, 384 dimensions, hybrid search with RRF k = 60 |
| Dependency fingerprint | `9b571fec3b87` (`requirements.lock`) |
| Prompt fingerprint | `8db7c1c606d6` |
| Base image | `python:3.12-slim@sha256:a6e34c59…` |

## Known limitations

- The web demo answers with local `qwen2.5:3b`. The evaluated configuration used Gemini 3.8 Flash, which needs provider approval before it can be used with company data.
- No production deployment, SSO, backups or monitoring.
- See the Technical Handover document for the full list, security notes and outstanding approvals.
