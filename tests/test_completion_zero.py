
"""教务课组 WCXF=0 时，应按已修课程重算，并挂上课程明细。"""
from jlu_toolkit import plan, meta, core


def test_attach_overrides_wcxf_zero():
    comp = meta.parse_completion(
        {"YQXF": 20, "WCXF": 0}, {},
        [{"KZM": "通识", "KZH": "G", "YQXF": 8, "WCXF": 0, "SFTG": "0"},
         {"KZM": "专业", "KZH": "P", "YQXF": 12, "WCXF": 0, "SFTG": "0"}],
    )
    assert all(g["earned"] == 0 for g in comp["groups"])
    p = {
        "courses": [
            {"code": "1", "name": "A", "credit": 2, "status": "已修", "status_code": "done", "group_code": "G", "group": "通识"},
            {"code": "2", "name": "B", "credit": 3, "status": "已修", "status_code": "done", "group_code": "P", "group": "专业"},
            {"code": "3", "name": "C", "credit": 2, "status": "未修", "status_code": "todo", "group_code": "P", "group": "专业"},
        ],
        "tree_nodes": [],
    }
    out = plan.attach_to_completion(comp, p)
    by = {g["code"]: g for g in out["groups"]}
    assert by["G"]["earned"] == 2 and by["P"]["earned"] == 3
    assert by["G"]["courses"] and by["P"]["courses"]
    assert by["G"]["earned_source"] == "plan_courses"


def test_derive_overrides_wcxf_zero():
    comp = meta.parse_completion({"YQXF": 10, "WCXF": 0}, {}, [
        {"KZM": "通识", "KZH": "G", "YQXF": 8, "WCXF": 0},
    ])
    plan_rows = [{"KZH": "G", "KCM": "体育"}]
    grades = [core.Grade("体育", 1, "通过", "t")]
    out = meta.derive_group_earned(comp, plan_rows, grades)
    assert out["groups"][0]["earned"] == 1 and out["groups_derived"] == 1
