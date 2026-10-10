from app.services.chunking import MAX_WORDS, PageInput, chunk_pages
from app.services.chunking import ChunkOut, missing_lines


def test_completeness_check_passes_when_nothing_is_lost():
    pages = [PageInput(1, "SALARY BANDS 2026\nA | 2,500 - 3,500\nB | 3,500 - 4,500")]
    assert missing_lines(pages, chunk_pages(pages)) == []


def test_completeness_check_detects_a_dropped_line():
    pages = [PageInput(1, "SALARY BANDS 2026\nA | 2,500 - 3,500\nB | 3,500 - 4,500")]
    broken = [ChunkOut(1, 0, "SALARY BANDS 2026", "A | 2,500 - 3,500", 4, 5, False)]
    assert missing_lines(pages, broken) == ["B | 3,500 - 4,500"]


def test_completeness_check_handles_very_long_lines():
    long_line = " ".join(f"word{i}" for i in range(400))
    pages = [PageInput(1, long_line)]
    assert missing_lines(pages, chunk_pages(pages)) == []


def test_chunks_never_cross_pages():
    pages = [PageInput(1, "Alpha text here"), PageInput(2, "Beta text here")]
    chunks = chunk_pages(pages)
    assert [c.page_number for c in chunks] == [1, 2]
    assert "Beta" not in chunks[0].text


def test_long_page_is_split_within_limits():
    line = " ".join(["word"] * 20)
    chunks = chunk_pages([PageInput(1, "\n".join([line] * 40))])
    assert len(chunks) > 1
    assert all(c.word_count <= MAX_WORDS for c in chunks)
    assert all(c.page_number == 1 for c in chunks)


def test_heading_carries_across_pages():
    pages = [PageInput(1, "LEAVE POLICY\nEmployees receive 20 days of annual leave."),
             PageInput(2, "Unused days carry over up to 5 days.")]
    chunks = chunk_pages(pages)
    assert [c.heading for c in chunks] == ["LEAVE POLICY", "LEAVE POLICY"]


def test_new_heading_starts_new_chunk():
    text = "1. Scope\nThis applies to all staff.\n2. Leave\nStaff receive 20 days."
    chunks = chunk_pages([PageInput(1, text)])
    assert [c.heading for c in chunks] == ["1. Scope", "2. Leave"]


def test_indexes_are_sequential():
    line = " ".join(["word"] * 20)
    pages = [PageInput(n, "\n".join([line] * 30)) for n in (1, 2, 3)]
    chunks = chunk_pages(pages)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_empty_page_gives_no_chunks():
    assert chunk_pages([PageInput(1, "   \n  ")]) == []


def test_same_input_same_output():
    pages = [PageInput(1, "HR POLICY\nStaff receive 20 days.\nCarry-over is 5 days.")]
    assert chunk_pages(pages) == chunk_pages(pages)


def test_ocr_pages_without_confidence_are_flagged():
    chunks = chunk_pages([PageInput(1, "Scanned text here.", is_ocr=True),
                          PageInput(2, "Typed text here.")])
    assert [c.low_confidence for c in chunks] == [True, False]

def test_table_rows_are_content_not_headings():
    text = "SALARY BANDS 2026\nBand | Monthly range | Review month\nA | 2,500 - 3,500 | April\nB | 3,500 - 4,500 | April"
    chunks = chunk_pages([PageInput(1, text)])
    assert len(chunks) == 1
    assert chunks[0].heading == "SALARY BANDS 2026"
    assert "\nB | 3,500 - 4,500 | April" in chunks[0].text


def test_consecutive_headings_are_joined_not_lost():
    text = "ANNUAL LEAVE POLICY\n1. Entitlement\nStaff receive 20 days of leave."
    chunks = chunk_pages([PageInput(1, text)])
    assert chunks[0].heading == "ANNUAL LEAVE POLICY > 1. Entitlement"


def test_no_line_is_ever_lost():
    pages = [PageInput(1, "SALARY BANDS 2026\nBand | Range\nA | 2,500\nB | 3,500\nC | 4,000"),
             PageInput(2, "1. Scope\nApplies to all staff.\n2. Leave\n3. Notes\nSee HR portal.")]
    chunks = chunk_pages(pages)
    stored = " ".join(f"{c.heading or ''} {c.text}" for c in chunks)
    for page in pages:
        for line in page.text.splitlines():
            assert line.strip() in stored, f"lost: {line}"



def test_completeness_check_passes_when_nothing_is_lost():
    pages = [PageInput(1, "SALARY BANDS 2026\nA | 2,500 - 3,500\nB | 3,500 - 4,500")]
    assert missing_lines(pages, chunk_pages(pages)) == []


def test_completeness_check_detects_a_dropped_line():
    pages = [PageInput(1, "SALARY BANDS 2026\nA | 2,500 - 3,500\nB | 3,500 - 4,500")]
    broken = [ChunkOut(1, 0, "SALARY BANDS 2026", "A | 2,500 - 3,500", 4, 5, False)]
    assert missing_lines(pages, broken) == ["B | 3,500 - 4,500"]


def test_completeness_check_handles_very_long_lines():
    long_line = " ".join(f"word{i}" for i in range(400))
    pages = [PageInput(1, long_line)]
    assert missing_lines(pages, chunk_pages(pages)) == []