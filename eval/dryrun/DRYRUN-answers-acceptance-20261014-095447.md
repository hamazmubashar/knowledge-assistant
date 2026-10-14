# Answer evaluation: acceptance set

- Run: 2026-10-14 09:54 UTC
- Corpus version: 2026-10-11.1
- Question file: acceptance_v1.csv (sha256 7c2eb9c95de0e2944d8d14a2b424e954378f1198b0c2bb7783ed1038c6b025d8)
- Code version: 857b544316ff
- Prompt fingerprint: 8db7c1c606d6; dependency fingerprint: 9b571fec3b87 (77 packages)
- Reranker: off (evidence gate: vector distance)
- Settings: top_k=5, support_check=True, relevance_check=True, answer_min_relevance=None
- Embedding model: BAAI/bge-small-en-v1.5; evidence threshold: 0.35
- Judges: gemini:gemini-3.8-flash → gemini-3.5-flash-lite (never the answer model)
- Run complete
- Relevance gate: off (logging only)
- Scoring: deterministic keyword facts (number words = digits, whole-token match) + citation page match; table fragments count as incorrect; no AI grader

## Comparison against Alex's targets

| Metric | Target | gemini:gemini-3.8-flash |
| --- | --- | --- |
| Answer correctness | ≥ 85% | 100.0% |
| Citation accuracy | ≥ 95% | 100.0% |
| Unsupported answers | ≤ 5% | 0.0% |
| Over-refusal | ≤ 10% | 0.0% |
| Access leaks | 0 | 0 |
| Correct refusals | all | 1/1 |
| Conflicts handled (both sources cited + details right) | all | 1/1 |
| Conflict breakdown | report | both cited 1, details right 1, flagged 1 |
| Injection resisted | all | 0/0 |
| Re-attributed citations | report | 0/3 |
| Latency p50 / p95 (ms) | report | 27933 / 62233 |
| Table-fragment answers | report | 0/2 |
| Copied headings in answers | report | 0/2 |
| Dropped sentence reasons | report | {} |

## Per question: gemini:gemini-3.8-flash

| ID | Type | Result | Correct | Reason | Best dist | Best rerank | Min relevance | ms | Answer (first 120 chars) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q01 | answerable | answered | ✔ |  | 0.1108 |  | 0.837 | 8231 | Full-time staff receive 20 days of paid annual leave each year. |
| q02 | absent | refused | ✔ | model_declined | 0.3141 |  |  | 62233 |  |
| q03 | conflict | answered | ✔ |  | 0.202 |  | 0.789 | 27933 | According to one source, employees are permitted to work from home up to 2 days per week. According to an office attenda |
