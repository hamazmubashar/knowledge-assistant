from app.services.chunking import MAX_WORDS, PageInput, chunk_pages


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