"""校历/节次/官方绩点/学业完成 + sync + explore v2（不访问教务）。"""
import json

import pytest

from jlu_toolkit import core, explore, jwxt, meta, sync, ui


def test_norm_time():
    assert meta.norm_time("0800") == "08:00"
    assert meta.norm_time("8:05") == "08:05"
    assert meta.norm_time("13:30:00") == "13:30"
    assert meta.norm_time(800) == "08:00"
    assert meta.norm_time("25:00") == "" and meta.norm_time(None) == ""


def test_parse_calendar_normalizes_to_monday():
    c = meta.parse_calendar({"XQKSRQ": "2026-09-09 00:00:00", "ZZC": 20.0, "ZJXZC": "18", "XN": "2026-2027", "XQ": 1})
    assert c == {"term": "2026-2027-1", "start_date": "2026-09-09", "first_monday": "2026-09-07",
                 "total_weeks": 20, "teaching_weeks": 18}


def test_parse_periods_multi_campus_and_disabled():
    rows = [
        {"DM": 1, "KSSJ": "0800", "JSSJ": "0845", "XXXQ": "A", "SFSY": 1},
        {"DM": 2, "KSSJ": "08:55", "JSSJ": "09:40", "XXXQ": "A", "SFSY": "1"},
        {"DM": 10, "KSSJ": "1925", "JSSJ": "2010", "XXXQ": "A"},
        {"DM": 1, "KSSJ": "0810", "JSSJ": "0855", "XXXQ": "B"},
        {"DM": 3, "KSSJ": "1000", "JSSJ": "1045", "XXXQ": "A", "SFSY": "0"},
    ]
    p = meta.parse_periods(rows)
    assert list(p) == ["1", "2", "10"]
    assert p["1"] == ["08:00", "08:45"]


def test_ics_uses_periods():
    c = core.Course("X", "t", "l", 1, 1, 2, [1])
    ics = core.to_ics([c], "2026-09-07", {"1": ["08:10", "08:55"], "2": ["09:05", "09:50"]})
    assert "T081000" in ics and "T095000" in ics
    c13 = core.Course("Y", "t", "l", 1, 12, 13, [1])
    assert "SUMMARY:Y" not in core.to_ics([c13], "2026-09-07")  # 未知节次跳过而不是崩溃
    assert "SUMMARY:Y" in core.to_ics([c13], "2026-09-07", {"12": ["20:20", "21:05"], "13": ["21:10", "21:55"]})


def test_parse_official_gpa():
    g = meta.parse_official_gpa({"PPJDCX": 3.6123, "JQPJF": 87.0, "PYFAMC": "计科", "XH": "secret"})
    assert g["plan"] == "计科"
    assert [i["key"] for i in g["items"]] == ["PPJDCX", "JQPJF"]
    assert g["items"][1]["value"] == "87"
    assert "secret" not in json.dumps(g)


def test_parse_completion_missing_and_sort():
    c = meta.parse_completion(
        {"YQXF": 165, "WCXF": 51.5, "XKXF": 70, "JSSFTG": "0", "PYFAMC": "计科"},
        {},
        [
            {"KZM": "通识必修", "YQXF": 21, "WCXF": 21, "SFTG": "1"},
            {"KZM": "专业必修", "YQXF": 62, "WCXF": 14.0, "WCMS": 4, "SFTG": "0"},
            {"KZM": "专业选修", "YQXF": 24, "WCXF": None, "SFTG": "0"},
        ],
    )
    assert c["missing"] == 113.5 and not c["passed"]
    assert [g["name"] for g in c["groups"]] == ["专业必修", "专业选修", "通识必修"]
    assert c["groups"][0]["missing"] == 48 and c["groups"][0]["courses_done"] == 4


def test_parse_completion_falls_back_to_plan():
    c = meta.parse_completion({}, {"ZSYQXF": "160", "YWCXF": "40", "PYFAMC": "P"}, [])
    assert c["required"] == 160 and c["earned"] == 40 and c["missing"] == 120 and c["plan"] == "P"


