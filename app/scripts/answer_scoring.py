"""Deterministic answer scoring helpers for the evaluation scripts.

Rules (each one makes the measurement more accurate, not more lenient or strict for its own sake):
- Numbers written as words count the same as digits ("six-month" == "6-month").
- Facts must match as whole words/numbers ("6" does not match inside "16").
- An answer containing a table separator ("|") is a fragment, not a usable answer.
- A sentence that starts with a copied ALL-CAPS heading is reported as a readability defect.
"""
import re

NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "thirteen": "13", "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
    "fifty": "50", "sixty": "60", "ninety": "90", "hundred": "100",
}
_NUMBER_WORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b")
_HEADING_PREFIX = re.compile(r"^([A-Z][A-Z&'/-]*(?:[ \t]+[A-Z][A-Z&'/-]*)*)\s+[A-Z]?[a-z]")


def normalize(text: str) -> str:
    t = text.lower()
    t = _NUMBER_WORD.sub(lambda m: NUMBER_WORDS[m.group(1)], t)
    t = re.sub(r"[\u2010-\u2015/-]", " ", t)          # hyphens, dashes, slashes -> space
    t = re.sub(r"[^\w\s.%|]", " ", t)                  # drop other punctuation, keep . % |
    t = re.sub(r"\.(?!\d)", " ", t)                    # sentence dots go, decimal points stay
    return re.sub(r"\s+", " ", t).strip()


def contains(text: str, phrase: str) -> bool:
    p = normalize(phrase)
    if not p:
        return False
    return re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", normalize(text)) is not None


def is_fragment(answer: str) -> bool:
    return "|" in answer


def heading_prefix(sentence: str) -> str | None:
    m = _HEADING_PREFIX.match(sentence.strip())
    if not m:
        return None
    prefix = " ".join(m.group(1).split())
    return prefix if len(prefix.replace(" ", "")) >= 4 else None   # "HR staff" is not a heading