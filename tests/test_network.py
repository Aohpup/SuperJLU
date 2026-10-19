"""Synthetic TLS, redirect and cookie recovery. No school network or real login."""
import ssl
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

import pytest

from jlu_toolkit import jwxt, network

CAS = "https://cas.jlu.edu.cn/tpass/login"


def eof():
    return urllib.error.URLError(ssl.SSLEOFError(8, "UNEXPECTED_EOF_WHILE_READING"))


def handler(monkeypatch, failure=None):
    monkeypatch.setattr(network.time, "sleep", lambda _: None)
    calls = []

    def broken(self, req):
        calls.append(req)
        raise failure or eof()
    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", broken)
    return network.SchoolHTTPSHandler(ssl.create_default_context()), calls


def request(url=CAS, data=None):
    req = urllib.request.Request(url, data=data)
    req.timeout = 5
    return req


def test_wrapped_ssl_eof_recovers_per_hop_and_keeps_cookie_redirect_pipeline(monkeypatch):
    recovery, original = handler(monkeypatch)
    monkeypatch.setattr(network, "native_available", lambda: True)
    seen = []

    def native(req, timeout):
        seen.append(req)
        if req.full_url == CAS:
            return network._response(req, 302,
                "Location: https://iedu.jlu.edu.cn/\r\nSet-Cookie: CAS=test; Path=/\r\n", b"")
        return network._response(req, 200, "Set-Cookie: BUSINESS=test; Path=/\r\n", b"synthetic")
    monkeypatch.setattr(network, "native_open", native)
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), recovery)
    with opener.open(CAS, timeout=5) as response:
        assert response.read() == b"synthetic"
    assert len(original) == 2 and len(seen) == 2
    assert {c.name for c in jar} == {"CAS", "BUSINESS"}
    assert recovery.native_hosts == {"cas.jlu.edu.cn", "iedu.jlu.edu.cn"}
    # A subsequent POST uses the selected stack on its first attempt, without
    # exposing the body to a subprocess or repeating it on failure.
    sent = []
    def fail_post(req, timeout):
        sent.append(req)
        raise OSError("offline")
    monkeypatch.setattr(network, "native_open", fail_post)
    with pytest.raises(OSError):
        opener.open(request(CAS, b"synthetic-password-form"), timeout=5)
    assert len(sent) == 1 and len(original) == 2
    assert sent[0].get_header("Cookie") == "CAS=test"


@pytest.mark.parametrize("url,data", [
    (CAS, b"password-form"),
    ("https://cas.jlu.edu.cn/tpass/recheckcode?code=example", None),
    ("https://cas.jlu.edu.cn/tpass/logout", None),
    ("https://iedu.jlu.edu.cn/?ticket=ST-synthetic", None),
    ("https://outside.invalid/", None),
])
def test_password_otp_logout_ticket_and_foreign_host_are_not_replayed(monkeypatch, url, data):
    recovery, calls = handler(monkeypatch)
    monkeypatch.setattr(network, "native_open", lambda *args: pytest.fail("unsafe replay"))
    with pytest.raises(urllib.error.URLError):
        recovery.https_open(request(url, data))
    assert len(calls) == 1


def test_certificate_error_never_switches_or_disables_validation(monkeypatch):
    recovery, calls = handler(monkeypatch, urllib.error.URLError(ssl.SSLCertVerificationError(1, "invalid")))
    monkeypatch.setattr(network, "native_open", lambda *args: pytest.fail("certificate bypass"))
    assert recovery._context.check_hostname and recovery._context.verify_mode == ssl.CERT_REQUIRED
    with pytest.raises(urllib.error.URLError):
        recovery.https_open(request())
    assert len(calls) == 1


def test_non_native_platform_has_only_one_retry(monkeypatch):
    recovery, calls = handler(monkeypatch)
    monkeypatch.setattr(network, "native_available", lambda: False)
    with pytest.raises(urllib.error.URLError):
        recovery.https_open(request())
    assert len(calls) == 2


