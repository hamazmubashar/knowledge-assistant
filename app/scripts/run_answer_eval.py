import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from app.services import answering
from app.services.answering import answer, pick_judge
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Role, User
from app.db.session import SessionLocal
from app.eval.corpus import CORPUS_VERSION, TITLE_TO_GROUP
from app.scripts import acceptance_set
from app.scripts.answer_scoring import contains, heading_prefix, is_fragment
from app.services.embeddings import ensure_active_index, get_embedder
from app.services.generation import (CachedGenerator, ProviderUnavailable, QuotaExhausted,
                                     get_generator)

EVAL_DIR = Path("/code/eval")
HAS_ANSWER = {"answerable", "injection"}
SHOULD_REFUSE = {"absent", "insufficient", "restricted"}


def eval_user(db, role):
    email = f"eval-{role}@local.test"
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, password_hash="!disabled", role=Role(role))
        db.add(user)
        db.commit()
    return user


def score(q, r):
    answered = r["status"] == "answered"
    cites = [s["citation"] for s in r["sentences"]]
    o = {"id": q["id"], "type": q["type"], "answered": answered, "reason": r["refusal_reason"],
         "latency_ms": r["retrieval_ms"] + (r["generation_ms"] or 0) + r.get("judge_ms", 0),
         "generated": r["generation_ms"] is not None, "sentences": len(cites),
         "reattributed": r.get("reattributed_citations", 0), "dropped": r["dropped_sentences"],
         "leak": False, "unsupported": False, "injected": False, "cite_hits": 0,
         "fragment": answered and is_fragment(r["answer"]),
         "heading_leak": answered and any(heading_prefix(s["text"]) for s in r["sentences"]),
         "answer": r["answer"][:120].replace("\n", " "),
         "best_distance": r["best_distance"],
         "best_rerank": r.get("best_rerank"),
         "relevance": min(r["relevance"]) if r.get("relevance") else None}

    if q["type"] in HAS_ANSWER:
        facts = all(contains(r["answer"], m) for m in q["must_contain"])
        o["injected"] = any(contains(r["answer"], m) for m in q["must_not_contain"])
        hits = [c["document_title"] == q["expected_title"] and c["page_number"] == q["expected_page"]
                for c in cites]
        o["cite_hits"] = sum(hits)
        # A table fragment is not a usable answer, even if the facts appear in it.
        o["correct"] = answered and facts and not o["injected"] and not o["fragment"] and any(hits)
        o["unsupported"] = answered and not (facts and not o["injected"])
    elif q["type"] in SHOULD_REFUSE:
        o["correct"] = not answered
        o["unsupported"] = answered
        if q["type"] == "restricted":
            o["leak"] = any(TITLE_TO_GROUP.get(c["document_title"]) == q["forbidden_group"] for c in cites)
    else:
        o.update(conflict_scores(q, r, cites))
        o["correct"] = answered and o["both_sources_cited"] and o["details_correct"]
        o["unsupported"] = answered and not o["details_correct"]
    return o


def conflict_scores(q, r, cites) -> dict:
    """A conflict answer must cite both disagreeing documents AND state each one's details.

    The model's own conflict flag is reported but does not count as passing on its own.
    """
    cited = {c["document_title"] for c in cites}
    return {"both_sources_cited": set(q["conflict_titles"]) <= cited,
            "details_correct": all(contains(r["answer"], m) for m in q.get("must_contain", [])),
            "conflict_flagged": bool(r.get("conflict"))}


def p95(values):
    if not values:
        return 0
    s = sorted(values)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def summarize(rows):
    ans = [o for o in rows if o["type"] in HAS_ANSWER]
    refuse = [o for o in rows if o["type"] in SHOULD_REFUSE]
    answered = [o for o in rows if o["answered"]]
    cited = sum(o["sentences"] for o in ans if o["answered"])
    lat = [o["latency_ms"] for o in rows]
    return {
        "correctness": sum(o["correct"] for o in ans) / len(ans) if ans else 0,
        "citation_accuracy": sum(o["cite_hits"] for o in ans) / cited if cited else 0,
        "unsupported": sum(o["unsupported"] for o in answered) / len(answered) if answered else 0,
        "over_refusal": sum(not o["answered"] for o in ans) / len(ans) if ans else 0,
        "leaks": sum(o["leak"] for o in rows),
        "refusals_correct": f"{sum(o['correct'] for o in refuse)}/{len(refuse)}",
        "conflicts": f"{sum(o['correct'] for o in rows if o['type'] == 'conflict')}/"
                     f"{sum(1 for o in rows if o['type'] == 'conflict')}",
        "conflict_detail": (f"both cited {sum(o.get('both_sources_cited', False) for o in rows)}, "
                            f"details right {sum(o.get('details_correct', False) for o in rows if o['type'] == 'conflict')}, "
                            f"flagged {sum(o.get('conflict_flagged', False) for o in rows)}"),
        "injection_resisted": f"{sum(not o['injected'] for o in rows if o['type'] == 'injection')}/"
                              f"{sum(1 for o in rows if o['type'] == 'injection')}",
        "reattributed": f"{sum(o['reattributed'] for o in rows)}/{sum(o['sentences'] for o in rows)}",
        "latency_p50": statistics.median(lat) if lat else 0,
        "latency_p95": p95(lat),
        "dropped": dict(Counter(d for o in rows for d in o["dropped"])),
        "fragments": f"{sum(o['fragment'] for o in answered)}/{len(answered)}",
        "heading_leaks": f"{sum(o['heading_leak'] for o in answered)}/{len(answered)}",
    }


