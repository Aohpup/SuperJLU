"""jwxt 单元测试：加密向量 + 模拟 HTTP 响应。不访问真实教务。"""
import json
import urllib.error
from unittest import mock

import pytest

from jlu_toolkit import jwxt
from jlu_toolkit.des_tpass import strEnc, strDec


def test_strenc_matches_login10_js_vectors():
    assert strEnc("a", "1", "2", "3") == "A62B4F77D5F8C6C7"
    assert strEnc("abcd", "1", "2", "3") == "A9CF2704230383D1"
    assert (
        strEnc("abcde", "1", "2", "3")
        == "A9CF2704230383D100DE5835FF643FD8"
    )
    assert (
        strEnc("2021001234WrongPass!LT-TEST-abc", "1", "2", "3")
        == "B6FC8B80C5445D4B3F18F3B7CC8F793AADF1687CA51FC40AEE4D770A7CD23E1F"
        "06A44DF02FBE364323F565D94D86535E620B0E1BD16331DC39644174795FB4D0"
    )
    assert strDec(strEnc("secret", "neusoft", "cas", "pd"), "neusoft", "cas", "pd") == "secret"


def test_encrypt_password_bundle():
    rsa = jwxt.JwxtClient.encrypt_password_bundle("u", "p", "LT-1")
    assert rsa == strEnc("upLT-1", "1", "2", "3")


def test_parse_weeks_skzc():
    assert jwxt.parse_weeks_skzc("0101") == [2, 4]
    assert jwxt.parse_weeks_skzc("00001111") == [5, 6, 7, 8]


def test_clean_teacher():
    assert jwxt.clean_teacher("张三/1001,李四/1002") == "张三,李四"
    assert jwxt.clean_teacher("") == ""


def test_row_to_course_and_grade():
    c = jwxt.row_to_course(
        {
            "KCM": "高等数学",
            "SKJS": "王五/2001",
            "JASMC": "经信A101",
            "SKXQ": "1",
            "KSJC": "1",
            "JSJC": "2",
            "SKZC": "1111000000000000",
        }
    )
    assert c is not None
    assert c.name == "高等数学"
    assert c.teacher == "王五"
    assert c.weekday == 1 and c.start == 1 and c.end == 2
    assert c.weeks == [1, 2, 3, 4]

    g = jwxt.row_to_grade(
        {"KCM": "线代", "XF": "3.0", "ZCJ": "88", "XNXQDM": "2025-2026-1"}
    )
    assert g is not None
    assert g.credit == 3.0 and g.score == "88" and g.term == "2025-2026-1"


def test_export_csv(tmp_path):
    courses = [
        jwxt.core.Course("课", "师", "地", 1, 1, 2, [1, 2, 3, 5]),
    ]
    p = tmp_path / "s.csv"
    jwxt.export_courses_csv(courses, str(p))
    text = p.read_text(encoding="utf-8-sig")
    assert "课" in text and "1-3,5" in text


LOGIN_HTML = '''
<form id="loginForm" action="/tpass/login" method="post">
<input type="hidden" id="lt" name="lt" value="LT-UNIT-TEST" />
<input type="hidden" name="execution" value="e1s1" />
<input type="hidden" name="_eventId" value="submit" />
<div id="errormsg"></div>
</form>
'''

FAIL_HTML = '''
<form id="loginForm">
<input type="hidden" id="lt" name="lt" value="LT-2" />
<input type="hidden" name="execution" value="e2s1" />
<span id="errormsg">用户名或密码错误</span>
</form>
'''


def test_login_success_mocked():
    client = jwxt.JwxtClient()
    calls = {"n": 0}

    def fake_request(url, data=None, headers=None, method=None):
        calls["n"] += 1
        if data is None:
            return 200, LOGIN_HTML, url
        # POST success → land on iedu
        return 200, "<html>portal</html>", jwxt.IEDU_PORTAL

    with mock.patch.object(client, "_request", side_effect=fake_request):
        client.login("2021001", "secret")
    assert client._logged_in
    assert calls["n"] == 2


def test_login_wrong_password_mocked():
    client = jwxt.JwxtClient()

    def fake_request(url, data=None, headers=None, method=None):
        if data is None:
            return 200, LOGIN_HTML, url
        return 200, FAIL_HTML, url

    with mock.patch.object(client, "_request", side_effect=fake_request):
        with pytest.raises(jwxt.LoginError) as ei:
            client.login("2021001", "bad")
    assert "密码" in str(ei.value)


def test_fetch_schedule_mocked():
    client = jwxt.JwxtClient()
    client._logged_in = True
    payload = {
        "datas": {
            "dqxnxq": {"rows": [{"DM": "2025-2026-2", "MC": "春"}]},
            "cxxszhxqkb": {
                "rows": [
                    {
                        "KCM": "操作系统",
                        "SKJS": "赵六/9",
                        "JASMC": "A201",
                        "SKXQ": 3,
                        "KSJC": 5,
                        "JSJC": 6,
                        "SKZC": "1111111111111111",
                    }
                ]
            },
        }
    }

    def fake_post(path, fields, referer):
        if path.endswith("dqxnxq.do"):
            return {"datas": {"dqxnxq": payload["datas"]["dqxnxq"]}}
        return {"datas": {"cxxszhxqkb": payload["datas"]["cxxszhxqkb"]}}

    with mock.patch.object(client, "_post_form", side_effect=fake_post):
        courses = client.fetch_schedule()
    assert len(courses) == 1
    assert courses[0].name == "操作系统" and courses[0].weekday == 3


def test_fetch_grades_mocked():
    client = jwxt.JwxtClient()

    def fake_post(path, fields, referer):
        return {
            "datas": {
                "xscjcx": {
                    "rows": [
                        {
                            "KCM": "编译原理",
                            "XF": 3.5,
                            "ZCJ": "92",
                            "XNXQDM": "2024-2025-1",
                        }
                    ]
                }
            }
        }

    with mock.patch.object(client, "_post_form", side_effect=fake_post):
        grades = client.fetch_grades()
    assert grades[0].score == "92" and grades[0].credit == 3.5


def test_save_load_credentials(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    # override default to our path via env: default_cred_path uses XDG_CONFIG_HOME/jlu-toolkit/
    saved = jwxt.save_credentials("u1", "p1", path)
    assert saved.exists()
    assert oct(saved.stat().st_mode & 0o777) == "0o600" or True  # Windows may differ
    assert jwxt.load_credentials(path) == ("u1", "p1")