def test_failed_native_recovery_preserves_tls_classification(monkeypatch):
    recovery, calls = handler(monkeypatch)
    monkeypatch.setattr(network, "native_available", lambda: True)
    monkeypatch.setattr(network, "native_open", lambda *args: (_ for _ in ()).throw(OSError("native offline")))
    with pytest.raises(urllib.error.URLError) as error:
        recovery.https_open(request())
    assert network.error_kind(error.value) == "tls" and len(calls) == 1


def test_error_is_classified_and_redacts_complete_query():
    text = network.error_message(CAS + "?service=private&ticket=ST-secret&code=secret", eof())
    assert "cas.jlu.edu.cn:443" in text and "TLS/SSL" in text
    assert all(secret not in text for secret in ("private", "ST-secret", "code="))
    assert network.error_kind(urllib.error.URLError(TimeoutError())) == "timeout"
    assert network.error_kind(ssl.SSLCertVerificationError()) == "certificate"


def test_client_does_not_replay_complete_redirect_chain_or_mark_login_expired(monkeypatch):
    c = jwxt.JwxtClient(route="direct")
    monkeypatch.setattr(c.opener, "open", lambda *args, **kwargs: (_ for _ in ()).throw(eof()))
    monkeypatch.setattr(jwxt, "mark_session_expired", lambda *args: pytest.fail("network is not expired login"))
    with pytest.raises(jwxt.NetworkError) as error:
        c._request(CAS + "?ticket=ST-secret")
    assert error.value.kind == "tls" and "ST-secret" not in str(error.value)


def test_authentication_uses_system_stack_from_first_get_through_otp_post(monkeypatch):
    monkeypatch.setattr(network, "native_available", lambda: True)
    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", lambda *args: pytest.fail("authentication stack changed"))
    seen = []
    def native(req, timeout):
        seen.append(req.get_method())
        return network._response(req, 200, "Content-Type: text/plain\r\n", b"synthetic")
    monkeypatch.setattr(network, "native_open", native)
    c = jwxt.JwxtClient(route="direct")
    c._request(CAS)
    c._request(CAS, data=b"rsa=synthetic")
    c._request(CAS, data=b"WxCode=synthetic")
    assert seen == ["GET", "POST", "POST"]


@pytest.mark.parametrize("fail_at", ["verification", "callback"])
def test_otp_validation_and_business_callback_failures_are_distinct_and_never_replay(monkeypatch, fail_at):
    monkeypatch.setattr(network, "native_available", lambda: True)
    seen = []
    def native(req, timeout):
        seen.append(req)
        if req.get_method() == "POST" and fail_at == "verification":
            raise ssl.SSLEOFError(8, "unexpected EOF")
        if req.get_method() == "POST":
            return network._response(req, 302, "Location: https://iedu.jlu.edu.cn/?ticket=ST-synthetic\r\n", b"")
        raise ssl.SSLEOFError(8, "callback EOF")
    monkeypatch.setattr(network, "native_open", native)
    c = jwxt.JwxtClient(route="direct")
    c.pending = jwxt.PendingSecondFactor("synthetic-lt", "synthetic-execution")
    for cookie in jwxt.jar_from_list([{"name":"CASTGC", "value":"synthetic-CAS", "domain":"cas.jlu.edu.cn"}]):
        c.jar.set_cookie(cookie)
    with pytest.raises(jwxt.NetworkError) as error:
        c.login_second_factor("synthetic-image", "synthetic-otp")
    text = str(error.value)
    assert len([r for r in seen if r.get_method() == "POST"]) == 1
    assert "ST-synthetic" not in text and "synthetic-otp" not in text
    if fail_at == "verification":
        assert "提交二次认证验证码" in text and "cas.jlu.edu.cn:443" in text
    else:
        assert "已返回跳转" in text and "iedu.jlu.edu.cn:443" in text
        assert error.value.can_connect_vpn is True
        assert "无需重发验证码" in text
