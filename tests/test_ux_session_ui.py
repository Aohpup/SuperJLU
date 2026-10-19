"""BATCH 1：会话提示去掉 CLI 话术、隐私文案、部分刷新可显示。"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from jlu_toolkit import core, jwxt, sync, ui
from jlu_toolkit.ui_page import PAGE


def test_page_has_no_cli_or_config_paths():
    assert "force-login" not in PAGE
    assert "jlu-toolkit fetch" not in PAGE
    assert "jlu-toolkit oa" not in PAGE
    assert "campus_links.json" not in PAGE
    assert "127.0.0.1" not in PAGE
    assert "~/.config" not in PAGE
    assert "数据与隐私" in PAGE and "只保存在本机" in PAGE
    assert 'placeholder="密码"' in PAGE
    assert "可留空" not in PAGE
    assert "sync-ind" in PAGE and "setSyncInd" in PAGE
    assert "err.payload" in PAGE


def test_session_status_messages_are_in_app():
    msg = jwxt.session_status()["message"]
    assert "终端" not in msg and "force-login" not in msg and "jlu-toolkit" not in msg
    err = jwxt.SessionExpiredError()
    assert "更多 → 登录" in str(err)
    assert "force-login" not in str(err)
    assert "终端" not in str(err)


def test_emap_errors_are_session_expired(monkeypatch):
    from tests.test_emap_cas_exchange import APP, ON_CAS, _client

    c, _ = _client(monkeypatch, [ON_CAS])
    monkeypatch.setattr("jlu_toolkit.sessions.load_cookies", lambda *_: [])
    monkeypatch.setattr("jlu_toolkit.sessions.migrate_cas_from_jwxt", lambda *_: 0)
    with pytest.raises(jwxt.SessionExpiredError) as e:
        c.enter_emap_app(APP)
    assert "更多 → 登录" in str(e.value)
    assert "force-login" not in str(e.value)


def test_sync_all_keeps_partial_on_login_error(tmp_path, monkeypatch):
    client = jwxt.JwxtClient()
    monkeypatch.setattr(client, "current_semester", lambda: "2025-2026-1")
    monkeypatch.setattr(client, "save_session", lambda *a, **k: None)

    def ok_schedule(term=None):
        return [core.Course("高数", "张", "一教", 1, 1, 2, list(range(1, 17)))]

    def boom(*a, **k):
        raise jwxt.SessionExpiredError("教务登录已过期，请在「更多 → 登录」中重新登录。")

    monkeypatch.setattr(client, "fetch_schedule", ok_schedule)
    monkeypatch.setattr(client, "fetch_grades", boom)

    with pytest.raises(jwxt.LoginError) as e:
        sync.sync_all(client, tmp_path)
    partial = getattr(e.value, "partial", None)
    assert partial and partial["schedule"]["ok"] is True
    assert partial["grades"].get("login_needed") is True
    assert partial["exams"].get("skipped") is True
    assert (tmp_path / "schedule.csv").exists()


@pytest.fixture
def srv(tmp_path):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(ui.Store(tmp_path)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path
    httpd.shutdown()


def _post(url, body):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_refresh_returns_snapshot_on_login_error(srv, monkeypatch):
    base, root = srv
    store = ui.Store(root)
    jwxt.export_courses_csv(
        [core.Course("线代", "李", "二教", 2, 3, 4, list(range(1, 17)))],
        str(store.p("schedule.csv")),
    )

    def boom(_store):
        err = jwxt.SessionExpiredError("教务登录已过期，请在「更多 → 登录」中重新登录。")
        err.partial = {"schedule": {"ok": True, "count": 1}, "grades": {"ok": False, "login_needed": True}}
        raise err

    monkeypatch.setattr(ui, "refresh_from_jwxt", boom)
    code, j = _post(base + "/api/refresh", {})
    assert code == 401
    assert j["ok"] is False and j["session_expired"] is True
    assert "force-login" not in j["error"]
    assert "更多 → 登录" in j["error"]
    assert any(c["name"] == "线代" for c in j["courses"])
    assert j["result"]["schedule"]["ok"] is True
