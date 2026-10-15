"""campus.py：vpn_url 编解码 + check_* 钩子（不联网）。"""
from __future__ import annotations

import json
import sys
import types

import pytest

from jlu_toolkit import campus, sessions


class FakeSession:
    def __init__(self, pages):
        """pages: list of (code, text, final) or callable(url)->tuple"""
        self.pages = pages
        self.urls = []

    def _request(self, url, data=None, headers=None, method=None, allow_redirects=True):
        self.urls.append(url)
        if callable(self.pages):
            code, text, final = self.pages(url)
        else:
            code, text, final = self.pages[len(self.urls) - 1]
        return code, text, final, (text or "").encode()


def test_vpn_url_roundtrip_oa():
    raw = "https://oa.jlu.edu.cn/defaultroot/PortalInformation!jldxList.action?channelId=179577"
    v = campus.vpn_url(raw)
    assert v.startswith("https://vpn.jlu.edu.cn/https/")
    assert "44696469646131313237446964696461a579b2620fdde512c84ea96fd9" in v
    assert campus.vpn_url_decode(v).startswith("https://oa.jlu.edu.cn/defaultroot/")
    assert "channelId=179577" in campus.vpn_url_decode(v)


def test_vpn_url_hosts_and_passthrough():
    assert "icourses.jlu.edu.cn" in campus.vpn_url_decode(
        campus.vpn_url("https://icourses.jlu.edu.cn/xsxk/profile/index.html")
    )
    same = "https://vpn.jlu.edu.cn/portal/"
    assert campus.vpn_url(same) == same
    with pytest.raises(ValueError):
        campus.vpn_url("/relative")


def test_vpn_url_legacy_keys_decode():
    # Reachee 旧前缀（jluvpnisthegood!）
    old = (
        "https://vpn.jlu.edu.cn/https/"
        "6a6c7576706e6973746865676f6f64215ebd458ea69e85a6228e6380fc/"
        "defaultroot/"
    )
    assert campus.vpn_url_decode(old) == "https://oa.jlu.edu.cn/defaultroot/"


def test_check_pay_expired_raises():
    html = '<script>alert("页面超时，请先登录");location.href="/pay/";</script>'
    s = FakeSession([(200, html, "https://ip.jlu.edu.cn/pay/?menu=home")])
    with pytest.raises(sessions.SiteSessionExpired) as ei:
        campus.check_pay(s)
    assert ei.value.site == "pay"


def test_check_pay_ok():
    html = "<html><body><div>welcome menu home</div></body></html>"
    s = FakeSession([(200, html, "https://ip.jlu.edu.cn/pay/?menu=home")])
    r = campus.check_pay(s)
    assert r["logged_in"] is True


def test_check_xsxk_json_ok_and_401():
    ok = FakeSession([(200, json.dumps({"code": 200, "data": {"t": 1}}), campus.XSXK_NOW)])
    assert campus.check_xsxk(ok)["logged_in"] is True
    bad = FakeSession([(200, json.dumps({"code": 401, "msg": "x"}), campus.XSXK_NOW)])
    with pytest.raises(sessions.SiteSessionExpired):
        campus.check_xsxk(bad)


def test_check_xsxk_html_expired():
    s = FakeSession([(200, "<title>错误提示</title>", campus.XSXK_NOW)])
    with pytest.raises(sessions.SiteSessionExpired):
        campus.check_xsxk(s)


def test_check_ilearn_cas_redirect():
    final = "https://ilearn.jlu.edu.cn/cas-server/login?service=https://ilearntec.jlu.edu.cn/coursecenter/main/index"
    s = FakeSession([(200, "<title>Loading...</title>", final)])
    with pytest.raises(sessions.SiteSessionExpired) as ei:
        campus.check_ilearn(s)
    assert ei.value.site == "ilearn"


def test_check_ilearn_ok():
    s = FakeSession([(200, "<html>ok</html>", "https://ilearntec.jlu.edu.cn/coursecenter/main/index")])
    assert campus.check_ilearn(s)["logged_in"] is True


def test_check_lib_isLogin():
    s = FakeSession([(200, "var isLogin = true;", "https://lib.jlu.edu.cn/")])
    assert campus.check_lib(s)["logged_in"] is True
    s2 = FakeSession([(200, "var isLogin = false;", "https://lib.jlu.edu.cn/")])
    assert campus.check_lib(s2)["logged_in"] is None


def test_check_vpn_login_page():
    html = "<html>师生普通登录 统一身份认证 <input type='password' name='p'></html>"
    s = FakeSession([(200, html, "https://vpn.jlu.edu.cn/")])
    with pytest.raises(sessions.SiteSessionExpired):
        campus.check_vpn(s)


