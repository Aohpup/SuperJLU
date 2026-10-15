import json

from jlu_toolkit import ui, ui_check


def test_ui_check_counts_offline(tmp_path, monkeypatch, capsys):
    d = tmp_path / "data"
    d.mkdir()
    tree = [{"code": "G0", "earned": 5, "courses": [], "children": [
        {"code": "G1", "earned": 5, "courses": [{"code": "a"}, {"code": "b"}], "children": []},
        {"code": "G2", "earned": 0, "courses": [{"code": "c"}], "children": []}]}]
    (d / "completion.json").write_text(json.dumps({"groups": [], "tree": tree, "unmatched": []}), encoding="utf-8")
    (d / "plan_courses.json").write_text(json.dumps({"source": {"plan": {"via": "known"}, "tree": {"via": "known"}},
        "courses": [{"code": "a", "status_code": "done"}, {"code": "b", "status_code": "todo"},
                    {"code": "c", "status_code": "done"}]}), encoding="utf-8")
    monkeypatch.setattr(ui, "data_dir", lambda: d)
    monkeypatch.setattr(ui, "campuses_api", lambda s: {"campuses": [{"code": "01", "name": "x"}, {"code": "02", "name": "y"}]})
    monkeypatch.setattr(ui, "buildings_api", lambda s, b: {"buildings": [{"code": "B", "name": "z"}]})
    monkeypatch.setattr(ui, "rooms_api", lambda s, b: {"rooms": [{"name": "r"}] * 7, "total": 9}
                        if b["seat_min"] == 100 else {"rooms": []})
    assert ui_check.main([]) == 0
    out = capsys.readouterr().out.strip()
    assert out.isascii()
    r = json.loads(out)
    assert r["page"]["has_script"] and r["data"]["tree_nodes"] == 3 and r["data"]["tree_courses_placed"] == 3
    assert r["data"]["tree_nodes_earned_gt0"] == 2 and r["data"]["plan_done"] == 2 and r["data"]["plan_via"] == "known"
    assert r["rooms"] == {"campuses_status": 200, "campuses": 2, "buildings_first_campus": 1,
                          "query_status": 200, "rooms": 7, "total": 9, "ok": True}
