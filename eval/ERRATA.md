# Development answer-key errata

Corrections to development answer keys. Historical reports are never edited; each correction
is its own commit, and reports produced before it keep the original scoring.

## E1 — d09 (warranty, device dropped in a pool) — 2026-10-14

- Original key: must_contain ["water damage", "not covered"]
- Problem: the key required exact wording. Gemini 3.8 Flash answered correctly
  ("Water damage and physical damage are excluded from warranty coverage.") and was scored incorrect.
- Effect on the reported result (report answers-dev-20261013-213421.md, cut-off 0.35, commit 58e5eb0):
  3.8 Flash correctness 85.7% (would be 92.9%), unsupported answers 7.1% (would be 0%).
  The reported figures stand as published.
- Corrected key: must_contain ["water damage"], must_not_contain ["is covered", "are covered"]
  (an answer saying water damage IS covered still fails).
- Found by: development team, after seeing the result. Reported to Alex Morgan on 2026-10-14
  before correction.