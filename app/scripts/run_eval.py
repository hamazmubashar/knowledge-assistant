import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.models import DocumentVersion, Role, User, VersionStatus
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


def stats(items):
    n = len(items)
    hits = sum(1 for a in items if a["page_rank"])
    top1 = sum(1 for a in items if a["page_rank"] == 1)
    mrr = sum(1 / a["page_rank"] for a in items if a["page_rank"]) / n if n else 0
    return n, hits, top1, mrr


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
    superseded_hits = 0
    with SessionLocal() as db:
        index_id = ensure_active_index(db, embedder)
        superseded = {str(v) for v in db.scalars(
            select(DocumentVersion.id).where(DocumentVersion.status == VersionStatus.superseded))}
        users = {r: eval_user(db, r) for r in ("support", "operations", "hr")}
        for q in questions:
            res = retrieval.search(db, users[q["role"]], q["question"], embedder, index_id, k=args.k)
            superseded_hits += sum(1 for r in res if r["version_id"] in superseded)
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

    n, hits, top1, mrr = stats(answerable)
    doc_hits = sum(1 for a in answerable if a["doc_rank"])
    leaks = sum(r["leaks"] for r in restricted)
    by_group, by_kind = defaultdict(list), defaultdict(list)
    for a in answerable:
        by_group[TITLE_TO_GROUP[a["expected_title"]]].append(a)
        by_kind[a["kind"]].append(a)

    now = datetime.now(timezone.utc)
    lines = [
        f"# Retrieval evaluation: {args.set} set", "",
        f"- Run: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Question file: {qfile.name} (sha256 {hashlib.sha256(raw).hexdigest()[:12]})",
        f"- Embedding model: {embedder.model_name} (index {index_id})",
        f"- k = {args.k}, candidates per search = 20, RRF k = {retrieval.RRF_K}", "",
        "## Summary", "",
        "| Metric | Value |", "| --- | --- |",
        f"| Answerable questions | {n} |",
        f"| Recall@1 (correct page ranked first) | {pct(top1, n)} ({top1}/{n}) |",
        f"| Recall@{args.k} (correct page) | {pct(hits, n)} ({hits}/{n}) |",
        f"| Recall@{args.k} (correct document) | {pct(doc_hits, n)} ({doc_hits}/{n}) |",
        f"| MRR (correct page) | {mrr:.3f} |",
        f"| Restricted questions / leaked results | {len(restricted)} / {leaks} |",
        f"| Results from superseded versions | {superseded_hits} |", "",
        "## By access group (answerable)", "",
        "| Group | Questions | Recall@1 | Recall@k | MRR |", "| --- | --- | --- | --- | --- |",
    ]
    for g, items in sorted(by_group.items()):
        gn, gh, g1, gm = stats(items)
        lines.append(f"| {g} | {gn} | {pct(g1, gn)} | {pct(gh, gn)} | {gm:.3f} |")
    lines += ["", "## By question kind (answerable)", "",
              "| Kind | Questions | Recall@1 | Recall@k |", "| --- | --- | --- | --- |"]
    for kind, items in sorted(by_kind.items()):
        kn, kh, k1, _ = stats(items)
        lines.append(f"| {kind} | {kn} | {pct(k1, kn)} | {pct(kh, kn)} |")

    lines += ["", "## Not ranked first (ranking weaknesses)", ""]
    weak = [a for a in answerable if a["page_rank"] != 1]
    lines += [f"- **{a['id']}** ({a['role']}, {a['kind']}): {a['question']}  \n"
              f"  Expected: {a['expected_title']} p{a['expected_page']} · page rank: {a['page_rank']} · "
              f"got: {'; '.join(a['top3']) or 'nothing'}" for a in weak] or ["None."]
    lines += ["", "## Restricted questions", ""]
    lines += [f"- **{r['id']}** ({r['role']}): {r['question']} · leaks: {r['leaks']} · "
              f"got: {'; '.join(r['top3']) or 'nothing'}" for r in restricted]
    lines += ["", "## Unanswerable questions (input for Week 3 refusal logic)", ""]
    lines += [f"- **{u['id']}** ({u['role']}): {u['question']} · "
              f"got: {'; '.join(u['top3']) or 'nothing'}" for u in unanswerable]

    report = "\n".join(lines) + "\n"
    out_dir = EVAL_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.set}-{now.strftime('%Y%m%d-%H%M%S')}.md"
    out.write_text(report)
    print(report)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()