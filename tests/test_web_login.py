"""应用内登录接口：/api/login/* 走 jwxt 的分步登录，不需要终端。"""
import json
import urllib.request
from http.server import ThreadingHTTPServer
import threading

import pytest

from jlu_toolkit import captcha, captcha_util, jwxt, ui
from jlu_toolkit.web_login import LoginFlow

PNG = b"\x89PNG\r\n\x1a\nfake"


class FakeClient:
    def __init__(self, first=jwxt.LoginStep.NEED_SECOND_FACTOR):
        self.first = first
        self.last_captcha_bytes = PNG
        self.last_error_text = ""
        self.saved = False
        self.calls = []
        self.answers = ["xxxx", "abcd"]
        self.sent = []
        self.second = None

    def login_password(self, u, p):
        self.calls.append(("pw", u, p))
        return self.first if p == "good" else jwxt.LoginStep.WRONG_PASSWORD


    def download_captcha(self, path=None, save=True):
        self.saved_flags = getattr(self, "saved_flags", []) + [save]
        a = self.answers.pop(0) if self.answers else ""
        self.last_captcha_bytes = a.encode()
        return None

    def request_wechat_code(self, cap):
        self.sent.append(cap)
        return jwxt.WechatCodeResult.SUCCESS if cap == "abcd" else jwxt.WechatCodeResult.CAPTCHA_ERROR

    def login_second_factor(self, cap, wx):
        self.second = cap
        return jwxt.LoginStep.SUCCESS if wx == "123456" else jwxt.LoginStep.FAILED

    def bootstrap_emap_apps(self):
        self.calls.append(("emap",))

    def save_session(self):
        self.saved = True


@pytest.fixture(autouse=True)
def fake_ocr(monkeypatch):
    # 测试里“图片”就是答案本身
    monkeypatch.setattr(captcha_util, "ocr_digits", lambda b: b.decode() or None)


def test_ocr_keeps_failing_gives_retry_not_captcha(creds):
    fc = FakeClient()
    fc.answers = ["zzzz"] * 10
    f = LoginFlow(lambda: fc)
    f.start("u", "good")
    r = f.send_code()
    assert r["retry"] is True and "captcha" not in r and r["error"]
    fc.answers = ["abcd"]
    assert f.send_code() == {"step": "code_sent"}


def test_solve_with_retry_helper():
    imgs = iter([b"", b"1111", b"2222"])
    tried = []
    assert captcha.solve_with_retry(lambda: next(imgs), lambda c: tried.append(c) or c == "2222", 3) == "2222"
    assert tried == ["1111", "2222"]
    assert captcha.solve(b"") == ""


def test_real_solver_reads_digits():
    pytest.importorskip("PIL")
    from jlu_toolkit import captcha_solver
    assert captcha_solver.load_templates()


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
    assert r == {"step": "need_second_factor"}  # 不再把图形验证码交给前端
    assert f.send_code() == {"step": "code_sent"}
    assert fc.sent == ["xxxx", "abcd"]  # 第一张识别错，自动换图重试
    assert f.verify(wechat_code="000000")["error"]
    assert f.verify(wechat_code="123456") == {"step": "success"}
    assert fc.second == "abcd"
    assert fc.saved and ("emap",) in fc.calls
    assert creds["cred"] == ("zhangsan", "good")
    with pytest.raises(ValueError):
        f.send_code()  # 流程结束后状态清空


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
        assert post("/api/login/send_code", {})["step"] == "code_sent"
        assert post("/api/login/verify", {"wechat_code": "123456"})["step"] == "success"
        page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
        assert 'id="login"' in page and "fetch --force-login" not in page
        assert 'id="lgc"' not in page and 'id="lgi"' not in page and "/api/login/captcha" not in page
    finally:
        httpd.shutdown()


def test_start_uses_saved_password_for_other_account(monkeypatch):
    monkeypatch.setattr(jwxt, "load_credentials", lambda: ("a", "pa"))
    monkeypatch.setattr(jwxt, "account_password", lambda u: {"b": "good"}.get(u))
    fc = FakeClient()
    f = LoginFlow(lambda: fc)
    f.start("b", "", remember=True)
    assert ("pw", "b", "good") in fc.calls


def test_app_login_never_saves_captcha_files(tmp_path, monkeypatch):
    from jlu_toolkit import jwxt as j
    monkeypatch.chdir(tmp_path)
    c = j.JwxtClient()
    c.last_captcha_paths = ["x"]
    c.pending = None
    c.last_content_type = "image/jpeg"
    jpg = bytes.fromhex("ffd8ffe000104a464946") + b"\0" * 200 + bytes.fromhex("ffd9")
    monkeypatch.setattr(j.captcha_util, "validate_captcha_bytes", lambda *a, **k: ("jpeg", 70, 36))
    c._request = lambda *a, **k: (200, "", "", jpg)
    assert c.download_captcha(save=False) is None
    assert c.last_captcha_bytes == jpg and c.last_captcha_paths == []
    assert list(tmp_path.iterdir()) == []


def test_solve_with_retry_respects_budget(monkeypatch):
    import time
    from jlu_toolkit import captcha
    t = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: t[0])
    calls = []

    def fetch():
        calls.append(1); t[0] += 20
        return b"x"
    monkeypatch.setattr(captcha, "solve", lambda b: "abcd")
    assert captcha.solve_with_retry(fetch, lambda c: False, tries=6, budget=30) is None
    assert len(calls) == 2


def test_fetch_captcha_does_not_retain_bytes():
    from jlu_toolkit.web_login import LoginFlow

    class C:
        last_captcha_bytes = None

        def download_captcha(self, path=None, save=True):
            assert save is False
            self.last_captcha_bytes = b"img" * 700

    f = LoginFlow(lambda: C())
    f._client = C()
    for _ in range(50):
        assert f._fetch_captcha() == b"img" * 700
        assert f._client.last_captcha_bytes is None
