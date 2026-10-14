from jlu_toolkit import core
def test_weeks(): assert core.parse_weeks("1-5单") == [1,3,5]
def test_point(): assert core.score_to_point("85") == 3.5 and core.score_to_point("59") == 0.0 and core.score_to_point("通过") is None
def test_gpa():
    r = core.gpa(core.load_grades("examples/grades.csv"))
    assert r["credits"] == 13
def test_ics():
    s = core.to_ics(core.load_courses("examples/schedule.csv"), "2026-09-07")
    assert s.count("BEGIN:VEVENT") == 16 + 8 + 8