def test_check_jwxt_uses_ref(monkeypatch):
    s = FakeSession(
        [(200, "<html>kb</html>", "https://iedu.jlu.edu.cn/jwapp/sys/wdkb/*default/index.do")]
    )
    assert campus.check_jwxt(s)["logged_in"] is True
    cas = FakeSession(
        [(200, '<form id="loginForm"><input type="password"></form>', "https://cas.jlu.edu.cn/tpass/login")]
    )
    with pytest.raises(sessions.SiteSessionExpired):
        campus.check_jwxt(cas)


def test_sessions_discovers_campus_hooks(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("JLU_TOOLKIT_NO_KEYRING", "1")
    monkeypatch.setenv("JLU_TOOLKIT_QUIET_STORE", "1")
    monkeypatch.setattr(sessions, "_checks", {})
    monkeypatch.setattr(sessions, "_vpn_impl", None)
    # ensure real campus module is importable
    monkeypatch.delitem(sys.modules, "jlu_toolkit.campus", raising=False)
    assert sessions.find_check("pay").__name__ == "check_pay"
    assert sessions.vpn_url("https://oa.jlu.edu.cn/").startswith("https://vpn.jlu.edu.cn/https/")


def test_sessions_check_handles_site_expired(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("JLU_TOOLKIT_NO_KEYRING", "1")
    monkeypatch.setenv("JLU_TOOLKIT_QUIET_STORE", "1")
    monkeypatch.setattr(sessions, "_checks", {})
    sessions.save_cookies("pay", [{"name": "PHPSESSID", "value": "x", "domain": "ip.jlu.edu.cn"}])

    def boom(sess):
        sessions.mark_expired("pay", "x")
        raise sessions.SiteSessionExpired("pay")

    sessions.register_check("pay", boom)
    r = sessions.check("pay")
    assert r["state"] == "expired"


def test_probe_offline_structure(monkeypatch):
    pages = {
        "https://iedu.jlu.edu.cn/": (200, "<html></html>", "https://cas.jlu.edu.cn/tpass/login?service=x"),
        "https://ip.jlu.edu.cn/pay/": (
            200,
            '<title>pay</title><form><input name="card"><input name="pwd"><input name="imgcode">'
            '<img src="img_safecode.php"></form>',
            "https://ip.jlu.edu.cn/pay/",
        ),
        "https://icourses.jlu.edu.cn/xsxk/profile/index.html": (
            200,
            "<title>选课</title><script src='/xsxk/profile/js/index.min.js'></script>",
            "https://icourses.jlu.edu.cn/xsxk/profile/index.html",
        ),
        "https://icourses.jlu.edu.cn/xsxk/profile/js/index.min.js": (
            200,
            'axios.post("/auth/login"); axios.get("/web/now"); "/elective/user"',
            "https://icourses.jlu.edu.cn/xsxk/profile/js/index.min.js",
        ),
        "https://ilearntec.jlu.edu.cn/": (200, "<title>学在吉大</title>", "https://ilearntec.jlu.edu.cn/"),
        campus.ILEARN_MAIN: (
            200,
            "cas.jlu.edu.cn/tpass/login",
            "https://ilearn.jlu.edu.cn/cas-server/login?service=x",
        ),
        "https://vpn.jlu.edu.cn/": (200, "统一身份认证 师生普通登录", "https://vpn.jlu.edu.cn/"),
        "https://lib.jlu.edu.cn/": (200, "var isLogin = false;", "https://lib.jlu.edu.cn/"),
        "https://lib.jlu.edu.cn/login": (
            200,
            'var logoutUrl = "https://cas.jlu.edu.cn/tpass/login?service=https://lib.jlu.edu.cn/sso/login/3rd/30569";',
            "https://lib.jlu.edu.cn/login",
        ),
    }

    def handler(url):
        for k, v in pages.items():
            if url.startswith(k.rstrip("/")) or url == k:
                return v
        return (404, "missing", url)

    fake = FakeSession(handler)
    rep = campus.probe(fake)
    assert rep["ok"] and len(rep["sites"]) == 6
    by = {s["id"]: s for s in rep["sites"]}
    assert by["pay"]["login_type"] == "own+captcha" and by["pay"]["cas_reusable"] == "no"
    assert by["xsxk"]["login_type"] == "own+captcha"
    assert by["lib"]["cas_reusable"] == "yes"
    assert "vpn.jlu.edu.cn/https/" in (by["pay"].get("vpn_url_sample") or "")
    table = campus.probe_table(rep)
    assert "pay" in table and "ilearn" in table
