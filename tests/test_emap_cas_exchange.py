"""进教务应用被送回统一认证时：没有 CASTGC 但有其它 CAS cookie（如 tpasssessionid）也要先试换票。"""
from http.cookiejar import Cookie

import pytest

from jlu_toolkit import jwxt


def _cookie(name, domain="cas.jlu.edu.cn", path="/tpass"):
    return Cookie(0, name, "v", None, False, domain, False, False, path, True, True, None, False, None, None, {})


def _client(monkeypatch, responses):
    c = jwxt.JwxtClient()
    calls = []

    def fake(url, *a, **k):
        calls.append(url)
        return responses[min(len(calls) - 1, len(responses) - 1)]
    monkeypatch.setattr(c, "_request", fake)
    monkeypatch.setattr(c, "save_session", lambda *a, **k: None)
    monkeypatch.setattr(jwxt, "mark_session_expired", lambda *a, **k: None)
    return c, calls


APP = "https://iedu.jlu.edu.cn/jwapp/sys/wdkb/*default/index.do"
ON_CAS = (200, '<form id="loginForm">', "https://cas.jlu.edu.cn/tpass/login?service=x", b"")
ON_IEDU = (200, "<html>ok</html>", APP, b"")


def test_exchange_with_tpasssessionid_only(monkeypatch):
    c, calls = _client(monkeypatch, [ON_CAS, ON_IEDU])
    c.jar.set_cookie(_cookie("tpasssessionid"))
    assert not c.has_cas_tgc() and c.has_cas_cookie()
    c.enter_emap_app(APP)
    assert "cas.jlu.edu.cn" in calls[1]


def test_no_cas_cookie_asks_relogin_in_app_words(monkeypatch):
    c, _ = _client(monkeypatch, [ON_CAS])
    monkeypatch.setattr("jlu_toolkit.sessions.load_cookies", lambda *_: [])
    monkeypatch.setattr("jlu_toolkit.sessions.migrate_cas_from_jwxt", lambda *_: 0)
    with pytest.raises(jwxt.LoginError) as e:
        c.enter_emap_app(APP)
    assert "更多 → 账号" in str(e.value)


def test_saved_cas_site_cookies_are_merged(monkeypatch):
    c, calls = _client(monkeypatch, [ON_CAS, ON_IEDU])
    monkeypatch.setattr("jlu_toolkit.sessions.migrate_cas_from_jwxt", lambda *_: 0)
    monkeypatch.setattr("jlu_toolkit.sessions.load_cookies",
                        lambda *_: jwxt.jar_to_list([_cookie("CASTGC")]))
    c.enter_emap_app(APP)
    assert c.has_cas_tgc() and "cas.jlu.edu.cn" in calls[1]
