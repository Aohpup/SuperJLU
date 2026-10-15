import json

from jlu_toolkit import plan, emap
from jlu_toolkit.core import Grade


def test_normalize_by_keys_and_captions():
    rows = [{"KCH": "A1", "KCM": "高数", "XF": 5.0, "XS": 80, "KCXZDM_DISPLAY": "必修", "JYXDXQ": "1",
             "KKDWDM_DISPLAY": "数学学院", "KZM": "数学", "KZH": "G1"},
            {"KCH": "B2", "KCM": "体育", "XF": "1", "ZZXQ": "2", "KZH": "G2"}]
    cs = plan.normalize(rows, {"ZZXQ": "建议修读学期"})
    assert cs[0]["credit"] == 5.0 and cs[0]["hours"] == "80" and cs[0]["dept"] == "数学学院"
    assert cs[1]["term"] == "2"


def test_merge_status():
    p = plan.normalize([{"KCH": "A1", "KCM": "高数", "XF": 5}, {"KCH": "B2", "KCM": "物理", "XF": 3},
                        {"KCH": "C3", "KCM": "化学", "XF": 2}, {"KCH": "D4", "KCM": "英语", "XF": 2}], {})
    d = plan.normalize([{"KCH": "D4", "KCM": "英语", "SFTG": "是"}], {})
    class C:  # 当前课表
        name = "物理"
    out = {c["code"]: c["status"] for c in plan.merge(p, d, [Grade("高数", 5, "90", "t")], [C()])}
    assert out == {"A1": "已修", "B2": "在修", "C3": "未修", "D4": "已修"}


def test_attach_prefers_server_earned():
    comp = {"groups": [{"code": "G1", "name": "数学", "earned": 4.0}, {"code": "G2", "name": "体育", "earned": None}]}
    p = {"courses": [{"group_code": "G1", "credit": 5, "status": "已修"},
                     {"group_code": "G2", "credit": 1, "status": "已修"}]}
    c = plan.attach_to_completion(comp, p)
    assert c["groups"][0]["earned"] == 4.0 and c["groups"][1]["earned"] == 1
    assert c["groups"][1]["earned_source"] == "plan_courses"


def test_explore_report_has_no_values(monkeypatch):
    rows = [{"KCH": "SECRET1", "KCM": "SECRETNAME", "XF": 9}]

    class FC:
        def enter_emap_app(self, *_): pass
        def post_raw(self, path, form, ref):
            assert "XH" not in form or form.get("XH")
            if path.endswith("kzkccx.do"):
                return 200, json.dumps({"code": "0", "datas": {"kzkccx": {"rows": rows, "totalSize": 1}}}), ""
            return 403, "", ""
    monkeypatch.setattr(plan, "_context", lambda c: {"XH": "S123456"})
    monkeypatch.setattr(emap, "discover", lambda c, a: {"modules_seen": [a.route], "do_paths": []})
    monkeypatch.setattr(emap, "module_meta", lambda c, a, m: {"modules": {}, "trace": []})
    rep, best = plan.explore(FC())
    s = json.dumps(rep, ensure_ascii=False)
    assert "SECRET" not in s and "S123456" not in s
    assert best["plan"]["app"] in ("xsfacx", "jwpubapp")


