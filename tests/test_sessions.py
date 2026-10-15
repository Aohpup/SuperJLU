import json
import sys
import threading
import types
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from jlu_toolkit import jwxt, sessions, ui


@pytest.fixture(autouse=True)
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("JLU_TOOLKIT_NO_KEYRING", "1")
    monkeypatch.setenv("JLU_TOOLKIT_QUIET_STORE", "1")
    monkeypatch.setattr(sessions, "_checks", {})
    monkeypatch.setattr(sessions, "_vpn_impl", None)
    monkeypatch.delitem(sys.modules, "jlu_toolkit.campus", raising=False)
    return tmp_path / "jlu-toolkit"


def fake_campus(monkeypatch, **fns):
    m = types.ModuleType("jlu_toolkit.campus")
    for k, v in fns.items():
        setattr(m, k, v)
    monkeypatch.setitem(sys.modules, "jlu_toolkit.campus", m)
    return m


def by_id(res):
    return {s["id"]: s for s in res["sites"]}


def test_registry_ids_are_identifiers():
    assert list(sessions.SITES) == ["jwxt", "pay", "xsxk", "ilearn", "vpn", "lib"]
    assert all(i.isidentifier() for i in sessions.SITES)
    assert sessions.SITES["ilearn"].captcha and sessions.SITES["lib"].auth == "none"


def test_default_status_without_campus(monkeypatch):
    monkeypatch.setattr(sessions, "_campus", lambda: None)
    s = by_id(sessions.all_status())
    assert s["jwxt"]["state"] == "missing" and s["pay"]["needs_login"]
    assert s["lib"]["state"] == "ok" and not s["lib"]["needs_login"]
    assert not any(v["has_check"] for v in s.values())
    assert set(s["pay"]) >= {"id", "name", "state", "checked_at", "needs_login", "message"}


def test_save_load_clear_encrypted_file(cfg):
    sessions.save_cookies("pay", [{"name": "JSESSIONID", "value": "abc", "domain": "ip.jlu.edu.cn"}])
    assert (cfg / "session-pay.json").exists() or (cfg / "session-pay.enc").exists()
    assert sessions.load_cookies("pay")[0]["value"] == "abc"
    assert sessions.status("pay")["state"] == "ok"
    st = (cfg / "sessions_status.json").read_text(encoding="utf-8")
    assert "abc" not in st  # 状态文件不含秘密
    sessions.mark_expired("pay", "重定向到 CAS")
    s = sessions.status("pay")
    assert s["state"] == "expired" and s["needs_login"] and "CAS" in s["message"]
    sessions.clear("pay")
    assert sessions.status("pay")["state"] == "missing" and sessions.load_cookies("pay") is None
    with pytest.raises(ValueError):
        sessions.save_cookies("jwxt", [])
    with pytest.raises(ValueError):
        sessions.status("nope")


def test_jwxt_maps_existing_session():
    c = jwxt.JwxtClient()
    c.save_session()
    assert sessions.status("jwxt")["state"] == "ok"
    sessions.mark_expired("jwxt", "x")
    assert jwxt.session_status()["state"] == "expired"


def test_campus_hooks_discovered(monkeypatch):
    seen = []

    def check_pay(sess):
        seen.append(sess)
        return {"logged_in": False, "reason": "跳到登录页"}
    fake_campus(monkeypatch, check_pay=check_pay, check_xsxk=lambda s: {"logged_in": None, "reason": "?"})
    sessions.save_cookies("pay", [])
    sessions.save_cookies("xsxk", [])
    assert sessions.status("pay")["has_check"]
    r = sessions.check("pay")
    assert r["state"] == "expired" and hasattr(seen[0], "_request")
    assert sessions.check("xsxk")["state"] == "unknown"
    assert sessions.check("ilearn")["state"] == "missing"  # 无钩子 → 不变


def test_hook_errors_become_unknown(monkeypatch):
    def boom(s):
        raise jwxt.NetworkError("down")
    sessions.register_check("pay", boom)
    sessions.save_cookies("pay", [])
    r = sessions.check("pay")
    assert r["state"] == "unknown" and "网络" in r["message"]


def test_vpn_url_pluggable(monkeypatch):
    monkeypatch.setattr(sessions, "_campus", lambda: None)
    with pytest.raises(NotImplementedError):
        sessions.vpn_url("https://iedu.jlu.edu.cn/")
    fake_campus(monkeypatch, vpn_url=lambda u: "VPN:" + u)
    monkeypatch.setattr(sessions, "_campus", lambda: sys.modules.get("jlu_toolkit.campus"))
    assert sessions.vpn_url("u") == "VPN:u"
    sessions.register_vpn_url(lambda u: "R:" + u)
    assert sessions.vpn_url("u") == "R:u"


def test_http(cfg, monkeypatch):
    store = ui.Store(cfg / "data")
    store.root.mkdir(parents=True)
    monkeypatch.setattr(ui, "refresh_from_jwxt", lambda s: (_ for _ in ()).throw(sessions.SiteSessionExpired("xsxk")))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(store))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/sessions") as r:
            d = json.loads(r.read())
        assert d["ok"] and [s["id"] for s in d["sites"]][0] == "jwxt"
        req = urllib.request.Request(base + "/api/refresh", data=b"{}", headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(req)
        body = json.loads(ei.value.read())
        assert ei.value.code == 401 and body["session_expired"] is True and body["site"] == "xsxk"
    finally:
        srv.shutdown()


def test_cli(capsys):
    from jlu_toolkit import cli
    cli.main(["sessions", "--json"])
    assert len(json.loads(capsys.readouterr().out)["sites"]) == 6
    sessions.save_cookies("lib", [])
    cli.main(["sessions", "clear", "lib"])
    assert "已清除" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["sessions", "clear"])
