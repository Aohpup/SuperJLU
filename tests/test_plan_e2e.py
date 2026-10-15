"""端到端：真实跑 cli._cmd_plan 与 MCP plan_courses，只模拟网络，防止引用不存在的辅助函数。"""
import json

from jlu_toolkit import secure_store
import sys
import types

import pytest

from jlu_toolkit import cli, emap, jwxt, plan

PLAN = {"code": "0", "datas": {"cxscfakzkc": {"totalSize": 2, "rows": [
    {"KCH": "A1", "KCM": "高数", "XF": 5, "KZH": "G1", "KZM": "数学", "KCXZDM_DISPLAY": "必修", "JYXDXQ": "1"},
    {"KCH": "B2", "KCM": "物理", "XF": 3, "KZH": "G1", "KZM": "数学"}]}}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    data = tmp_path / "jlu-toolkit" / "data"
    data.mkdir(parents=True)
    (data / "grades.csv").write_text("课程,学分,成绩,学期\n高数,5,90,2025-2026-1\n", encoding="utf-8")
    (data / "schedule.csv").write_text("name,teacher,room,weekday,start,end,weeks\n", encoding="utf-8")
    (data / "completion.json").write_text(json.dumps({"groups": [{"code": "G1", "name": "数学", "earned": None}]}),
                                          encoding="utf-8")

    def post_raw(self, path, form, ref):
        if path.endswith("cxscfakzkc.do") and form.get("XH") and form.get("PYFADM"):
            return 200, json.dumps(PLAN), ""
        return 403, "", ""
    monkeypatch.setattr(jwxt.JwxtClient, "load_session", lambda self: True)
    monkeypatch.setattr(jwxt.JwxtClient, "save_session", lambda self: None)
    monkeypatch.setattr(jwxt.JwxtClient, "enter_emap_app", lambda self, *a: None)
    monkeypatch.setattr(jwxt.JwxtClient, "post_raw", post_raw)
    monkeypatch.setattr(plan, "_context", lambda c: {"XH": "S1", "PYFADM": "P1"})
    monkeypatch.setattr(emap, "discover", lambda c, a: {"modules_seen": [a.route], "do_paths": []})
    monkeypatch.setattr(emap, "module_meta", lambda c, a, m: {"modules": {}, "trace": []})
    return data


def test_cmd_plan_refresh_json_end_to_end(env, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["jlu-toolkit", "plan", "--refresh", "--json"])
    cli.main()
    out = capsys.readouterr().out.strip()
    assert out.isascii()
    j = json.loads(out)
    assert j["count"] == 2 and j["source"]["plan"]["action"].endswith("cxscfakzkc.do")
    st = {c["code"]: c["status"] for c in j["courses"]}
    assert st == {"A1": "已修", "B2": "未修"}
    comp = secure_store.load_json(env / "completion.json")
    assert comp["groups"][0]["earned"] == 5


def test_cmd_plan_probe_and_text(env, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["jlu-toolkit", "plan", "--probe", "-o", str(env / "p.json")])
    cli.main()
    cap = capsys.readouterr()
    assert cap.out.isascii() and cap.err.isascii()
    assert json.loads((env / "p.json").read_text(encoding="ascii"))["calls_with_rows"]
    monkeypatch.setattr(sys, "argv", ["jlu-toolkit", "plan", "--refresh"])
    cli.main()
    assert "高数" in capsys.readouterr().out


def test_mcp_plan_courses_tool(env, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["jlu-toolkit", "plan", "--refresh", "--json"])
    cli.main()
    capsys.readouterr()
    tools = {}

    class FakeMCP:
        def __init__(self, *_): pass
        def tool(self):
            def deco(f):
                tools[f.__name__] = f
                return f
            return deco
        def run(self): pass
    fm = types.ModuleType("mcp.server.fastmcp"); fm.FastMCP = FakeMCP
    monkeypatch.setitem(sys.modules, "mcp", types.ModuleType("mcp"))
    monkeypatch.setitem(sys.modules, "mcp.server", types.ModuleType("mcp.server"))
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fm)
    from jlu_toolkit import mcp_server
    mcp_server.main()
    r = tools["plan_courses"](status="未修")
    assert r["count"] == 1 and r["courses"][0]["code"] == "B2"
