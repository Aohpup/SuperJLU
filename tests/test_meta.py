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
    assert [i["key"] for i in g["items"]] == ["JQPJF", "PPJDCX"]  # GPA_FIELDS 顺序：JQPJF 在前
    assert g["items"][0]["key"] == "JQPJF" and g["items"][0]["value"] == "87"
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
    assert any(s.get("XH") == "20240001" or s.get("XH1") == "20240001" for _, s in fc.posts)
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
                    {"name": "cxzxfaxfjd", "url": "cjcx/cxzxfaxfjd.do",
                     "controls": [{"name": "XH1"}, {"name": "XH2"}, {"name": "PPJDCX"}]},
                    {"name": "xscjcx", "url": "cjcx/xscjcx.do",
                     "controls": [{"name": "XNXQDM"}]},
                ]}), path
            if path == "/jwapp/sys/cjcx/modules/cjcx/cxzxfaxfjd.do":
                return 200, json.dumps({"datas": {"cxzxfaxfjd": {"rows": [{"PPJDCX": "3.61", "JQPJF": "87"}]}}}), path
            if "/jwapp/sys/cjcx/cjcx/" in path:
                raise AssertionError(f"bad path {path}")
            return 404, "", path

    g = meta.fetch_official_gpa(FC())
    assert g["source"] == "official" and [i["key"] for i in g["items"]] == ["JQPJF", "PPJDCX"]
    assert g["endpoint"] == "/jwapp/sys/cjcx/modules/cjcx/cxzxfaxfjd.do"
    rep = meta.probe_gpa(FC(), log=lambda s: None)
    dumped = json.dumps(rep)
    assert "3.61" not in dumped and "87" not in dumped
    assert set(rep["hit"]["matched_labels"]) == {"PPJDCX", "JQPJF"}
    assert any(a["name"] == "cxzxfaxfjd" for a in rep["actions"])


def test_gpaish_hint():
    assert meta._gpaish("cxzxfaxfjd", "/x/cxzxfaxfjd.do", [])
    assert meta._gpaish("", "/x/xspjxfjd.do", ["XH"])
    assert not meta._gpaish("xscjcx", "/x/xscjcx.do", ["XNXQDM"])


def test_emap_abs_resolves_under_modules():
    from jlu_toolkit import emap
    app = emap.App("cjcx", "cjcx")
    assert app.abs("cjcx/cxxspjjdxx.do") == "/jwapp/sys/cjcx/modules/cjcx/cxxspjjdxx.do"
    assert app.abs("./modules/cjcx/cxxspjjdxx.do") == "/jwapp/sys/cjcx/modules/cjcx/cxxspjjdxx.do"
    assert app.abs("/jwapp/sys/cjcx/modules/cjcx/x.do") == "/jwapp/sys/cjcx/modules/cjcx/x.do"
    assert app.abs("cjcx/xxx.do") != "/jwapp/sys/cjcx/cjcx/xxx.do"


def test_parse_official_gpa_jlu_fields():
    g = meta.parse_official_gpa({"PJJD": 3.747, "JQPJF": 87.5, "SYBXKGPA": 3.8, "XH": "secret"})
    keys = [i["key"] for i in g["items"]]
    assert keys == ["PJJD", "JQPJF", "SYBXKGPA"]
    assert g["items"][0]["label"] == "平均绩点"
    assert "secret" not in json.dumps(g)


def test_fetch_uses_resolved_cxxspjjdxx():
    class FC:
        def enter_emap_app(self, app): pass
        def _request(self, url, data=None, headers=None, method=None, allow_redirects=True):
            if "index.do" in url:
                return 200, '<script src="../modules/cjcx/cjcx.js"></script>', url, b""
            if url.endswith("/modules/cjcx/cjcx.js"):
                return 200, 'getModel("modules/cjcx.do","cxxspjjdxx")', url, b""
            return 404, "", url, b""
        def post_raw(self, path, fields, ref):
            if path.endswith("grpyfacx.do"):
                return 200, json.dumps({"datas": {"grpyfacx": {"rows": [{"XH": "20240001"}]}}}), path
            if path.endswith("/cjcx.do"):
                return 200, json.dumps({"models": [
                    {"name": "cxxspjjdxx", "url": "cjcx/cxxspjjdxx.do",
                     "controls": [{"name": "XH"}, {"name": "XNXQDM"}, {"name": "PJJD"}, {"name": "JQPJF"}]},
                ]}), path
            if path == "/jwapp/sys/cjcx/modules/cjcx/cxxspjjdxx.do":
                if not fields.get("XH"):
                    return 200, json.dumps({"code": "0", "datas": {"cxxspjjdxx": {"rows": []}}}), path
                return 200, json.dumps({"datas": {"cxxspjjdxx": {"rows": [{"PJJD": "3.747", "JQPJF": "87.5", "SYBXKGPA": "3.8"}]}}}), path
            if "/jwapp/sys/cjcx/cjcx/" in path:
                raise AssertionError(f"bad resolved path: {path}")
            return 404, "", path

    g = meta.fetch_official_gpa(FC())
    assert g["source"] == "official" and g["endpoint"].endswith("cxxspjjdxx.do")
    assert [i["key"] for i in g["items"]] == ["PJJD", "JQPJF", "SYBXKGPA"]


