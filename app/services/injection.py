import re

PATTERNS = {
    "ignore_instructions": re.compile(
        r"\b(ignore|disregard|forget)\b[^.]{0,40}\b(previous|prior|above|earlier|all)\b"
        r"[^.]{0,20}\b(instructions?|rules|prompts?)\b", re.I),
    "role_override": re.compile(r"\byou are now\b", re.I),
    "system_label": re.compile(r"\b(system|assistant|developer)\s+(notice|instruction|prompt|message)\s*:", re.I),
    "privileged_mode": re.compile(r"\b(admin|developer|god)\s+mode\b", re.I),
    "exfiltration": re.compile(r"\breveal\b[^.]{0,40}\b(salar\w*|passwords?|secrets?|confidential|all|every)\b", re.I),
    "tag_breakout": re.compile(r"<\s*/?\s*evidence", re.I),
}

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def find_injection(text: str) -> list[str]:
    return [name for name, p in PATTERNS.items() if p.search(text or "")]


def sanitize(text: str) -> tuple[str, int]:
    if not text:
        return text, 0
    sentences = _SENTENCE.split(text)
    kept = [s for s in sentences if not find_injection(s)]
    return " ".join(kept), len(sentences) - len(kept)


def filter_injected(sentences: list[dict]) -> tuple[list[dict], int]:
    kept = [s for s in sentences if not find_injection(s["text"]) and not find_injection(s["quote"])]
    return kept, len(sentences) - len(kept)