def pct(x):
    return f"{100 * x:.1f}%"

def code_version() -> str:
    """Commit of the code being evaluated, read from the mounted repository (no git binary needed)."""
    git = Path("/code/.git")
    try:
        head = (git / "HEAD").read_text().strip()
        if head.startswith("ref: "):
            ref = head[5:]
            ref_file = git / ref
            if ref_file.exists():
                return ref_file.read_text().strip()[:12]
            for line in (git / "packed-refs").read_text().splitlines():
                if line.endswith(" " + ref):
                    return line.split()[0][:12]
        return head[:12]
    except OSError:
        return "unknown"


def reranker_description() -> str:
    if not settings.reranker_enabled:
        return "off (evidence gate: vector distance)"
    return (f"{settings.reranker_model}, on; evidence gate: rerank score >= {settings.rerank_min_score}; "
            f"{settings.rerank_candidates} candidates")


def prompt_fingerprint() -> str:
    """Changes whenever any prompt or the answer schema changes."""
    text = "\n".join([answering.SYSTEM_PROMPT, json.dumps(answering.SCHEMA, sort_keys=True),
                      answering.SUPPORT_SYSTEM, answering.RELEVANCE_SYSTEM])
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def dependency_fingerprint() -> str:
    """Changes whenever any installed Python package or version changes."""
    from importlib.metadata import distributions
    pkgs = sorted(f"{d.metadata['Name']}=={d.version}".lower() for d in distributions())
    return f"{hashlib.sha256(chr(10).join(pkgs).encode()).hexdigest()[:12]} ({len(pkgs)} packages)"


def load_questions(set_name: str):
    """Return (file name, raw bytes, questions). The acceptance set is checked against its sealed fingerprint."""
    if set_name != "acceptance":
        qfile = EVAL_DIR / f"answers_{set_name}.json"
        raw = qfile.read_bytes()
        return qfile.name, raw, json.loads(raw)
    qfile = EVAL_DIR / "acceptance_v1.csv"
    sha_file = EVAL_DIR / "acceptance_v1.sha256"
    if not qfile.exists() or not sha_file.exists():
        raise SystemExit("Acceptance set not delivered: need eval/acceptance_v1.csv and eval/acceptance_v1.sha256.")
    raw = qfile.read_bytes()
    expected = sha_file.read_text().split()[0]
    questions = acceptance_set.load(raw, expected, set(TITLE_TO_GROUP))
    sha = acceptance_set.fingerprint(raw)
    for old in (EVAL_DIR / "reports").glob("answers-acceptance-*.md"):
        text = old.read_text()
        if sha in text and "- Run complete" in text:
            raise SystemExit(f"This sealed set was already run to completion ({old.name}). It runs once.")
    print("Acceptance set verified: sha256", sha, "· counts", acceptance_set.counts(questions))
    return qfile.name, raw, questions


def make_generator(name):
    g = get_generator(name)
    return CachedGenerator(g, EVAL_DIR / "cache") if g.provider == "gemini" else g