def test_response_shape_and_extract_payload():
    obj = {"code": "0", "datas": {"cxxspjjdxx": {"rows": [], "totalSize": 0}}}
    s = meta.response_shape(obj)
    assert "$.datas" in s["paths"] and s["paths"]["$.datas.cxxspjjdxx.rows"] == "array[0]"
    assert meta.extract_gpa_payload(obj) is None

    obj2 = {"code": "0", "datas": {"cxxspjjdxx": {"PJJD": 3.7, "JQPJF": 88}}}
    assert meta.extract_gpa_payload(obj2)["PJJD"] == 3.7
    s2 = meta.response_shape(obj2)
    assert "PJJD" in s2["gpa_keys_seen"]
    dumped = json.dumps(s2)
    assert "3.7" not in dumped and "88" not in dumped

    obj3 = {"code": "0", "datas": [{"PJJD": "3.1", "XH": "secret"}]}
    assert meta.extract_gpa_payload(obj3)["PJJD"] == "3.1"
    assert "secret" not in json.dumps(meta.response_shape(obj3))

    obj4 = {"PJJD": 3.2, "SYBXKGPA": 3.5}
    assert meta.extract_gpa_payload(obj4)["PJJD"] == 3.2


def test_param_variants_include_xh_and_querysetting():
    vs = meta._param_variants("20240001", ["XH", "XNXQDM"], "2026-2027-1")
    names = [n for n, _, _ in vs]
    assert "POST:XH" in names and "POST:XH+XNXQDM" in names
    assert "POST:querySetting(XH)" in names and "POST:empty" in names
    # 不含学号值泄漏到 variant 名以外的结构——form 有值但测试侧不打印
    assert any(f.get("XH") == "20240001" for _, _, f in vs)


def test_call_gpa_tries_variants_until_nonempty_rows():
    calls = []
    class FC:
        def enter_emap_app(self, a): pass
        def current_semester(self): return "2026-2027-1"
        def _request(self, url, data=None, headers=None, method=None, allow_redirects=True):
            return 200, "{}", url, b""
        def post_raw(self, path, fields, ref):
            calls.append(dict(fields))
            # 前两次空 rows，第三次（带 XNXQDM）返回
            if fields.get("XNXQDM") == "2026-2027-1":
                return 200, json.dumps({"code": "0", "datas": {"cxxspjjdxx": {"rows": [
                    {"PJJD": "3.747", "JQPJF": "87.5"}]}}}), path
            return 200, json.dumps({"code": "0", "datas": {"cxxspjjdxx": {"rows": []}}}), path

    g = meta._call_gpa_action(FC(), "/jwapp/sys/cjcx/modules/cjcx/cxxspjjdxx.do",
                              ["XH", "XNXQDM"], "20240001", "2026-2027-1")
    assert g and g["source"] == "official" and g["items"][0]["key"] == "PJJD"
    assert g["variant"] == "POST:XH+XNXQDM"
    assert any("XNXQDM" in c for c in calls)


def test_rxylgpacx_primary_with_captions():
    class FC:
        def enter_emap_app(self, a): pass
        def current_semester(self): return "2026-2027-1"
        def _request(self, url, data=None, headers=None, method=None, allow_redirects=True):
            if "index.do" in url:
                return 200, "<html></html>", url, b""
            if "rxylgpacx.do" in url:
                return 200, json.dumps({"models": [{
                    "name": "rxylgpacxcx",
                    "url": "cjcx/rxylgpacx/rxylgpacxcx.do",
                    "controls": [
                        {"name": "PJJD", "caption": "平均绩点"},
                        {"name": "JQPJF", "caption": "加权平均分"},
                        {"name": "CUSTOMXF", "caption": "培养方案学分"},
                    ],
                }]}), url, b""
            return 404, "", url, b""
        def post_raw(self, path, fields, ref):
            if "grpyfacx" in path:
                return 200, json.dumps({"datas": {"grpyfacx": {"rows": [{"XH": "20240001"}]}}}), path
            if path == meta.EP_GPA_RXYL or "modules*cjcx/rxylgpacx/rxylgpacxcx.do" in path:
                assert fields == {"pageSize": "10", "pageNumber": "1"}
                assert "modules*cjcx" in path
                assert "cjcx" in ref and "EMAP_LANG" in ref
                return 200, json.dumps({"code": "0", "datas": {"rxylgpacxcx": {"rows": [
                    {"PJJD": "3.747", "JQPJF": "87.5", "XBDM": "1", "XBDM_DISPLAY": "男", "CUSTOMXF": "120"}]}}}), path
            return 404, "", path

    g = meta.fetch_official_gpa(FC())
    assert g["source"] == "official"
    assert g["endpoint"] == meta.EP_GPA_RXYL
    assert g["variant"] == "POST:pageSize+pageNumber"
    assert g["rows"] == 1
    labels = {i["key"]: i["label"] for i in g["items"]}
    vals = {i["key"]: i["value"] for i in g["items"]}
    assert labels["PJJD"] == "平均绩点" and labels.get("CUSTOMXF") == "培养方案学分"
    assert vals.get("XBDM") == "男"  # prefer DISPLAY
    assert "3.747" not in json.dumps(labels)


