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
    if "|" in s:
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


def _count(lines: list[str]) -> int:
    return sum(len(line.split()) for line in lines)


def _overlap(lines: list[str]) -> list[str]:
    kept, n = [], 0
    for line in reversed(lines):
        n += len(line.split())
        if n > OVERLAP_WORDS:
            break
        kept.insert(0, line)
    return kept


def chunk_pages(pages: list[PageInput]) -> list[ChunkOut]:
    out: list[ChunkOut] = []
    heading: str | None = None
    heading_open = False

    for page in pages:
        low = page.is_ocr and (page.ocr_confidence is None
                               or page.ocr_confidence < LOW_OCR_CONFIDENCE)
        lines: list[str] = []
        fresh = 0
        chunk_heading = heading

        def emit(ls):
            wc = _count(ls)
            out.append(ChunkOut(
                page_number=page.page_number, chunk_index=len(out), heading=chunk_heading,
                text="\n".join(ls), word_count=wc,
                token_estimate=round(wc * TOKENS_PER_WORD), low_confidence=low))

        for raw in page.text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if is_heading(line):
                if fresh:
                    emit(lines)
                lines, fresh = [], 0
                heading = f"{heading} > {line}" if heading_open and heading else line
                chunk_heading = heading
                heading_open = True
                continue
            heading_open = False
            words = line.split()
            if len(words) > MAX_WORDS:
                if fresh:
                    emit(lines)
                for i in range(0, len(words), MAX_WORDS - OVERLAP_WORDS):
                    emit([" ".join(words[i:i + MAX_WORDS])])
                lines, fresh = [], 0
                continue
            if fresh and _count(lines) + len(words) > TARGET_WORDS:
                emit(lines)
                lines, fresh = _overlap(lines), 0
                chunk_heading = heading
            if not fresh and _count(lines) + len(words) > MAX_WORDS:
                lines = []
            lines.append(line)
            fresh += len(words)
        if fresh:
            emit(lines)

    return out

class ContentLoss(RuntimeError):
    """Chunking lost page content: the version must not be published."""


def _norm_ws(s: str) -> str:
    return " ".join(s.split())


def missing_lines(pages: list[PageInput], chunks: list[ChunkOut]) -> list[str]:
    stored = _norm_ws(" ".join(f"{c.heading or ''} {c.text}" for c in chunks))
    stored_words = set(stored.split())
    lost = []
    for page in pages:
        for raw in page.text.splitlines():
            line = _norm_ws(raw)
            if not line:
                continue
            words = line.split()
            if len(words) > MAX_WORDS:
                if not set(words) <= stored_words:
                    lost.append(line)
            elif line not in stored:
                lost.append(line)
    return lost