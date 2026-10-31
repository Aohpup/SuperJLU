from jlu_toolkit import jwxt, web_login
import pytest


def test_friendly_cas_error():
    m = jwxt.friendly_cas_error("CA认证中心异常，请稍后再试")
    assert m.startswith("CA认证中心异常") and "不是账号或密码错误" in m and "校外 WebVPN" in m
    assert "校外 WebVPN" not in jwxt.friendly_cas_error("CA认证中心异常，请稍后再试", webvpn=True)
    assert jwxt.friendly_cas_error("用户名或密码错误") == "用户名或密码错误"
    assert jwxt.friendly_cas_error("") == ""


def test_extract_then_friendly_from_cas_page():
    html = '<form id="loginForm"><span id="errormsg" class="script_red">CA认证中心异常，请稍后再试</span></form>'
    assert jwxt.extract_cas_error(html) == "CA认证中心异常，请稍后再试"


class _C:
    route = "direct"
    last_error_text = "CA认证中心异常，请稍后再试"

    def login_password(self, u, p, service=None):
        return jwxt.LoginStep.WRONG_PASSWORD


def test_login_flow_shows_helpful_message():
    f = web_login.LoginFlow(client_factory=_C)
    with pytest.raises(ValueError) as e:
        f.start("abc", "x", remember=False)
    assert "不是账号或密码错误" in str(e.value)
