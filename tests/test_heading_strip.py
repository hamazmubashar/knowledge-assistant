from app.services.answering import strip_copied_headings

TEXT = "Full-time staff receive 20 days of paid annual leave each year."


def run(text, quote, heading, chunk_text=TEXT):
    evidence = {"SOURCE_1": {"heading": heading, "text": chunk_text}}
    out, n = strip_copied_headings([{"text": text, "quote": quote, "evidence_id": "SOURCE_1",
                                     "reattributed": False}], evidence)
    return out[0]["text"], out[0]["quote"], n


def test_heading_on_its_own_line_is_removed_from_text_and_quote():
    text, quote, n = run("ANNUAL LEAVE\n" + TEXT, "ANNUAL LEAVE\n" + TEXT, "ANNUAL LEAVE")
    assert (text, quote, n) == (TEXT, TEXT, 1)


def test_capitalised_heading_on_the_same_line_is_removed():
    text, _, n = run("ANNUAL LEAVE " + TEXT, TEXT, "ANNUAL LEAVE")
    assert (text, n) == (TEXT, 1)


def test_last_part_of_a_joined_heading_is_removed():
    text, _, _ = run("PARENTAL LEAVE Birth parents receive 16 weeks of paid parental leave.",
                     TEXT, "HR POLICIES > PARENTAL LEAVE")
    assert text == "Birth parents receive 16 weeks of paid parental leave."


def test_normal_sentence_starting_with_heading_word_is_kept():
    text, _, n = run("Probation lasts 6 months for all new staff.", TEXT, "Probation")
    assert (text, n) == ("Probation lasts 6 months for all new staff.", 0)


def test_heading_only_sentence_is_left_for_drop_heading_only():
    text, _, n = run("ANNUAL LEAVE", TEXT, "ANNUAL LEAVE")
    assert (text, n) == ("ANNUAL LEAVE", 0)


def test_no_heading_means_no_change():
    text, quote, n = run(TEXT, TEXT, None)
    assert (text, quote, n) == (TEXT, TEXT, 0)


def test_colon_after_heading_is_removed_and_first_letter_capitalised():
    text, _, _ = run("Annual leave: full-time staff receive 20 days each year.", TEXT, "Annual leave")
    assert text == "Full-time staff receive 20 days each year."


def test_heading_kept_inside_chunk_text_is_removed():
    text, _, n = run("SHIPPING\nStandard delivery takes 3 to 5 working days.", TEXT, None,
                     chunk_text="SHIPPING\nStandard delivery takes 3 to 5 working days.")
    assert (text, n) == ("Standard delivery takes 3 to 5 working days.", 1)