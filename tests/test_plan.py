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