def test_star_path_constant():
    assert "modules*cjcx" in meta.EP_GPA_RXYL
    assert "modules/" not in meta.EP_GPA_RXYL.split("modules")[0] + "modules"


def test_emap_abs_nested_rxyl():
    from jlu_toolkit import emap
    app = emap.App("cjcx", "cjcx")
    assert app.abs("cjcx/rxylgpacx/rxylgpacxcx.do") == "/jwapp/sys/cjcx/modules/cjcx/rxylgpacx/rxylgpacxcx.do"
    assert app.abs("rxylgpacx/rxylgpacxcx.do") == "/jwapp/sys/cjcx/modules/rxylgpacx/rxylgpacxcx.do"


def test_reject_course_row_as_official_gpa():
    assert meta.extract_gpa_payload({"datas": {"cxxscj": {"rows": [
        {"KCM": "高数", "ZCJ": 92, "XFJD": 4.0, "JDF": 4.0}]}}}) is None
    assert meta.is_course_endpoint("/jwapp/sys/cjcx/modules/cjcx/cxxscj.do")
    assert meta._call_gpa_action(
        type("C", (), {"post_raw": staticmethod(lambda *a, **k: (200, "{}", "")),
                       "_request": staticmethod(lambda *a, **k: (200, "{}", "", b""))})(),
        "/jwapp/sys/cjcx/modules/cjcx/cxxscj.do", [], "20240001") is None


def test_sync_does_not_promote_cxxscj(tmp_path):
    routes = dict(ROUTES)
    # 所有绩点候选空，但 cxxscj 有单科行
    routes[meta.EP_GPA] = {"code": "404"}
    routes[meta.EP_GPA_JLU] = {"code": "0", "datas": {"cxxspjjdxx": {"rows": []}}}
    routes[meta.EP_GPA_RXYL] = {"code": "404"}
    routes[meta.EP_GPA_RXYL_ALT] = {"code": "403"}
    fc = FakeClient(routes)
    # FakeClient._request returns empty html; post_raw for cxxscj if called
    orig = fc.post_raw
    def post_raw(path, fields, ref):
        if "cxxscj" in path:
            return 200, json.dumps({"datas": {"cxxscj": {"rows": [{"KCM": "x", "ZCJ": 90, "XFJD": 4}]}}}), path
        return orig(path, fields, ref)
    fc.post_raw = post_raw
    s = sync.sync_all(fc, tmp_path)
    g = json.loads((tmp_path / "official_gpa.json").read_text(encoding="utf-8"))
    assert g.get("source") != "official" or "cxxscj" not in (g.get("endpoint") or "")
    # 应回退 jw_point 或 available false
    assert g.get("source") in ("grades_jw_point", None) or g.get("available") is False or g.get("source") == "grades_jw_point"


def test_zgcjgpa_row_accepted_and_xm_dropped():
    row = {"ZGCJGPA": "3.75", "CJDPM": "12", "XM": "张三", "WID": "w", "SFFB": "1",
           "XZNJ": "2024", "XZNJ_DISPLAY": "2024级", "YXDM": "01", "YXDM_DISPLAY": "计算机学院",
           "ZYDM": "x", "ZYDM_DISPLAY": "计科", "BJDM": "b", "BJDM_DISPLAY": "1班"}
    assert meta.is_summary_gpa_row(row)
    g = meta.parse_official_gpa(row)
    keys = [i["key"] for i in g["items"]]
    assert keys[:2] == ["ZGCJGPA", "CJDPM"]
    assert "XM" not in keys and "WID" not in keys
    vals = {i["key"]: i["value"] for i in g["items"]}
    assert vals["YXDM"] == "计算机学院" and vals["XZNJ"] == "2024级"
