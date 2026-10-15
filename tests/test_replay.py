"""离线回放：合成、去标识的接口响应（字段名与吉大教务一致，值虚构），覆盖已知接口优先的取数路径。"""
import json
from pathlib import Path

import pytest

from jlu_toolkit import emap, endpoints, jwxt, meta, plan, rooms

FIX = Path(__file__).parent / "fixtures" / "replay"
REPLAY = json.loads((FIX / "replay.json").read_text(encoding="utf-8"))
ROOM_ROWS = json.loads((FIX / "rooms_rows.json").read_text(encoding="utf-8"))
PRIVATE = ("TEST-XH", "TEST-FA", "TEST-WID", "TEST-NAME")


class ReplayClient:
    def __init__(self):
        self.calls = []

    def enter_emap_app(self, *_):
        pass

    def save_session(self):
        pass

    def _request(self, url, **kw):
        return 404, "", url, {}

    def post_raw(self, path, form, ref):
        self.calls.append((path, dict(form)))
        if path.endswith("/kxjscx/cxkxjs.do"):
            size, n = int(form.get("pageSize") or 200), int(form.get("pageNumber") or 1)
            rows = [r for r in ROOM_ROWS if r["XXXQDM"] == form.get("XXXQDM", "01")]
            return 200, json.dumps({"code": "0", "datas": {"cxkxjs": {
                "totalSize": len(rows), "rows": rows[(n - 1) * size:n * size]}}}, ensure_ascii=False), ""
        if path in REPLAY:
            if path.endswith("cxscfakzkc.do") and not (form.get("XH") and form.get("PYFADM")):
                return 200, json.dumps({"code": "0", "datas": {"cxscfakzkc": {"totalSize": 0, "rows": []}}}), ""
            if path.endswith("kzcx.do") and "TEST-FA" not in form.get("querySetting", ""):
                return 200, json.dumps({"code": "0", "datas": {"kzcx": {"totalSize": 0, "rows": []}}}), ""
            return 200, json.dumps(REPLAY[path], ensure_ascii=False), ""
        return 403, "", ""


@pytest.fixture
def data_dir():
    d = jwxt.config_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _no_private(obj):
    s = json.dumps(obj, ensure_ascii=False)
    assert not any(p in s for p in PRIVATE), "个人字段泄漏"


def test_known_registry_paths():
    assert endpoints.get("plan_courses").path == "/jwapp/sys/xywccx/modules/xywccx/cxscfakzkc.do"
    assert endpoints.get("plan_tree").path == "/jwapp/sys/xsfacx/modules/pyfacxepg/kzcx.do"
    assert endpoints.get("official_gpa").path.endswith("modules*cjcx/rxylgpacx/rxylgpacxcx.do")
    assert endpoints.get("rooms_query").path == "/jwapp/sys/kxjas/modules/kxjscx/cxkxjs.do"
    assert jwxt.EP_GRADES == endpoints.get("grades").path and meta.EP_COMPLETION == endpoints.get("completion").path
    assert endpoints.build_form(endpoints.get("plan_courses"), {}) is None  # 缺 XH/PYFADM → 回退
    assert endpoints.scrub({"XH": 1, "XM_DISPLAY": 2, "a": [{"WID": 3, "b": 4}]}) == {"a": [{"b": 4}]}


def test_plan_known_first_tree_assignment_and_earned(data_dir, monkeypatch):
    monkeypatch.setattr(plan, "explore", lambda *a, **k: pytest.fail("已知接口可用时不应走发现"))
    c = ReplayClient()
    p = plan.fetch_plan(c)
    assert p["source"]["plan"]["via"] == "known" and p["source"]["tree"]["via"] == "known"
    assert p["count"] == 6
    st = p["tree_stats"]
    assert st["groups"] == 5 and st["matched"] == 6 and st["unmatched"] == 0 and st["placed_in_tree"] == 6
    status = {x["code"]: x["status_code"] for x in p["courses"]}
    assert status == {"SZ001": "done", "SZ002": "done", "SZ003": "todo", "LD001": "inprog",
                      "ZY001": "done", "ZY002": "todo"}
    summ = {s["code"]: s for s in p["tree_summary"]}
    assert summ["G1"]["earned"] == 5.0 and summ["G1"]["required"] == 18
    assert summ["G0"]["earned"] == 5.0 and summ["G0"]["total_courses"] == 4  # 子组汇总
    assert summ["G2"]["earned"] == 0 and summ["G31"]["earned"] == 4.0 and summ["G3"]["earned"] == 4.0
    _no_private(p)
    # 课组号放进 completion 后，扁平课组也与树一致（WCXF=0 不当真）
    comp = plan.attach_to_completion({"groups": [{"code": "G1", "name": "思政类课程", "required": 18.0,
                                                  "earned": 0.0, "earned_source": "jw"}]}, p)
    assert comp["groups"][0]["earned"] == 5.0 and comp["tree_stats"]["matched"] == 6
    _no_private(comp)


def test_plan_guard_refuses_schoolwide_table():
    c = ReplayClient()
    with pytest.raises(emap.TooLarge):
        emap.fetch_paged(c, "/jwapp/sys/xsfacx/modules/pyfacxepg/kzkccx.do", {}, "ref")
    assert sum(1 for p, _ in c.calls if p.endswith("kzkccx.do")) == 1  # 只请求第一页即拒绝


def test_official_gpa_replay(data_dir):
    g = meta.fetch_rxyl_official_gpa(ReplayClient(), captions={})
    assert g and g["source"] == "official"
    keys = [i["key"] for i in g["items"]]
    assert keys[:2] == ["ZGCJGPA", "CJDPM"] and {"XZNJ", "YXDM", "ZYDM", "BJDM"} <= set(keys)
    vals = {i["key"]: i["value"] for i in g["items"]}
    assert vals["YXDM"] == "某学院" and vals["ZGCJGPA"] == "3.61"
    _no_private(g)
    assert (data_dir / "gpa_endpoint.txt").read_text(encoding="utf-8").endswith("rxylgpacxcx.do")


def test_rooms_replay_known_endpoint_cached_meta_and_paging(data_dir, monkeypatch):
    (data_dir / "rooms_meta.json").write_text((FIX / "rooms_meta.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(rooms, "full_meta", lambda *a, **k: pytest.fail("有缓存元数据时不应重新发现"))
    c = ReplayClient()
    q = rooms.RoomQuery("01", "2026-10-20", 1, 2, term="2026-2027-1", week=7, weekday=2, seat_min=100)
    found, prof = rooms.query_rooms(c, q, data_dir / "rooms_profile.json")
    assert prof["endpoint"] == endpoints.get("rooms_query").path and prof["total"] == 205
    assert len(found) == 135 and all(int(r.seats) >= 100 for r in found)  # 本地兜底筛选
    pages = sorted({f.get("pageNumber") for p, f in c.calls if p.endswith("cxkxjs.do")})
    assert pages == ["1", "2"]
    r0 = found[0]
    assert r0.kind == "多媒体" and r0.exam_seats and r0.free_time == "08:00-09:40"
    assert [s["name"] for s in rooms.extra_search_fields(rooms.cached_meta(c))] == ["SFKT"]
