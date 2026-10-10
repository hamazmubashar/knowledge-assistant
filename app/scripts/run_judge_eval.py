import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.answering import (RELEVANCE_SCHEMA, RELEVANCE_SYSTEM, SUPPORT_SCHEMA,
                                    SUPPORT_SYSTEM)
from app.services.generation import (CachedGenerator, ProviderUnavailable, QuotaExhausted,
                                     get_generator)

EVAL_DIR = Path("/code/eval")


def make_judge(name):
    g = get_generator(name)
    return CachedGenerator(g, EVAL_DIR / "cache") if g.provider == "gemini" else g


def ask(judge, case):
    if case["type"] == "relevance":
        gen = judge.generate(RELEVANCE_SYSTEM,
                             f"Question: {case['question']}\nAnswer sentence: {case['sentence']}",
                             RELEVANCE_SCHEMA)
        key = "relevant"
    else:
        gen = judge.generate(SUPPORT_SYSTEM, f"Claim: {case['claim']}\nQuote: {case['quote']}",
                             SUPPORT_SCHEMA)
        key = "supported"
    try:
        return json.loads(gen.text).get(key) is True, gen.latency_ms
    except (json.JSONDecodeError, AttributeError):
        return False, gen.latency_ms


def metrics(rows):
    pos = [r for r in rows if r["label"]]
    neg = [r for r in rows if not r["label"]]
    return {
        "n": len(rows),
        "accuracy": sum(r["pred"] == r["label"] for r in rows) / len(rows) if rows else 0,
        "false_accepts": f"{sum(r['pred'] for r in neg)}/{len(neg)}",
        "false_rejects": f"{sum(not r['pred'] for r in pos)}/{len(pos)}",
        "median_ms": statistics.median(r["ms"] for r in rows) if rows else 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judges", default=settings.judge_model)
    args = ap.parse_args()
    cases = json.loads((EVAL_DIR / "judge_cases.json").read_text())
    now = datetime.now(timezone.utc)
    lines = [f"# Judge accuracy test", "", f"- Run: {now.strftime('%Y-%m-%d %H:%M UTC')}",
             f"- Cases: {len(cases)} (labels written by the developer, not yet SME-reviewed)", ""]

    for name in [j.strip() for j in args.judges.split(",")]:
        judge, rows, stopped = make_judge(name), [], None
        for case in cases:
            try:
                pred, ms = ask(judge, case)
            except (QuotaExhausted, ProviderUnavailable) as e:
                stopped = str(e)
                break
            rows.append({**case, "pred": pred, "ms": ms})
            print(f"[{name}] {case['id']}: label={case['label']} judge={pred}")
        lines += [f"## Judge: {name}", "",
                  f"- **Incomplete:** {stopped}" if stopped else "- Complete", "",
                  "| Check | Cases | Accuracy | False accepts (dangerous) | False rejects | Median ms |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for kind in ("relevance", "support"):
            m = metrics([r for r in rows if r["type"] == kind])
            lines.append(f"| {kind} | {m['n']} | {100 * m['accuracy']:.0f}% | {m['false_accepts']} | "
                         f"{m['false_rejects']} | {m['median_ms']:.0f} |")
        errors = [r for r in rows if r["pred"] != r["label"]]
        lines += ["", "Disagreements:" if errors else "No disagreements."]
        for r in errors:
            text = r.get("sentence") or r.get("claim")
            lines.append(f"- {r['id']} ({r['type']}): label {r['label']}, judge {r['pred']}: {text}")
        lines.append("")

    report = "\n".join(lines)
    out = EVAL_DIR / "reports" / f"judge-{now.strftime('%Y%m%d-%H%M%S')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(report)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
    