class FakeClient:
    """按路径返回固定 JSON 的假客户端。"""

    def __init__(self, routes):
        self.routes = routes
        self.posts = []
        self.saved = False

    def enter_emap_app(self, app):
        pass

    def current_semester(self):
        return "2026-2027-1"

    def _request(self, url, data=None, headers=None, method=None, allow_redirects=True):
        # 发现阶段：给空页面，避免依赖真实脚本
        return 200, "<html></html>", url, b""

    def post_raw(self, path, fields, ref):
        self.posts.append((path, dict(fields)))
        r = self.routes.get(path)
        if r is None:
            return 404, "", path
        return 200, json.dumps(r), path

    def fetch_schedule(self, term=None):
        return [core.Course("课", "t", "l", 1, 1, 2, [1])]

    def fetch_grades(self):
        return [core.Grade("课", 2.0, "90", "2025-2026-1")]

    def fetch_exams(self, term=None):
        raise jwxt.JwxtError("exams down")

    def save_session(self):
        self.saved = True


ROUTES = {
    meta.EP_CALENDAR: {"datas": {"cxxljc": {"rows": [{"XQKSRQ": "2026-09-07 00:00:00", "ZZC": 20}]}}},
    meta.EP_PERIODS: {"datas": {"jc": {"rows": [{"DM": 1, "KSSJ": "0800", "JSSJ": "0845"}]}}},
    meta.EP_PLAN: {"datas": {"grpyfacx": {"rows": [{"XH": "20240001", "PYFADM": "P1", "ZSYQXF": 165}]}}},
    meta.EP_GPA: {"datas": {"cxzxfaxfjd": {"rows": [{"PPJDCX": "3.61"}]}}},
    meta.EP_COMPLETION: {"datas": {"cxxsscfa": {"rows": [{"YQXF": 165, "WCXF": 51, "XH": "20240001", "PYFADM": "P1"}]}}},
    meta.EP_COMPLETION_GROUPS: {"datas": {"cxscfakz": {"rows": [{"KZM": "专业必修", "YQXF": 62, "WCXF": 14}]}}},
}


def test_fetch_gpa_sends_xh_fields():
    fc = FakeClient(ROUTES)
    g = meta.fetch_official_gpa(fc)
    sent = dict(fc.posts)[meta.EP_GPA]
    assert all(sent[f"XH{i}"] == "20240001" for i in range(1, 7))
    assert g["items"][0]["value"] == "3.61"


def test_sync_all_writes_files_and_summary_has_no_personal(tmp_path):
    fc = FakeClient(ROUTES)
    s = sync.sync_all(fc, tmp_path)
    assert s["schedule"]["ok"] and s["calendar"]["first_monday"] == "2026-09-07"
    assert s["exams"]["ok"] is False  # 单项失败不影响其他
    assert s["completion"]["groups"] == 1
    dumped = json.dumps(s, ensure_ascii=False)
    for secret in ("20240001", "3.61", "51"):
        assert secret not in dumped
    for f in ("schedule.csv", "grades.csv", "calendar.json", "periods.json", "official_gpa.json", "completion.json"):
        assert (tmp_path / f).exists(), f
    assert fc.saved
    snap = ui.Store(tmp_path).snapshot()
    assert snap["first_monday"] == "2026-09-07" and snap["first_monday_source"] == "calendar"
    assert snap["periods"]["1"] == ["08:00", "08:45"]
    assert snap["completion"]["missing"] == 114


def test_manual_override_and_clear(tmp_path):
    (tmp_path / "calendar.json").write_text('{"first_monday": "2026-09-07"}', encoding="utf-8")
    st = ui.Store(tmp_path)
    st.save_settings({"first_monday": "2026-09-14"})
    assert st.first_monday() == "2026-09-14"
    st.save_settings({"first_monday": ""})
    assert st.first_monday() == "2026-09-07"


