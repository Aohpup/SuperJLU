import json
import threading
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer

import pytest

from jlu_toolkit import jwxt, secure_store, sessions, ui

CAS_LOGIN_PAGE = '<form id="loginForm" action="/tpass/login"><input type="password" name="p"></form>'


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("JLU_TOOLKIT_NO_KEYRING", "1")
    monkeypatch.setenv("JLU_TOOLKIT_QUIET_STORE", "1")
    return tmp_path / "jlu-toolkit"


def jar(*cookies):
    return jwxt.jar_from_list([{"name": n, "value": v, "domain": d, "path": "/"} for n, v, d in cookies])


def route(monkeypatch, fn):
    calls = []

    def _request(self, url, data=None, headers=None, allow_redirects=True, **k):
        calls.append(url)
        return fn(self, url)
    monkeypatch.setattr(jwxt.JwxtClient, "_request", _request)
    return calls


def test_remember_me_fields():
    html = ('<input type="checkbox" name="rememberMe" value="true"><input name="warn" value="true">'
            '<input type="hidden" name="lt" value="x">')
    assert jwxt.remember_me_fields(html) == [("rememberMe", "true")]
    assert jwxt.remember_me_fields('<input name="remember-me">') == [("remember-me", "true")]
    assert jwxt.remember_me_fields(CAS_LOGIN_PAGE) == []


def test_save_session_persists_all_cas_cookies():
    c = jwxt.JwxtClient()
    c.jar = jar(("CASTGC", "tgt", "cas.jlu.edu.cn"), ("Language", "zh", "cas.jlu.edu.cn"),
                ("JSESSIONID", "s", "iedu.jlu.edu.cn"))
    c._rebuild_opener()
    c.save_session()
    names = sorted(d["name"] for d in sessions.load_cookies("cas"))
    assert names == ["CASTGC", "Language"]
    assert sessions.status("cas")["state"] == "ok"


def _saved_cas():
    sessions.save_cookies("cas", jwxt.jar_to_list(jar(("CASTGC", "tgt", "cas.jlu.edu.cn"))))


def test_refresh_via_cas_success(monkeypatch):
    _saved_cas()
    seen = {}

    def fn(self, url):
        seen["cas_cookie"] = any(ck.name == "CASTGC" for ck in self.jar)
        return 200, "<html>portal</html>", "https://iedu.jlu.edu.cn/jwapp/", b""
    calls = route(monkeypatch, fn)
    assert sessions.refresh_via_cas("jwxt") is True
    assert calls[0].startswith(jwxt.CAS_LOGIN + "?service=") and seen["cas_cookie"]
    assert jwxt.session_status()["state"] == "ok"


def test_refresh_via_cas_lands_on_login(monkeypatch):
    _saved_cas()
    route(monkeypatch, lambda s, u: (200, CAS_LOGIN_PAGE, "https://cas.jlu.edu.cn/tpass/login", b""))
    assert sessions.refresh_via_cas("jwxt") is False
    assert sessions.status("cas")["state"] == "expired"


def test_refresh_only_for_cas_sites(monkeypatch):
    _saved_cas()
    calls = route(monkeypatch, lambda s, u: (200, "", u, b""))
    for sid in ("pay", "xsxk", "ilearn", "vpn", "lib", "cas"):  # 非 CAS 或尚无 service
        assert sessions.refresh_via_cas(sid) is False
    assert calls == []
    sessions.clear("cas")
    assert sessions.refresh_via_cas("jwxt") is False


def test_session_alive_tries_cas_once(monkeypatch):
    _saved_cas()
    state = {"refreshed": False}

    def fn(self, url):
        if url.startswith(jwxt.CAS_LOGIN):
            state["refreshed"] = True
            return 200, "ok", "https://iedu.jlu.edu.cn/", b""
        if state["refreshed"]:
            return 200, "<html>kb</html>", url, b""
        return 200, CAS_LOGIN_PAGE, "https://cas.jlu.edu.cn/tpass/login", b""
    route(monkeypatch, fn)
    c = jwxt.JwxtClient()
    assert c.session_alive() is True and c._cas_refreshed


def test_post_form_expired_without_cas_raises(monkeypatch):
    calls = route(monkeypatch, lambda s, u: (200, CAS_LOGIN_PAGE, "https://cas.jlu.edu.cn/tpass/login", b""))
    with pytest.raises(jwxt.SessionExpiredError):
        jwxt.JwxtClient()._post_form("/x.do", {}, "r")
    assert not any(u.startswith(jwxt.CAS_LOGIN) for u in calls)


def test_keepalive(monkeypatch):
    assert sessions.keepalive()["alive"] is False
    c = jwxt.JwxtClient()
    c.save_session()
    route(monkeypatch, lambda s, u: (200, "<html>kb</html>", u, b""))
    r = sessions.keepalive()
    assert r["alive"] and not r["refreshed_via_cas"] and r["session"]["state"] == "ok"
    route(monkeypatch, lambda s, u: (200, CAS_LOGIN_PAGE, "https://cas.jlu.edu.cn/tpass/login", b""))
    r = sessions.keepalive()
    assert not r["alive"] and r["session"]["session_expired"]


def test_cache_json_encrypted_and_migrates(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    keyring = pytest.importorskip("keyring")
    from tests.test_secure_store import MemKeyring
    monkeypatch.delenv("JLU_TOOLKIT_NO_KEYRING")
    old = keyring.get_keyring()
    keyring.set_keyring(MemKeyring())
    try:
        d = tmp_path / "data"
        d.mkdir()
        (d / "plan_courses.json").write_text(json.dumps({"count": 1, "secret": "3.61"}), encoding="utf-8")
        assert secure_store.load_json(d / "plan_courses.json") == {"count": 1, "secret": "3.61"}
        assert not (d / "plan_courses.json").exists() and b"3.61" not in (d / "plan_courses.enc").read_bytes()
        secure_store.save_json(d / "official_gpa.json", {"gpa": 3.9})
        assert secure_store.json_exists(d / "official_gpa.json")
        assert ui.Store(d)._json("official_gpa.json", None) == {"gpa": 3.9}
        assert "official_gpa.json" in secure_store.cache_meta(d)
        assert secure_store.load_json(d / "nope.json", 7) == 7
    finally:
        keyring.set_keyring(old)


def test_http_offline_and_keepalive(env, monkeypatch):
    d = env / "data"
    d.mkdir(parents=True)
    store = ui.Store(d)
    secure_store.save_json(d / "completion.json", {"groups": []})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(store))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/session") as r:
            s = json.loads(r.read())
        assert s["offline"] is True and s["cached_at"] and s["state"] == "missing"
        with urllib.request.urlopen(base + "/api/data") as r:
            assert json.loads(r.read())["offline"] is True
        jwxt.JwxtClient().save_session()
        route(monkeypatch, lambda s_, u: (200, CAS_LOGIN_PAGE, "https://cas.jlu.edu.cn/tpass/login", b""))
        req = urllib.request.Request(base + "/api/session/keepalive", data=b"{}",
                                     headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(req)
        b = json.loads(ei.value.read())
        assert ei.value.code == 401 and b["session_expired"] and b["site"] == "jwxt"
        route(monkeypatch, lambda s_, u: (200, "<html>kb</html>", u, b""))
        jwxt.JwxtClient().save_session()
        with urllib.request.urlopen(req) as r:
            k = json.loads(r.read())
        assert k["alive"] and k["offline"] is False
    finally:
        srv.shutdown()
