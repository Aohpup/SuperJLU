"""UI failures stay short, preserve caches and distinguish auth/certificate errors."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from jlu_toolkit import jwxt, ui

DIAGNOSTIC = "空教室查询未成功；尝试：" + "cxkxjs.do/meta:HTTP404；" * 12


@pytest.fixture
def server(tmp_path):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(ui.Store(tmp_path)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", tmp_path
    httpd.shutdown(); httpd.server_close()


def post(base, path):
    req = urllib.request.Request(base + path, data=b"{}", headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req) as response: return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


@pytest.mark.parametrize("error,status", [(jwxt.JwxtError(DIAGNOSTIC), 400),
    (jwxt.NetworkError("synthetic SSL details", "tls"), 502),
    (jwxt.NetworkError("synthetic timeout details", "timeout"), 502)])
def test_room_failure_is_short_actionable_and_does_not_discard_cache(server, monkeypatch, error, status):
    base, root = server
    saved = root / "schedule.csv"
    saved.write_bytes(b"synthetic cached schedule")
    def fail(*args, **kwargs): raise error
    monkeypatch.setattr(ui, "rooms_api", fail)
    code, result = post(base, "/api/rooms")
    assert code == status and result["connection_action"]
    assert "切换登录方式" in result["error"] and len(result["error"]) < 90
    assert not any(detail in result["error"] for detail in ("HTTP404", "cxkxjs", "尝试", "SSL"))
    assert not result.get("session_expired")
    assert saved.read_bytes() == b"synthetic cached schedule"


def test_missing_login_directs_to_login_without_raw_backend_errors(server, monkeypatch):
    def fail(*args): raise jwxt.LoginError("synthetic missing session")
    monkeypatch.setattr(ui, "rooms_api", fail)
    code, result = post(server[0], "/api/rooms")
    assert code == 400 and result["connection_action"] and "登录后重试" in result["error"]


def test_real_session_expiry_remains_a_401(server, monkeypatch):
    def fail(*args): raise jwxt.SessionExpiredError("教务会话已过期")
    monkeypatch.setattr(ui, "rooms_api", fail)
    code, result = post(server[0], "/api/rooms")
    assert code == 401 and result["session_expired"]


def test_invalid_query_is_not_reported_as_a_network_or_login_problem(server, monkeypatch):
    def fail(*args): raise ValueError("请选择校区")
    monkeypatch.setattr(ui, "rooms_api", fail)
    code, result = post(server[0], "/api/rooms")
    assert code == 400 and result["error"] == "请选择校区" and not result.get("connection_action")


def test_certificate_failure_does_not_suggest_switching_auth_routes(server, monkeypatch):
    def fail(*args): raise jwxt.NetworkError("synthetic certificate error", "certificate")
    monkeypatch.setattr(ui, "rooms_api", fail)
    code, result = post(server[0], "/api/rooms")
    assert code == 502 and result["error_kind"] == "certificate"
    assert "安全连接验证失败" in result["error"] and not result["connection_action"]


@pytest.mark.parametrize("path", ["/api/grades/refresh", "/api/refresh", "/api/rooms/fields"])
def test_other_teaching_endpoints_use_the_same_short_failure(path):
    message, action = ui.teaching_error(path, jwxt.JwxtError(DIAGNOSTIC))
    assert action and "切换登录方式" in message and "HTTP404" not in message


def test_login_and_network_diagnostics_keep_their_specific_failure_stage():
    error = jwxt.NetworkError("提交二次认证验证码时连接中断", "tls")
    assert ui.teaching_error("/api/login/verify", error) == (str(error), False)
    assert ui.teaching_error("/api/network/vpn", error) == (str(error), False)