def test_explore_ctx_never_reported():
    client = jwxt.JwxtClient()

    def fake_req(url, data=None, headers=None, method=None, allow_redirects=True):
        if url.endswith("index.do"):
            return 200, '<script src="public/js/app.js"></script>', url, b""
        if url.endswith("app.js"):
            return 200, 'ajax("/jwapp/sys/kxjscx/modules/kxjscx/cxkxjs.do");load("modules/kxjscx.do")', url, b""
        return 404, "", url, b""

    sent = []

    def fake_post(path, fields, referer):
        sent.append((path, fields))
        if path.endswith("grpyfacx.do"):
            return 200, json.dumps({"datas": {"grpyfacx": {"rows": [{"XH": "20249999", "PYFADM": "PF77", "XM": "王五"}]}}}), path
        return 200, json.dumps({"datas": {"x": {"rows": []}}}), path

    with pytest.MonkeyPatch.context() as m:
        m.setattr(client, "_request", fake_req)
        m.setattr(client, "post_raw", fake_post)
        rep = explore.run_explore(client, "2026-2027-1", log=lambda s: None)
    dumped = json.dumps(rep, ensure_ascii=False)
    for secret in ("20249999", "PF77", "王五"):
        assert secret not in dumped
    assert rep["context_found"] == ["PYFADM", "XH"]
    # 需要学号的探测确实用到了学号（只在请求体里）
    gpa = [f for p, f in sent if p.endswith("cxzxfaxfjd.do") and "XH1" in f]
    assert gpa and gpa[0]["XH6"] == "20249999"
    assert "/jwapp/sys/kxjscx/modules/kxjscx/cxkxjs.do" in rep["discover"]["kxjscx"]["do_paths"]


def test_explore_skips_when_ctx_missing():
    client = jwxt.JwxtClient()
    with pytest.MonkeyPatch.context() as m:
        m.setattr(client, "_request", lambda *a, **k: (200, "", a[0], b""))
        m.setattr(client, "post_raw", lambda p, f, r: (200, "{}", p))
        rep = explore.run_explore(client, "2026-2027-1", log=lambda s: None)
    skipped = [p for p in rep["probes"] if p.get("skipped")]
    assert {p["label"] for p in skipped} >= {"学分绩点统计(XH1..6)", "学业完成课组明细"}


def test_group_earned_none_means_missing_unknown():
    c = meta.parse_completion({"YQXF": 10, "WCXF": 4}, {}, [{"KZM": "A", "KZH": "A", "YQXF": 6, "WCXF": None}])
    assert c["groups"][0]["missing"] is None and c["groups"][0]["earned"] is None


def test_derive_group_earned_rollup():
    comp = meta.parse_completion({"YQXF": 20, "WCXF": 7}, {}, [
        {"KZM": "专业课", "KZH": "P", "YQXF": 12},
        {"KZM": "专业必修", "KZH": "P1", "FKZH": "P", "YQXF": 8},
        {"KZM": "专业选修", "KZH": "P2", "FKZH": "P", "YQXF": 4},
        {"KZM": "通识", "KZH": "G", "YQXF": 8},
    ])
    plan = [{"KZH": "P1", "KCM": "数据结构"}, {"KZH": "P1", "KCM": "操作系统"},
            {"KZH": "P2", "KCM": "机器学习"}, {"KZH": "G", "KCM": "体育"}, {"KZH": "G", "KCM": "军事理论"}]
    grades = [core.Grade("数据结构", 4, "90", "t"), core.Grade("操作系统", 4, "55", "t"),
              core.Grade("机器学习", 2, "良好", "t"), core.Grade("体育", 1, "通过", "t"),
              core.Grade("军事理论", 2, "不及格", "t")]
    out = meta.derive_group_earned(comp, plan, grades)
    by = {g["code"]: g for g in out["groups"]}
    assert by["P1"]["earned"] == 4 and by["P2"]["earned"] == 2 and by["P"]["earned"] == 6
    assert by["G"]["earned"] == 1 and by["G"]["missing"] == 7
    assert by["P"]["earned_source"] == "derived" and out["groups_derived"] == 4


