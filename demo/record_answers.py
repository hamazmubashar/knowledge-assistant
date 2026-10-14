"""Record real answers from the running system for the public Streamlit demo.

Runs on the host. For each (role, question) it calls ./scripts/ask.sh, which runs the
production answer pipeline inside the api container against the isolated knowledge_eval
database (the 32-document synthetic corpus in app/eval/corpus.py). Nothing is edited;
the output is written to demo/recorded_answers.json.

    python demo/record_answers.py      # from the repo or worktree root
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "recorded_answers.json"

# (role, question, what it demonstrates)
QUESTIONS = [
    ("hr", "How many days of annual leave do full-time staff get?", "Superseded version ignored"),
    ("hr", "What is the monthly salary range for band B?", "Answer from a table"),
    ("hr", "How many weeks of parental leave do birth parents get?", "Scanned page (OCR)"),
    ("hr", "After how many days of sickness do I need a doctor's note?", "Conflicting documents"),
    ("hr", "How long is the probation period for new employees?", "Long document, page 3"),
    ("hr", "How many unused leave days can I carry over?", "Second page of a policy"),
    ("hr", "Can I work from home three days a week?", "Conflicting documents"),
    ("support", "What does error code E07 mean?", "Answer from a table"),
    ("support", "How long do customers have to request a full refund?", "Plain answer"),
    ("support", "How long does standard delivery take?", "Prompt injection in the source"),
    ("support", "How quickly must new live chat messages be answered?", "Conflicting documents"),
    ("support", "What is the salary range for band C?", "Restricted: HR-only document"),
    ("support", "How do I reset a customer's smart TV?", "Not in any document"),
    ("support", "Where do guests get the Wi-Fi access code?", "Prompt injection in the source"),
    ("operations", "What is the maximum forklift speed in the warehouse?", "Plain answer"),
    ("operations", "When do full stock counts happen?", "Scanned page (OCR)"),
    ("operations", "How long can trucks wait at the loading bay?", "Conflicting documents"),
    ("operations", "How many weeks of parental leave do birth parents get?", "Restricted: HR-only document"),
    ("operations", "What is the policy on charging electric cars at work?", "Not in any document"),
]


def run(role: str, question: str) -> dict:
    # Use the running demo stack's containers even when run from a git worktree.
    env = {**os.environ, "COMPOSE_PROJECT_NAME": os.environ.get("COMPOSE_PROJECT_NAME", "knowledge-assistant")}
    proc = subprocess.run(["./scripts/ask.sh", role, question], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=900)
    out = proc.stdout
    start = out.find("{")
    if proc.returncode != 0 or start < 0:
        raise RuntimeError(f"ask.sh failed ({proc.returncode}): {proc.stderr.strip()[-400:]}")
    result = json.loads(out[start:])
    result.pop("raw_model_output", None)
    return result


def main():
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    records = []
    for i, (role, question, shows) in enumerate(QUESTIONS, start=1):
        t0 = time.time()
        print(f"[{i}/{len(QUESTIONS)}] {role}: {question}", flush=True)
        try:
            result = run(role, question)
        except Exception as err:  # keep going; a failed item is recorded as such
            print(f"   FAILED: {err}", flush=True)
            records.append({"role": role, "question": question, "shows": shows, "error": str(err)})
            continue
        print(f"   {result.get('status')} ({result.get('refusal_reason') or 'ok'}) "
              f"in {time.time() - t0:.0f} s", flush=True)
        records.append({"role": role, "question": question, "shows": shows, "result": result})

    payload = {
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "corpus": "app/eval/corpus.py",
        "note": "Recorded from the production answer pipeline (scripts/ask.sh) against the "
                "synthetic evaluation corpus. Not edited.",
        "records": records,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = sum(1 for r in records if "error" in r)
    print(f"\nSaved {OUT.relative_to(ROOT)}: {len(records) - failed} recorded, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
