from jlu_toolkit import rooms


def _r():
    return rooms.Room(name="A101", building="B", campus="C", seats="", kind="", exam_seats="",
                      free_date="2026-10-01", free_periods="", free_time="")


def test_date_mode_label_matches_query():
    q = rooms.RoomQuery(campus="01", date="2026-10-18", start=1, end=2)
    out = rooms.label_free_date([_r()], q, "2026-09-07")
    assert out[0].free_date == "2026-10-18 周日（第6周）"


def test_week_mode_label_uses_chinese_weekday():
    q = rooms.RoomQuery(campus="01", date="", start=1, end=2, mode="week", weeks="6", weekday=3)
    assert rooms.label_free_date([_r()], q)[0].free_date == "第6周 周三"
