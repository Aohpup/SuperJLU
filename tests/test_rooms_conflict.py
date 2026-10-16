from jlu_toolkit import rooms


def _q(**kw):
    base = dict(campus="1", date="2026-10-15", start=1, end=2, building="", term="t", week=7, weekday=4)
    base.update(kw)
    return rooms.RoomQuery(**base)


def test_date_mode_drops_week_and_weekday():
    fn = rooms._with_filters(rooms.SCHEMES["form_kxrq_ksjc"], [])
    d = fn(_q())
    assert d["KXRQ"] == "2026-10-15"
    assert not any(k in d for k in ("ZC", "XQ", "XQJ"))


def test_week_mode_drops_all_dates():
    fn = rooms._with_filters(rooms.SCHEMES["form_kxrq_ksjc"], [])
    d = fn(_q(mode="week", weeks="6,7", date="2026-10-15"))
    assert "KXRQ" not in d and d["ZC"] and d["XQ"] == "4"


def test_special_rooms():
    assert rooms.is_special_room(rooms.Room(name="A101", kind="实验室"))
    assert rooms.is_special_room(rooms.Room(name="计算机机房3"))
    assert not rooms.is_special_room(rooms.Room(name="逸夫楼201", kind="多媒体教室"))
