import json

import pytest

from jlu_toolkit import jwxt, rooms


def test_parse_periods_arg():
    assert rooms.parse_periods_arg("3") == (3, 3)
    assert rooms.parse_periods_arg("3-4") == (3, 4)
    with pytest.raises(ValueError):
        rooms.parse_periods_arg("4-3")


def test_week_and_weekday():
    assert rooms.week_and_weekday("2026-10-15", "2026-09-07") == (6, 4)
    assert rooms.week_and_weekday("2026-10-15", None) == (0, 4)


META = {"models": [{"name": "cxkxjs", "url": "/jwapp/sys/kxjas/modules/kxjscx/cxkxjs.do",
                    "controls": [{"name": "XXXQDM", "url": "/jwapp/code/abc-xq.do"},
                                 {"name": "KXRQ"}, {"name": "KSJC"}, {"name": "JSJC"},
                                 {"name": "JXLDM", "url": "/jwapp/code/abc-jxl.do"}, {"name": "XNXQDM"}]}]}


def test_parse_meta():
    m = rooms.parse_meta(META)
    assert m["actions"] == ["/jwapp/sys/kxjas/modules/kxjscx/cxkxjs.do"]
    assert {"XXXQDM", "KXRQ", "KSJC", "JSJC"} <= set(m["fields"])
    assert m["dicts"]["XXXQDM"].endswith("abc-xq.do")


class FC:
    def __init__(self, ok_when):
        self.ok_when = ok_when
        self.calls = []

    def enter_emap_app(self, app):
        self.entered = app

    def _request(self, url, data=None, headers=None, method=None, allow_redirects=True):
        if "*default/index.do" in url:
            return 200, '<script src="../modules/kxjscx/kxjscx.js"></script>', url, b""
        if url.endswith("/jwapp/sys/kxjas/modules/kxjscx/kxjscx.js"):
            return 200, 'WIS_EMAP_SERV.getModel("modules/kxjscx.do","cxkxjs");$.post("./modules/kxjscx/cxkxjs.do")', url, b""
        return 404, "", url, b""

    def post_raw(self, path, fields, ref):
        self.calls.append((path, dict(fields)))
        if path.endswith("/kxjscx.do") and not fields:
            return 200, json.dumps(META), path
        if path.endswith(".do") and path.count("/") == 5 and not fields:
            return 404, "", path
        if path.endswith("abc-xq.do"):
            return 200, json.dumps({"datas": {"code": {"rows": [{"id": "01", "name": "前卫南区"}]}}}), path
        if self.ok_when(path, fields):
            return 200, json.dumps({"code": "0", "datas": {"cxkxjs": {"rows": [
                {"JASMC": "逸夫楼A101", "JXLDM_DISPLAY": "逸夫楼", "SKZWS": 120.0}]}}}), path
        return 200, json.dumps({"code": "1", "msg": "请选择校区"}), path


def test_query_uses_meta_scheme_and_saves_profile(tmp_path):
    fc = FC(lambda p, f: f.get("XXXQDM") == "01" and f.get("KXRQ") == "2026-10-15" and f.get("KSJC") == "1")
    q = rooms.RoomQuery("01", "2026-10-15", 1, 2, term="2026-2027-1", week=6, weekday=4)
    prof_path = tmp_path / "p.json"
    found, prof = rooms.query_rooms(fc, q, prof_path)
    assert found[0].name == "逸夫楼A101" and found[0].seats == "120"
    assert prof["scheme"] == "meta" and prof_path.exists()
    # 第二次直接用 profile，第一枪就中
    fc.calls.clear()
    rooms.query_rooms(fc, q, prof_path, meta=rooms.parse_meta(META))
    assert len(fc.calls) == 1


def test_query_failure_reports_codes(tmp_path):
    fc = FC(lambda p, f: False)
    with pytest.raises(jwxt.JwxtError, match="请选择校区"):
        rooms.query_rooms(fc, rooms.RoomQuery("01", "2026-10-15", 1, 2), None, max_tries=5)


def test_list_campuses_from_dict():
    assert rooms.list_campuses(FC(lambda p, f: False)) == [{"code": "01", "name": "前卫南区"}]


def test_probe_has_no_data_values():
    fc = FC(lambda p, f: f.get("XXXQDM") == "01" and "KXRQ" in f)
    rep = rooms.probe(fc, "2026-09-07", "2026-2027-1", None, "2026-10-15", (1, 2), log=lambda s: None)
    dumped = json.dumps(rep, ensure_ascii=False)
    assert rep["hit"] and rep["hit"]["rows"] == 1
    for v in ("逸夫楼A101", "前卫南区", "2026-10-15"):
        assert v not in dumped


def test_discover_finds_view_script_and_module():
    d = rooms.discover(FC(lambda p, f: False))
    assert "/jwapp/sys/kxjas/modules/kxjscx/kxjscx.js" in [f["path"] for f in d["fetched"]]
    assert "modules/kxjscx.do" in d["do_paths"] and "kxjscx" in d["modules_seen"]


def test_app_is_kxjas():
    assert rooms.APP.endswith("/jwapp/sys/kxjas/*default/index.do")
    assert rooms._abs("./modules/kxjscx/cxkxjs.do") == "/jwapp/sys/kxjas/modules/kxjscx/cxkxjs.do"
    assert rooms._abs("modules/kxjscx.do?*json=1") == "/jwapp/sys/kxjas/modules/kxjscx.do"
