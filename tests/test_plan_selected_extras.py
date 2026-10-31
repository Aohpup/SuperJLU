"""培养方案课程表里没有、但自己选了的课（限选/通识课程池）不能在学业完成里消失。"""
from jlu_toolkit import plan as pl
from jlu_toolkit.core import Course
from jlu_toolkit.ui_page import PAGE


def _row(**kw):
    c = {k: "" for k in pl.COLS}
    c.update(kw)
    return c


def test_pool_courses_from_record_and_schedule_are_kept():
    plan = [_row(code="A1", name="高等数学", group="必修", group_code="G1", credit="5")]
    done = [_row(code="ZG9", name="仿生学的发展与应用", group="卓工限选", group_code="G7", credit="2")]
    now = [Course("西方戏剧鉴赏", "某老师", "某教室", 3, 9, 10, [1, 2], kch="YS3"),
           Course("高等数学", "", "", 1, 1, 2, [1])]
    out = pl.merge(plan, done, [], now)
    by = {c["name"]: c for c in out}
    assert by["仿生学的发展与应用"]["group_code"] == "G7" and by["仿生学的发展与应用"]["status"] == "在修"
    assert by["西方戏剧鉴赏"]["status"] == "在修" and by["西方戏剧鉴赏"]["code"] == "YS3"
    assert by["高等数学"]["status"] == "在修" and len(out) == 3  # 不重复


def test_schedule_extra_is_labelled_in_tree_unmatched():
    courses = pl.merge([_row(code="A1", name="高数", group_code="G1")], [], [],
                       [Course("西方戏剧鉴赏", "", "", 3, 9, 10, [1])])
    bt = pl.build_tree(pl.tree_nodes([{"KZH": "G1", "KZM": "必修"}]), courses)
    assert [c["unmatched_reason"] for c in bt["unmatched"]] == ["selected_now"]
    assert "本学期已选" in PAGE


def test_no_plan_keeps_old_behaviour():
    done = [_row(code="X", name="课", group_code="G")]
    assert [c["name"] for c in pl.merge([], done, [], [Course("别的", "", "", 1, 1, 1, [1])])] == ["课"]
