import re
from dataclasses import dataclass

TARGET_WORDS = 220
MAX_WORDS = 300
OVERLAP_WORDS = 40
LOW_OCR_CONFIDENCE = 70.0
TOKENS_PER_WORD = 1.33

_NUMBERED = re.compile(r"^(\d+(\.\d+)*\.?|[A-Z]\.)\s+\S")


@dataclass
class PageInput:
    page_number: int
    text: str
    is_ocr: bool = False
    ocr_confidence: float | None = None


@dataclass
class ChunkOut:
    page_number: int
    chunk_index: int
    heading: str | None
    text: str
    word_count: int
    token_estimate: int
    low_confidence: bool


def is_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 80 or len(s.split()) > 12:
        return False
    if s.endswith((".", ",", ";")):
        return False
    if s.endswith(":") or _NUMBERED.match(s):
        return True
    letters = [c for c in s if c.isalpha()]
    if len(letters) >= 3 and all(c.isupper() for c in letters):
        return True
    words = [w for w in s.split() if w[0].isalpha()]
    return len(words) >= 2 and all(w[0].isupper() for w in words)


def chunk_pages(pages: list[PageInput]) -> list[ChunkOut]:
    out: list[ChunkOut] = []
    heading: str | None = None

    for page in pages:
        low = page.is_ocr and (page.ocr_confidence is None
                               or page.ocr_confidence < LOW_OCR_CONFIDENCE)
        words: list[str] = []
        fresh = 0
        chunk_heading = heading

        def emit(ws):
            out.append(ChunkOut(
                page_number=page.page_number, chunk_index=len(out),
                heading=chunk_heading, text=" ".join(ws), word_count=len(ws),
                token_estimate=round(len(ws) * TOKENS_PER_WORD), low_confidence=low,
            ))

        for raw in page.text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if is_heading(line):
                if fresh:
                    emit(words)
                words, fresh = [], 0
                heading = chunk_heading = line
                continue
            line_words = line.split()
            if fresh and len(words) + len(line_words) > TARGET_WORDS:
                emit(words)
                words, fresh = words[-OVERLAP_WORDS:], 0
                chunk_heading = heading
            words += line_words
            fresh += len(line_words)
            while len(words) > MAX_WORDS:
                emit(words[:MAX_WORDS])
                words = words[MAX_WORDS - OVERLAP_WORDS:]
                fresh = max(0, len(words) - OVERLAP_WORDS)
        if fresh:
            emit(words)

    return out