def test_rejects_unfiltered_and_prefers_student_plan(monkeypatch):
    big = {"code": "0", "datas": {"kzkccx": {"rows": [{"KCH": "x", "KCM": "y"}], "totalSize": 239471}}}
    mine = {"code": "0", "datas": {"cxscfakzkc": {"rows": [{"KCH": "x", "KCM": "y", "XF": 2}], "totalSize": 254}}}
    seen = []

    class FC:
        def enter_emap_app(self, *_): pass
        def post_raw(self, path, form, ref):
            seen.append((path.rsplit("/", 1)[-1], sorted(form)))
            if path.endswith("kzkccx.do"):
                return 200, json.dumps(big), ""
            if path.endswith("cxscfakzkc.do") and "XH" in form and "PYFADM" in form:
                return 200, json.dumps(mine), ""
            return 403, "", ""
    monkeypatch.setattr(plan, "_context", lambda c: {"XH": "S1", "PYFADM": "P1"})
    monkeypatch.setattr(emap, "discover", lambda c, a: {"modules_seen": [a.route], "do_paths": []})
    monkeypatch.setattr(emap, "module_meta", lambda c, a, m: {"modules": {}, "trace": []})
    rep, best = plan.explore(FC())
    assert best["plan"]["path"].endswith("cxscfakzkc.do") and best["plan"]["total"] == 254
    assert not any(n == "kzkccx.do" and f == ["pageNumber", "pageSize"] for n, f in seen)
    assert any(c.get("rejected") for c in rep["calls_with_rows"])
    import pytest
    from jlu_toolkit import jwxt
    with pytest.raises(jwxt.JwxtError):
        plan.fetch_all(FC(), {"app": "xsfacx", "route": "xsfacx", "path": "/jwapp/sys/xsfacx/modules/pyfacxepg/kzkccx.do",
                              "form": {"PYFADM": "P1"}})


def test_cxscfakzkc_fields():
    rows = [{"KCH": "A1", "KCM": "高数", "XF": 5, "XNXQDM": "2024-2025-1", "XNXQDM_DISPLAY": "2024-2025学年第一学期",
             "KSLXDM_DISPLAY": "考试", "ZSCJ": "88", "XH": "S1", "PYFADM": "P1", "WID": "w", "SFXK": "0"},
            {"KCH": "B2", "KCM": "物理", "XF": 3, "SFXK": "1"},
            {"KCH": "C3", "KCM": "化学", "XF": 2, "SFXK": "0"}]
    cs = {c["code"]: c for c in plan.merge(plan.normalize(rows, {}), [], [], [])}
    a = cs["A1"]
    assert a["term"] == "2024-2025学年第一学期" and a["exam_type"] == "考试" and a["score"] == "88"
    assert a["status"] == "已修" and cs["B2"]["status"] == "在修" and cs["C3"]["status"] == "未修"
    s = json.dumps(list(cs.values()), ensure_ascii=False)
    assert "S1" not in s and "P1" not in s and '"w"' not in s


def test_build_tree_nested_and_unmatched():
    nodes = plan.tree_nodes([{"KZH": "R", "KZM": "总"}, {"KZH": "A", "KZM": "数学", "FKZH": "R", "YQXF": 8},
                             {"KZH": "B", "KZM": "体育", "FKZH": "R", "YQXF": 4}])
    cs = [{"code": "1", "name": "高数", "credit": 5, "status": "已修", "group_code": "A"},
          {"code": "2", "name": "体育", "credit": 1, "status": "未修", "group_code": "B"},
          {"code": "3", "name": "x", "credit": 2, "status": "已修", "group_code": "Z"},
          {"code": "4", "name": "y", "credit": 2, "status": "已修", "group_code": "Z", "sub_rd": "9"}]
    t = plan.build_tree(nodes, cs, [{"code": "B", "earned": 2.0}])
    assert len(t["roots"]) == 1 and [c["code"] for c in t["roots"][0]["children"]] == ["A", "B"]
    a, b = t["roots"][0]["children"]
    assert a["earned"] == 5 and a["missing"] == 3 and b["earned"] == 2.0 and b["earned_source"] == "jw"
    want = {"groups": 3, "roots": 1, "courses": 4, "matched": 2, "unmatched": 2,
            "unmatched_kzh": 1, "reasons": {"kzh_not_in_tree": 1, "substitute": 1}, "placed_in_tree": 2}
    assert {k: t["stats"][k] for k in want} == want


def _shape(nodes, courses):
    t = plan.build_tree(plan.tree_nodes(nodes), courses)
    return t, {s["code"]: s for s in plan.tree_summary(t["roots"])}


