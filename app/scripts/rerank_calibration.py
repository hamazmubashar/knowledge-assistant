"""Choose the reranker cut-off from DEV data only, without calling any language model.

For each dev question, prints the best reranker score and best vector distance among the
passages the asking role can see, then checks whether either signal separates questions that
should be answered from those that should be refused.

Run after ./scripts/eval.sh dev (which builds the eval database), with the reranker on:
  docker compose exec -T -e RERANKER_ENABLED=true api sh -c \
    'export DATABASE_URL="${DATABASE_URL%/*}/knowledge_eval" STORAGE_BUCKET=eval-documents;
     python -m app.scripts.rerank_calibration'
Never point it at the held-out or acceptance sets.
"""
import json
from pathlib import Path

from app.core.config import settings
from app.db.session import SessionLocal
from app.scripts.run_answer_eval import eval_user
from app.services import retrieval
from app.services.embeddings import ensure_active_index, get_embedder

EVAL_DIR = Path("/code/eval")
ANSWER = {"answerable", "injection", "conflict"}
REFUSE = {"absent", "insufficient"}          # restricted is handled by access control, not the gate


def labelled_dev_questions():
    out = []
    for q in json.loads((EVAL_DIR / "answers_dev.json").read_text()):
        if q["type"] in ANSWER | REFUSE:
            out.append((q["id"], q.get("role", "hr"), q["question"], q["type"] in ANSWER))
    for q in json.loads((EVAL_DIR / "questions_dev.json").read_text()):
        if q.get("forbidden_group") or q.get("kind") == "restricted" or q.get("type") == "restricted":
            continue
        should_answer = bool(q.get("expected_title"))
        out.append((q["id"], q.get("role", "hr"), q["question"], should_answer))
    return out


def separation(name, answer_vals, refuse_vals, higher_is_better):
    if not answer_vals or not refuse_vals:
        return f"{name}: not enough labelled questions"
    if higher_is_better:
        worst_answer, best_refuse = min(answer_vals), max(refuse_vals)
        gap = worst_answer - best_refuse
    else:
        worst_answer, best_refuse = max(answer_vals), min(refuse_vals)
        gap = best_refuse - worst_answer
    if gap > 0:
        cut = round((worst_answer + best_refuse) / 2, 4)
        return (f"{name}: SEPARATES. weakest should-answer {worst_answer:.4f}, strongest should-refuse "
                f"{best_refuse:.4f}, gap {gap:.4f}, midpoint {cut}")
    return (f"{name}: OVERLAPS by {-gap:.4f} (weakest should-answer {worst_answer:.4f}, "
            f"strongest should-refuse {best_refuse:.4f})")


def main():
    if not settings.database_url.endswith("/knowledge_eval"):
        raise SystemExit("Refusing: DATABASE_URL must point to the knowledge_eval database.")
    if not settings.reranker_enabled:
        raise SystemExit("Run with RERANKER_ENABLED=true so reranker scores are produced.")
    embedder = get_embedder()
    rows = []
    with SessionLocal() as db:
        index_id = ensure_active_index(db, embedder)
        users = {}
        for qid, role, question, should_answer in labelled_dev_questions():
            user = users.setdefault(role, eval_user(db, role))
            results = retrieval.search(db, user, question, embedder, index_id, k=5)
            best_rr = max((r["rerank_score"] for r in results), default=None)
            dists = [r["distance"] for r in results if r["distance"] is not None]
            rows.append((qid, should_answer, best_rr, min(dists) if dists else None))

    print(f"Reranker: {settings.reranker_model}; candidates {settings.rerank_candidates}")
    print("| ID | Should | Best rerank | Best distance |")
    print("| --- | --- | --- | --- |")
    for qid, ans, rr, d in sorted(rows, key=lambda r: (r[1], r[2] if r[2] is not None else -99)):
        print(f"| {qid} | {'answer' if ans else 'refuse'} | {rr} | {d} |")
    ans_rr = [r[2] for r in rows if r[1] and r[2] is not None]
    ref_rr = [r[2] for r in rows if not r[1] and r[2] is not None]
    ans_d = [r[3] for r in rows if r[1] and r[3] is not None]
    ref_d = [r[3] for r in rows if not r[1] and r[3] is not None]
    print()
    print(f"Questions: {len(ans_rr)} should answer, {len(ref_rr)} should refuse (dev only)")
    print(separation("Reranker score", ans_rr, ref_rr, higher_is_better=True))
    print(separation("Vector distance", ans_d, ref_d, higher_is_better=False))


if __name__ == "__main__":
    main()
