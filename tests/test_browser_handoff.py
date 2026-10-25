"""Browser handoff must not consume tickets or export application credentials."""
import http.client
import json
import threading
import urllib.parse
from http.server import ThreadingHTTPServer

import pytest

from jlu_toolkit import campus, jwxt, sessions, sso, ui

CK = [{"name": "CASTGC", "value": "TGT-synthetic", "domain": "cas.jlu.edu.cn", "path": "/"}]


@pytest.fixture
def cas(monkeypatch):
    seen = []
    monkeypatch.setattr(sessions, "migrate_cas_from_jwxt", lambda: 0)
    monkeypatch.setattr(sessions, "load_cookies", lambda sid: CK if sid == "cas" else None)
    monkeypatch.setattr(sessions, "save_cas_from_jar", lambda jar: 1)

    def request(c, url, **kwargs):
        assert c.route == "direct"  # Never inherit application WebVPN routing.
        assert kwargs["allow_redirects"] is False
        service = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["service"][0]
        seen.append(service)
        return 302, "", service + ("&" if "?" in service else "?") + "ticket=ST-synthetic", b""

    monkeypatch.setattr(jwxt.JwxtClient, "_request", request)
    return seen


@pytest.fixture
def srv(tmp_path):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(ui.Store(tmp_path)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def get(port, sid="jwxt", **query):
    path = "/api/sso/jump?" + urllib.parse.urlencode({"id": sid, "n": ui.SSO_NONCE, **query})
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", path, headers={"Host": "127.0.0.1"})
    r = c.getresponse()
    result = r.status, dict(r.getheaders()), r.read().decode()
    c.close()
    return result


def test_fresh_tickets_use_original_service_and_only_callback_is_proxied(cas, monkeypatch):
    from jlu_toolkit import webvpn
    monkeypatch.setattr(webvpn, "mode", lambda: "webvpn")
    direct = sso.issue_ticket("jwxt")
    proxy = sso.issue_ticket("jwxt", "webvpn")
    assert direct == jwxt.IEDU_PORTAL + "?ticket=ST-synthetic"
    assert campus.vpn_url_decode(proxy) == direct
    assert cas == [jwxt.IEDU_PORTAL, jwxt.IEDU_PORTAL]
    status = sso.last_status("jwxt")
    assert status["state"] == "issued" and "免登跳转" in status["message"]
    assert "已登录" not in status["message"] and "登录成功" not in status["message"]
    raw = (jwxt.config_dir() / "browser-handoff.json").read_text()
    assert "ST-" not in raw and "TGT" not in raw and "https" not in raw


@pytest.mark.parametrize("target", [
    "https://iedu.jlu.edu.cn/?ticket=ST-x",  # Wrong service path.
    "https://vpn.jlu.edu.cn/?ticket=ST-x",  # Another trusted school host is still wrong.
    jwxt.IEDU_PORTAL + "?ticket=ST-x&ticket=ST-y",
    jwxt.IEDU_PORTAL + "?ticket=ST-x#fragment",
    "https://evil.example/?ticket=ST-x",
    "https://[invalid",
])
def test_invalid_callbacks_never_report_success(cas, monkeypatch, target):
    monkeypatch.setattr(jwxt.JwxtClient, "_request", lambda *a, **k: (302, "", target, b""))
    with pytest.raises(sso.BrowserJumpError):
        sso.issue_ticket("jwxt")
    assert sso.last_status("jwxt")["state"] != "issued"


def test_failure_page_reports_network_error_without_discarding_app_session(cas, srv, monkeypatch):
    c = jwxt.JwxtClient()
    c.save_session()

    def fail(*a, **k):
        raise jwxt.NetworkError("sensitive debug text", "network")

    monkeypatch.setattr(jwxt.JwxtClient, "_request", fail)
    code, headers, body = get(srv)
    assert code == 409 and "Location" not in headers
    assert "连接学校认证服务失败" in body and "重试免登" in body
    assert "在网站独立登录" in body and "sensitive debug text" not in body
    assert "TGT-" not in body and "ST-" not in body
    assert jwxt.session_status()["state"] == "ok"
    assert sso.last_status("jwxt")["state"] == "network"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_expired_cas_does_not_expire_jwxt(cas, monkeypatch):
    jwxt.JwxtClient().save_session()
    monkeypatch.setattr(jwxt.JwxtClient, "_request", lambda *a, **k:
                        (200, '<form id="loginForm">', jwxt.CAS_LOGIN, b""))
    with pytest.raises(sso.BrowserJumpError, match="已过期"):
        sso.issue_ticket("ilearn")
    assert jwxt.session_status()["state"] == "ok"
    assert sso.last_status("ilearn")["state"] == "expired"


def test_vpn_setup_does_not_issue_tickets_until_user_chooses_step(cas, srv):
    code, _, body = get(srv, route="webvpn", stage="setup")
    assert code == 200 and cas == []
    assert "1. 在浏览器连接 WebVPN" in body and "2. 进入目标服务" in body
    assert "相同的浏览器" in body and "ST-" not in body
    code, headers, _ = get(srv, "vpn")
    assert code == 302
    assert cas == [sso.SSO_TARGETS["vpn"][0]]
    assert headers["Location"].startswith("https://vpn.jlu.edu.cn/login?cas_login=true&ticket=")
    code, headers, _ = get(srv, route="webvpn", stage="target")
    assert code == 302 and cas[-1] == jwxt.IEDU_PORTAL
    assert campus.vpn_url_decode(headers["Location"]) == jwxt.IEDU_PORTAL + "?ticket=ST-synthetic"


@pytest.mark.parametrize("stage", [None, "start", "target"])
def test_normal_vpn_open_goes_straight_to_school(cas, srv, stage):
    query = {"route": "webvpn"}
    if stage is not None:
        query["stage"] = stage
    code, headers, body = get(srv, **query)
    assert code == 302 and body == ""
    assert campus.vpn_url_decode(headers["Location"]) == jwxt.IEDU_PORTAL + "?ticket=ST-synthetic"
    assert cas == [jwxt.IEDU_PORTAL]


def test_own_login_site_stays_independent(cas, srv):
    code, headers, _ = get(srv, "pay", route="webvpn", stage="target")
    assert code == 302 and not cas
    assert campus.vpn_url_decode(headers["Location"]) == sso.BROWSER_TARGETS["pay"]


@pytest.mark.parametrize("query", [{"route": "auto"}, {"stage": "bad"}])
def test_invalid_flow_does_not_issue_ticket(cas, srv, query):
    assert get(srv, **query)[0] == 400 and not cas


def test_session_status_is_local_read_only_and_does_not_assert_ilearn_login(cas):
    jwxt.JwxtClient().save_session()
    data = sessions.all_status()
    il = next(s for s in data["sites"] if s["id"] == "ilearn")
    assert il["state"] == "missing" and not cas
