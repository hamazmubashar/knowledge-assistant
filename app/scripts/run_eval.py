import argparse
import hashlib
import json
from app.core.config import settings
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.db.models import Role, User
from app.db.session import SessionLocal
from app.eval.corpus import TITLE_TO_GROUP
from app.services import retrieval
from app.services.embeddings import ensure_active_index, get_embedder

EVAL_DIR = Path("/code/eval")


def eval_user(db, role):
    email = f"eval-{role}@local.test"
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash="!disabled", role=Role(role))
        db.add(user)
        db.commit()
    return user


def rank_of(results, title, page=None):
    for i, r in enumerate(results, start=1):
        if r["document_title"] == title and (page is None or r["page_number"] == page):
            return i
    return None


def pct(n, d):
    return f"{100 * n / d:.1f}%" if d else "n/a"


def main():
    if not settings.database_url.endswith("/knowledge_eval"):
        raise SystemExit("Refusing to evaluate: DATABASE_URL must point to the knowledge_eval database.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["dev", "heldout"], required=True)
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    qfile = EVAL_DIR / f"questions_{args.set}.json"
    raw = qfile.read_bytes()
    questions = json.loads(raw)
    embedder = get_embedder()

    answerable, restricted, unanswerable = [], [], []
    with SessionLocal() as db:
        index_id = ensure_active_index(db, embedder)
        users = {r: eval_user(db, r) for r in ("support", "operations", "hr")}
        for q in questions:
            res = retrieval.search(db, users[q["role"]], q["question"], embedder, index_id, k=args.k)
            top3 = [f"{r['document_title']} p{r['page_number']}" for r in res[:3]]
            if q["type"] == "answerable":
                answerable.append({**q, "page_rank": rank_of(res, q["expected_title"], q["expected_page"]),
                                   "doc_rank": rank_of(res, q["expected_title"]), "top3": top3})
            elif q["type"] == "restricted":
                forbidden = TITLE_TO_GROUP[q["expected_title"]]
                leaked = [r for r in res if r["access_group"] == forbidden
                          or r["document_title"] == q["expected_title"]]
                restricted.append({**q, "leaks": len(leaked), "top3": top3})
            else:
                unanswerable.append({**q, "top3": top3})

    n = len(answerable)
    page_hits = sum(1 for a in answerable if a["page_rank"])
    doc_hits = sum(1 for a in answerable if a["doc_rank"])
    mrr = sum(1 / a["page_rank"] for a in answerable if a["page_rank"]) / n if n else 0
    total_leaks = sum(r["leaks"] for r in restricted)

    by_group, by_kind = defaultdict(list), defaultdict(list)
    for a in answerable:
        by_group[TITLE_TO_GROUP[a["expected_title"]]].append(a)
        by_kind[a["kind"]].append(a)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Retrieval evaluation: {args.set} set", "",
        f"- Run: {now}",
        f"- Question file: {qfile.name} (sha256 {hashlib.sha256(raw).hexdigest()[:12]})",
        f"- Embedding model: {embedder.model_name} (index {index_id})",
        f"- k = {args.k}, candidates per search = 20, RRF k = {retrieval.RRF_K}", "",
        "## Summary", "",
        "| Metric | Value |", "| --- | --- |",
        f"| Answerable questions | {n} |",
        f"| Recall@{args.k} (correct page) | {pct(page_hits, n)} ({page_hits}/{n}) |",
        f"| Recall@{args.k} (correct document) | {pct(doc_hits, n)} ({doc_hits}/{n}) |",
        f"| MRR (correct page) | {mrr:.3f} |",
        f"| Restricted questions | {len(restricted)} |",
        f"| Leaked restricted results | {total_leaks} |", "",
        "## By access group (answerable)", "",
        "| Group | Questions | Recall@k (page) | MRR |", "| --- | --- | --- | --- |",
    ]
    for g, items in sorted(by_group.items()):
        h = sum(1 for a in items if a["page_rank"])
        m = sum(1 / a["page_rank"] for a in items if a["page_rank"]) / len(items)
        lines.append(f"| {g} | {len(items)} | {pct(h, len(items))} | {m:.3f} |")
    lines += ["", "## By question kind (answerable)", "",
              "| Kind | Questions | Recall@k (page) |", "| --- | --- | --- |"]
    for kind, items in sorted(by_kind.items()):
        h = sum(1 for a in items if a["page_rank"])
        lines.append(f"| {kind} | {len(items)} | {pct(h, len(items))} |")
    lines += ["", "## Failure cases (correct page not in top k)", ""]
    fails = [a for a in answerable if not a["page_rank"]]
    if not fails:
        lines.append("None.")
    for a in fails:
        lines.append(f"- **{a['id']}** ({a['role']}, {a['kind']}): {a['question']}  ")
        lines.append(f"  Expected: {a['expected_title']} p{a['expected_page']} · "
                     f"document rank: {a['doc_rank']} · got: {'; '.join(a['top3']) or 'nothing'}")
    lines += ["", "## Restricted questions", ""]
    for r in restricted:
        lines.append(f"- **{r['id']}** ({r['role']}): {r['question']} · leaks: {r['leaks']} · "
                     f"got: {'; '.join(r['top3']) or 'nothing'}")
    lines += ["", "## Unanswerable questions (input for Week 3 refusal logic)", ""]
    for u in unanswerable:
        lines.append(f"- **{u['id']}** ({u['role']}): {u['question']} · "
                     f"got: {'; '.join(u['top3']) or 'nothing'}")

    report = "\n".join(lines) + "\n"
    out_dir = EVAL_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.set}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    out.write_text(report)
    print(report)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()