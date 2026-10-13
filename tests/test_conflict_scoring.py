from app.scripts.run_answer_eval import conflict_scores

Q = {"conflict_titles": ["EVAL General Remote Work Policy", "EVAL General Office Attendance Memo"],
     "must_contain": ["2 days", "3 days"]}


def answer(text, titles, flagged):
    return {"answer": text, "conflict": flagged}, [{"document_title": t} for t in titles]


def test_flag_alone_does_not_pass():
    r, cites = answer("Employees may work from home up to 2 days per week.",
                      ["EVAL General Remote Work Policy"], flagged=True)
    s = conflict_scores(Q, r, cites)
    assert s["conflict_flagged"] and not s["both_sources_cited"] and not s["details_correct"]


def test_both_sources_and_both_values_pass():
    r, cites = answer("The policy allows 2 days per week. The memo allows 3 days per week.",
                      Q["conflict_titles"], flagged=False)
    s = conflict_scores(Q, r, cites)
    assert s["both_sources_cited"] and s["details_correct"]


def test_both_sources_with_a_wrong_value_fails_details():
    r, cites = answer("The policy allows 2 days per week. The memo allows 4 days per week.",
                      Q["conflict_titles"], flagged=True)
    s = conflict_scores(Q, r, cites)
    assert s["both_sources_cited"] and not s["details_correct"]