def test_single_course_group_and_mixed():
    nodes = [{"KZH": "R", "KZM": "根"}, {"KZH": "S", "KZM": "单课组", "FKZH": "R"},
             {"KZH": "E", "KZM": "空父", "FKZH": "R"}, {"KZH": "E1", "KZM": "子1", "FKZH": "E"},
             {"KZH": "E2", "KZM": "子2", "FKZH": "E"}, {"KZH": "M", "KZM": "混合", "FKZH": "R"},
             {"KZH": "M1", "KZM": "混合子", "FKZH": "M"}]
    c = lambda code, g: {"code": code, "name": code, "credit": 1, "status": "已修", "group_code": g}  # noqa: E731
    cs = [c("k1", "S"), c("k2", "E1"), c("k3", "E2"), c("k4", "E2"), c("k5", "M"), c("k6", "M1")]
    t, s = _shape(nodes, cs)
    assert s["S"]["direct_courses"] == 1 and s["S"]["course_codes"] == ["k1"]
    assert s["E"]["direct_courses"] == 0 and s["E"]["total_courses"] == 3
    assert s["M"]["direct_courses"] == 1 and s["M"]["total_courses"] == 2
    assert t["stats"]["placed_in_tree"] == 6 == t["stats"]["matched"]


def test_cycle_nodes_are_promoted_not_lost():
    nodes = [{"KZH": "A", "KZM": "a", "FKZH": "B"}, {"KZH": "B", "KZM": "b", "FKZH": "A"}]
    t, s = _shape(nodes, [{"code": "k", "name": "k", "credit": 1, "status": "已修", "group_code": "A"}])
    assert t["stats"]["placed_in_tree"] == 1 and t["stats"]["promoted_cycle_nodes"] >= 1


def test_tree_js_renders_single_and_nested(tmp_path):
    import re, shutil, subprocess
    from pathlib import Path
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node not available")
    from jlu_toolkit.ui_page import PAGE
    js = re.search(r"<script>(.*)</script>", PAGE, re.S).group(1)
    (tmp_path / "p.js").write_text(js, encoding="utf-8")
    test = (Path(__file__).parent / "js_tree_test.js").read_text(encoding="utf-8")
    (tmp_path / "t.js").write_text(test, encoding="utf-8")
    out = subprocess.run([node, str(tmp_path / "t.js"), str(tmp_path / "p.js")], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout.strip().splitlines()[-1])
    assert r == {"ok": True, "soloOpen": True, "rows1": 1, "rows3": 3}
    css = re.search(r"<style>(.*)</style>", PAGE, re.S).group(1)
    # 全局 th 是 sticky(top:58px)：课组表必须取消，否则表头盖住第一行
    assert re.search(r"\.rt th\{[^}]*position:static", css)


def test_earned_prefers_completion_then_courses_over_zero_tree():
    nodes = plan.tree_nodes([{"KZH": "R", "KZM": "思政", "YQXF": 18, "WCXF": 0},
                             {"KZH": "C", "KZM": "子", "FKZH": "R", "YQXF": 4, "WCXF": "0"},
                             {"KZH": "J", "KZM": "有服务器值", "YQXF": 2}])
    c = lambda code, g, cr, st: {"code": code, "name": code, "credit": cr, "status": st, "group_code": g}  # noqa: E731
    cs = [c("a", "R", 3, "已修"), c("b", "R", 2, "未修"), c("d", "C", 1.5, "已修"), c("e", "J", 2, "已修")]
    t = plan.build_tree(nodes, cs, [{"code": "J", "earned": 1.0}])
    by = {n["code"]: n for n in t["roots"]}
    assert by["R"]["earned"] == 4.5 and by["R"]["earned_source"] == "plan_courses" and by["R"]["missing"] == 13.5
    assert by["R"]["children"][0]["earned"] == 1.5
    assert by["J"]["earned"] == 1.0 and by["J"]["earned_source"] == "jw"
