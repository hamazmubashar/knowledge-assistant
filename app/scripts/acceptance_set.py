"""Load the sealed acceptance set without revealing it.

The expert delivers a CSV (see the writing guide). This module checks its fingerprint,
converts rows to the question format used by run_answer_eval, and validates them.
Error messages name only row ids and column names, never question text or answers,
so a failed load does not unseal the set.
"""
import csv
import hashlib
import io

TYPES = {"answerable", "conflict", "injection", "absent", "insufficient", "restricted"}
ROLES = {"support", "operations", "hr"}
GROUPS = {"general", "hr", "support", "operations"}
COLUMNS = ["id", "type", "role", "question", "must_contain", "must_not_contain",
           "expected_title", "expected_page", "conflict_titles", "forbidden_group", "comments"]
REQUIRED = {
    "answerable": ["must_contain", "expected_title", "expected_page"],
    "injection": ["must_contain", "must_not_contain", "expected_title", "expected_page"],
    "conflict": ["conflict_titles"],
    "restricted": ["forbidden_group"],
    "absent": [],
    "insufficient": [],
}


class SealError(SystemExit):
    pass


def fingerprint(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _split(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split(";") if x.strip()]


def load(raw: bytes, expected_sha256: str, known_titles: set[str]) -> list[dict]:
    sha = fingerprint(raw)
    if sha != expected_sha256.strip().lower():
        raise SealError("Fingerprint mismatch: this is not the sealed file Alex registered. Not running.")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    missing_cols = [c for c in COLUMNS if c not in (reader.fieldnames or []) and c != "comments"]
    if missing_cols:
        raise SealError(f"Missing columns: {', '.join(missing_cols)}")

    questions, errors, seen = [], [], set()
    for n, r in enumerate(reader, start=2):              # row 1 is the header
        rid = (r.get("id") or "").strip() or f"row {n}"
        qtype = (r.get("type") or "").strip().lower()
        role = (r.get("role") or "").strip().lower()
        if rid in seen:
            errors.append(f"{rid}: duplicate id")
        seen.add(rid)
        if qtype not in TYPES:
            errors.append(f"{rid}: type"); continue
        if role not in ROLES:
            errors.append(f"{rid}: role")
        if not (r.get("question") or "").strip():
            errors.append(f"{rid}: question")
        for col in REQUIRED[qtype]:
            if not (r.get(col) or "").strip():
                errors.append(f"{rid}: {col}")
        q = {"id": rid, "type": qtype, "role": role,
             "question": (r.get("question") or "").strip(),
             "must_contain": _split(r.get("must_contain")),
             "must_not_contain": _split(r.get("must_not_contain")),
             "expected_title": (r.get("expected_title") or "").strip(),
             "expected_page": None,
             "conflict_titles": _split(r.get("conflict_titles")),
             "forbidden_group": (r.get("forbidden_group") or "").strip().lower()}
        page = (r.get("expected_page") or "").strip()
        if page:
            if page.isdigit() and int(page) > 0:
                q["expected_page"] = int(page)
            else:
                errors.append(f"{rid}: expected_page")
        if q["expected_title"] and q["expected_title"] not in known_titles:
            errors.append(f"{rid}: expected_title not in corpus")
        if any(t not in known_titles for t in q["conflict_titles"]):
            errors.append(f"{rid}: conflict_titles not in corpus")
        if qtype == "conflict" and len(q["conflict_titles"]) < 2:
            errors.append(f"{rid}: conflict_titles needs two titles")
        if q["forbidden_group"] and q["forbidden_group"] not in GROUPS:
            errors.append(f"{rid}: forbidden_group")
        questions.append(q)
    if errors:
        raise SealError("The sealed set has problems (ids and columns only):\n  " + "\n  ".join(errors))
    if not questions:
        raise SealError("The sealed set is empty.")
    return questions


def counts(questions: list[dict]) -> dict:
    out = {t: 0 for t in sorted(TYPES)}
    for q in questions:
        out[q["type"]] += 1
    return out