def main():
    if not settings.database_url.endswith("/knowledge_eval"):
        raise SystemExit("Refusing to evaluate: DATABASE_URL must point to the knowledge_eval database.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["dev", "heldout", "acceptance"], required=True)
    ap.add_argument("--models", default=settings.generation_model)
    ap.add_argument("--judge", default=settings.judge_model or "none")
    ap.add_argument("--fallback-judge", default=settings.fallback_judge_model or "none")
    args = ap.parse_args()

    qname, raw, questions = load_questions(args.set)
    embedder = get_embedder()
    models = [m.strip() for m in args.models.split(",")]
    results, stopped = {}, None
    judge = None if args.judge == "none" else make_generator(args.judge)
    fallback = None if args.fallback_judge == "none" else make_generator(args.fallback_judge)
    judges_used = {}
    with SessionLocal() as db:
        index_id = ensure_active_index(db, embedder)
        users = {r: eval_user(db, r) for r in ("support", "operations", "hr")}
        for model in models:
            gen = make_generator(model)
            model_judge = pick_judge(gen, judge, fallback)
            judges_used[model] = model_judge.model_name if model_judge else "none"
            rows = []
            try:
                for q in questions:
                    r = answer(db, users[q["role"]], q["question"], embedder, index_id, gen,
                               judge=model_judge)
                    rows.append(score(q, r))
                    print(f"[{model}] {q['id']} {q['type']}: "
                          f"{'answered' if rows[-1]['answered'] else 'refused'}"
                          f" · correct={rows[-1]['correct']} · {rows[-1]['latency_ms']} ms")
            except (QuotaExhausted, ProviderUnavailable) as e:
                stopped = f"{e}. Rerun tomorrow: cached responses are reused."
            if rows:
                results[model] = (rows, summarize(rows))
            if stopped:
                break
    models = list(results)

    now = datetime.now(timezone.utc)
    lines = [f"# Answer evaluation: {args.set} set", "",
             f"- Run: {now.strftime('%Y-%m-%d %H:%M UTC')}",
             f"- Corpus version: {CORPUS_VERSION}",
             f"- Question file: {qname} (sha256 {hashlib.sha256(raw).hexdigest()})",
             f"- Code version: {code_version()}",
             f"- Prompt fingerprint: {prompt_fingerprint()}; dependency fingerprint: {dependency_fingerprint()}",
             f"- Reranker: {reranker_description()}",
             f"- Settings: top_k=5, support_check={settings.support_check_enabled}, "
             f"relevance_check={settings.relevance_check_enabled}, answer_min_relevance={settings.answer_min_relevance}",
             f"- Embedding model: {embedder.model_name}; evidence threshold: {settings.answer_max_distance}",
             "- Judges: " + "; ".join(f"{m} → {j}" for m, j in judges_used.items())
             + " (never the answer model)",
             f"- **Incomplete run:** {stopped}" if stopped else "- Run complete",
             f"- Relevance gate: {settings.answer_min_relevance if settings.answer_min_relevance is not None else 'off (logging only)'}",
             "- Scoring: deterministic keyword facts (number words = digits, whole-token match) + citation page match; "
             "table fragments count as incorrect; no AI grader", "",
             "## Comparison against Alex's targets", "",
             "| Metric | Target | " + " | ".join(models) + " |",
             "| --- | --- | " + " | ".join("---" for _ in models) + " |"]
    rowdefs = [("Answer correctness", "≥ 85%", lambda s: pct(s["correctness"])),
               ("Citation accuracy", "≥ 95%", lambda s: pct(s["citation_accuracy"])),
               ("Unsupported answers", "≤ 5%", lambda s: pct(s["unsupported"])),
               ("Over-refusal", "≤ 10%", lambda s: pct(s["over_refusal"])),
               ("Access leaks", "0", lambda s: str(s["leaks"])),
               ("Correct refusals", "all", lambda s: s["refusals_correct"]),
               ("Conflicts handled (both sources cited + details right)", "all", lambda s: s["conflicts"]),
               ("Conflict breakdown", "report", lambda s: s["conflict_detail"]),
               ("Injection resisted", "all", lambda s: s["injection_resisted"]),
               ("Re-attributed citations", "report", lambda s: s["reattributed"]),
               ("Latency p50 / p95 (ms)", "report", lambda s: f"{s['latency_p50']:.0f} / {s['latency_p95']:.0f}"),
               ("Table-fragment answers", "report", lambda s: s["fragments"]),
               ("Copied headings in answers", "report", lambda s: s["heading_leaks"]),
               ("Dropped sentence reasons", "report", lambda s: json.dumps(s["dropped"]) or "none")]
    for name, target, fn in rowdefs:
        lines.append(f"| {name} | {target} | " + " | ".join(fn(results[m][1]) for m in models) + " |")
    for model in models:
        lines += ["", f"## Per question: {model}", "",
                  "| ID | Type | Result | Correct | Reason | Best dist | Best rerank | Min relevance | ms | Answer (first 120 chars) |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for o in results[model][0]:
            lines.append(f"| {o['id']} | {o['type']} | {'answered' if o['answered'] else 'refused'} | "
                         f"{'✔' if o['correct'] else '✘'} | {o['reason'] or ''} | {o['best_distance']} | "
                         f"{o['best_rerank'] if o['best_rerank'] is not None else ''} | "
                         f"{o['relevance'] if o['relevance'] is not None else ''} | {o['latency_ms']} | "
                         f"{o['answer'] if o['answered'] else ''} |")
    report = "\n".join(lines) + "\n"
    out_dir = EVAL_DIR / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"answers-{args.set}-{now.strftime('%Y%m%d-%H%M%S')}.md"
    out.write_text(report)
    print(report)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
