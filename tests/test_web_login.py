"""应用内登录接口：/api/login/* 走 jwxt 的分步登录，不需要终端。"""
import json
import urllib.request
from http.server import ThreadingHTTPServer
import threading

import pytest

from jlu_toolkit import jwxt, ui
from jlu_toolkit.web_login import LoginFlow

PNG = b"\x89PNG\r\n\x1a\nfake"


class FakeClient:
    def __init__(self, first=jwxt.LoginStep.NEED_SECOND_FACTOR):
        self.first = first
        self.last_captcha_bytes = PNG
        self.last_error_text = ""
        self.saved = False
        self.calls = []

    def login_password(self, u, p):
        self.calls.append(("pw", u, p))
        return self.first if p == "good" else jwxt.LoginStep.WRONG_PASSWORD

    def download_captcha(self):
        return None

    def request_wechat_code(self, cap):
        return jwxt.WechatCodeResult.SUCCESS if cap == "abcd" else jwxt.WechatCodeResult.CAPTCHA_ERROR

    def login_second_factor(self, cap, wx):
        return jwxt.LoginStep.SUCCESS if wx == "123456" else jwxt.LoginStep.FAILED

    def bootstrap_emap_apps(self):
        self.calls.append(("emap",))

    def save_session(self):
        self.saved = True


@pytest.fixture
def creds(monkeypatch):
    box = {}
    monkeypatch.setattr(jwxt, "save_credentials", lambda u, p: box.update(cred=(u, p)))
    monkeypatch.setattr(jwxt, "load_credentials", lambda: box.get("cred"))
    return box


def test_full_two_factor_flow(creds):
    fc = FakeClient()
    f = LoginFlow(lambda: fc)
    r = f.start("zhangsan", "good", remember=True)
    assert r["step"] == "need_second_factor" and r["captcha"].startswith("data:image/png;base64,")
    r = f.send_code("xxxx")
    assert r["error"] == "图形验证码错误" and "captcha" in r
    assert f.send_code("abcd") == {"step": "code_sent"}
    assert f.verify("abcd", "000000")["error"]
    assert f.verify("abcd", "123456") == {"step": "success"}
    assert fc.saved and ("emap",) in fc.calls
    assert creds["cred"] == ("zhangsan", "good")
    with pytest.raises(ValueError):
        f.captcha()  # 流程结束后状态清空


def test_wrong_password_and_no_remember(creds):
    f = LoginFlow(lambda: FakeClient(jwxt.LoginStep.SUCCESS))
    with pytest.raises(ValueError):
        f.start("zhangsan", "bad")
    assert f.start("zhangsan", "good", remember=False) == {"step": "success"}
    assert "cred" not in creds


def test_saved_password_reused(creds):
    creds["cred"] = ("lisi", "good")
    fc = FakeClient(jwxt.LoginStep.SUCCESS)
    f = LoginFlow(lambda: fc)
    assert f.saved_username() == "lisi"
    assert f.start("", "")["step"] == "success"
    assert fc.calls[0] == ("pw", "lisi", "good")


def test_http_endpoints(tmp_path, creds):
    fc = FakeClient()
    store = ui.Store(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(store, LoginFlow(lambda: fc)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def post(path, body):
        req = urllib.request.Request(base + path, json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=5).read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    try:
        assert post("/api/login/start", {"username": "u", "password": "bad"})["ok"] is False
        assert post("/api/login/start", {"username": "u", "password": "good"})["step"] == "need_second_factor"
        assert post("/api/login/send_code", {"captcha": "abcd"})["step"] == "code_sent"
        assert post("/api/login/verify", {"captcha": "abcd", "wechat_code": "123456"})["step"] == "success"
        page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
        assert 'id="login"' in page and "fetch --force-login" not in page
    finally:
        httpd.shutdown()