def test_official_gpa_unavailable_then_jw_points(tmp_path):
    routes = dict(ROUTES)
    routes[meta.EP_GPA] = {"code": "404"}
    fc = FakeClient(routes)
    with pytest.raises(meta.Unavailable):
        meta.fetch_official_gpa(fc)
    gs = [core.Grade("a", 2, "90", "t", 4.0), core.Grade("b", 2, "70", "t", 2.0)]
    g = meta.fetch_official_gpa(fc, grades=gs)
    assert g["source"] == "grades_jw_point" and g["items"][0]["value"] == "3.000"


def test_sync_unavailable_gpa_is_not_failure(tmp_path):
    routes = dict(ROUTES)
    routes[meta.EP_GPA] = {"code": "404"}
    fc = FakeClient(routes)
    s = sync.sync_all(fc, tmp_path)
    assert s["official_gpa"]["ok"] and s["official_gpa"]["available"] is False
    assert json.loads((tmp_path / "official_gpa.json").read_text(encoding="utf-8"))["available"] is False


def test_grade_jw_point_roundtrip(tmp_path):
    g = jwxt.row_to_grade({"KCM": "x", "XF": 2.0, "ZCJ": 91.0, "XFJD": 4.1})
    assert g.jw_point == 4.1
    p = tmp_path / "g.csv"
    jwxt.export_grades_csv([g, core.Grade("y", 1, "通过", "t")], str(p))
    back = core.load_grades(str(p))
    assert back[0].jw_point == 4.1 and back[1].jw_point is None


def test_summarize_msg_redacts_numbers():
    s = explore.summarize_json({"code": "1", "msg": "学号20240001无权限访问"})
    assert "20240001" not in s["msg"] and "无权限" in s["msg"]


def test_emap_discover_cjcx_finds_gpa_action():
    from jlu_toolkit import emap

    class FC:
        def enter_emap_app(self, app): pass
        def _request(self, url, data=None, headers=None, method=None, allow_redirects=True):
            if "index.do" in url:
                return 200, '<script src="../modules/cjcx/cjcx.js"></script>', url, b""
            if url.endswith("/modules/cjcx/cjcx.js"):
                return 200, 'getModel("modules/cjcx.do","cxzxfaxfjd"); $.post("./modules/cjcx/cxzxfaxfjd.do")', url, b""
            return 404, "", url, b""
        def post_raw(self, path, fields, ref):
            if path.endswith("grpyfacx.do"):
                return 200, json.dumps({"datas": {"grpyfacx": {"rows": [{"XH": "20240001"}]}}}), path
            if path.endswith("/cjcx.do"):
                return 200, json.dumps({"models": [
                    {"name": "cxzxfaxfjd", "url": "/jwapp/sys/cjcx/modules/cjcx/cxzxfaxfjd.do",
                     "controls": [{"name": "XH1"}, {"name": "XH2"}, {"name": "PPJDCX"}]},
                    {"name": "xscjcx", "url": "/jwapp/sys/cjcx/modules/cjcx/xscjcx.do",
                     "controls": [{"name": "XNXQDM"}]},
                ]}), path
            if path.endswith("cxzxfaxfjd.do"):
                return 200, json.dumps({"datas": {"cxzxfaxfjd": {"rows": [{"PPJDCX": "3.61", "JQPJF": "87"}]}}}), path
            return 404, "", path

    g = meta.fetch_official_gpa(FC())
    assert g["source"] == "official" and [i["key"] for i in g["items"]] == ["PPJDCX", "JQPJF"]
    rep = meta.probe_gpa(FC(), log=lambda s: None)
    dumped = json.dumps(rep)
    assert "3.61" not in dumped and "87" not in dumped
    assert rep["hit"]["matched_labels"] == ["PPJDCX", "JQPJF"]
    assert any(a["name"] == "cxzxfaxfjd" for a in rep["actions"])


def test_gpaish_hint():
    assert meta._gpaish("cxzxfaxfjd", "/x/cxzxfaxfjd.do", [])
    assert meta._gpaish("", "/x/xspjxfjd.do", ["XH"])
    assert not meta._gpaish("xscjcx", "/x/xscjcx.do", ["XNXQDM"])
