from app.scripts.answer_scoring import contains, heading_prefix, is_fragment, normalize


def test_number_words_match_digits():
    assert contains("New employees complete a six-month probation period.", "6-month")
    assert contains("New employees complete a six-month probation period.", "6")
    assert contains("Up to 5 unused days may be carried over.", "five")


def test_numbers_match_whole_tokens_only():
    assert not contains("Birth parents receive 16 weeks of leave.", "6")
    assert contains("Birth parents receive 16 weeks of leave.", "16 weeks")


def test_units_and_punctuation_are_ignored():
    assert contains("The maximum speed is 8 km/h.", "8 km/h")
    assert contains("Carried days expire on 31 March.", "31 march")
    assert contains("A fee of 2.5% applies.", "2.5%")


def test_table_rows_are_fragments():
    assert is_fragment("ESCALATION MATRIX P1 outage | 15 minutes | On-call engineer")
    assert not is_fragment("A P1 outage must receive a first response within 15 minutes.")


def test_copied_headings_are_detected():
    assert heading_prefix("ANNUAL LEAVE Full-time staff receive 20 days.") == "ANNUAL LEAVE"
    assert heading_prefix("PROBATION New employees complete a 6-month probation.") == "PROBATION"
    assert heading_prefix("HR staff approve requests.") is None
    assert heading_prefix("Full-time staff receive 20 days.") is None
    assert normalize("Six-Month") == "6 month"



def test_headings_on_their_own_line_are_detected():
    # Chunks keep line breaks, so a copied heading often ends with a newline, not a space.
    assert heading_prefix("ANNUAL LEAVE\nFull-time staff receive 20 days.") == "ANNUAL LEAVE"
    assert heading_prefix("QUARTERLY STOCK COUNT\nFull stock counts happen quarterly.") == "QUARTERLY STOCK COUNT"
    assert heading_prefix("SHIPPING\nStandard delivery takes 3 to 5 working days.") == "SHIPPING"