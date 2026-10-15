"""exams / explore / ui 单元测试（不访问教务）。"""
import datetime as dt
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from jlu_toolkit import exams, explore, jwxt, ui


def test_parse_kssjms():
    assert exams.parse_kssjms("2023-04-27 10:10-12:10(星期四)") == ("2023-04-27T10:10", "2023-04-27T12:10")
    assert exams.parse_kssjms("2026年1月6日 9:00~11:00") == ("2026-01-06T09:00", "2026-01-06T11:00")
    assert exams.parse_kssjms("") == ("", "")


def test_row_to_exam_numeric_and_missing():
    e = exams.row_to_exam(
        {"KCM": "操作系统", "KSSJMS": "2026-12-28 13:30-15:30(星期一)", "JASMC": None, "ZWH": 7.0, "XNXQDM": "2026-2027-1"},
        jwxt._emap_str,
    )
    assert e.start == "2026-12-28T13:30" and e.location == "待定" and e.seat == "7"
    e2 = exams.row_to_exam({"KCM": "体育", "KSRQ": "2027-01-02 00:00:00"}, jwxt._emap_str)
    assert e2.start == "2027-01-02T00:00"
    assert exams.row_to_exam({"KCM": ""}, jwxt._emap_str) is None


def test_countdown_and_upcoming(tmp_path):
    now = dt.datetime(2026, 10, 15, 9, 0)
    a = exams.Exam("A", "2026-10-17T13:30", "2026-10-17T15:30", "x")
    b = exams.Exam("B", "2026-10-01T08:00", "2026-10-01T10:00", "y")
    c = exams.Exam("C", "", "", "z")
    assert exams.format_countdown(exams.countdown(a, now)) == "还有 2 天 4 小时"
    assert exams.format_countdown(exams.countdown(b, now)) == "已结束"
    assert exams.format_countdown(None) == "时间待定"
    assert [e.name for e in exams.upcoming([c, b, a], now)] == ["A", "C"]
    p = tmp_path / "e.csv"
    exams.export_exams_csv([a, c], str(p))
    assert exams.load_exams(str(p)) == [a, c]


def test_fetch_exams_falls_back():
    client = jwxt.JwxtClient()
    calls = []

    def fake_post(path, fields, referer):
        calls.append(path)
        if path == jwxt.EP_EXAMS_ALT:
            return 404, "", path
        return 200, json.dumps({"datas": {"wdksap": {"rows": [
            {"KCM": "数据结构", "KSSJMS": "2026-11-03 08:00-10:00", "JASMC": "A101"}]}}}), path

    with pytest.MonkeyPatch.context() as m:
        m.setattr(client, "enter_emap_app", lambda app: None)
        m.setattr(client, "post_raw", fake_post)
        got = client.fetch_exams("2026-2027-1")
    assert calls == [jwxt.EP_EXAMS_ALT, jwxt.EP_EXAMS]
    assert got[0].name == "数据结构"


def test_summarize_json_has_no_values():
    data = {"code": "0", "datas": {"cxxsjbxxlb": {"totalSize": 1, "extParams": {"code": 1, "msg": "张三"},
             "rows": [{"XM": "张三", "XH": "20230001", "SFZJH": "220102200001011234"}]}}}
    s = explore.summarize_json(data)
    dumped = json.dumps(s, ensure_ascii=False)
    for secret in ("张三", "20230001", "220102200001011234"):
        assert secret not in dumped
    blk = s["datas"]["cxxsjbxxlb"]
    assert blk["rows"] == 1 and blk["fields"] == ["SFZJH", "XH", "XM"]


def test_probes_are_read_only():
    for pr in explore.PROBES:
        if pr.path:
            explore._assert_read_only(pr.path)
    with pytest.raises(ValueError):
        explore._assert_read_only("/jwapp/sys/xywccx/modules/xywccx/bysc.do")


def test_run_explore_sanitized():
    client = jwxt.JwxtClient()

    def fake_req(url, data=None, headers=None, method=None, allow_redirects=True):
        return 200, "<html>secret-name</html>", url, b""

    def fake_post(path, fields, referer):
        return 200, json.dumps({"datas": {"x": {"rows": [{"XM": "李四"}]}}}), "https://iedu.jlu.edu.cn" + path

    with pytest.MonkeyPatch.context() as m:
        m.setattr(client, "_request", fake_req)
        m.setattr(client, "post_raw", fake_post)
        rep = explore.run_explore(client, "2026-2027-1", log=lambda s: None)
    dumped = json.dumps(rep, ensure_ascii=False)
    assert "李四" not in dumped and "secret-name" not in dumped
    assert len(rep["probes"]) == sum(1 for p in explore.PROBES if p.path)


@pytest.fixture
def server(tmp_path):
    ui.seed_demo(tmp_path)
    store = ui.Store(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(store))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path
    httpd.shutdown()


def _get(url, host=None):
    req = urllib.request.Request(url, headers={"Host": host} if host else {})
    with urllib.request.urlopen(req) as r:
        return r.status, r.read(), r.headers


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def test_ui_page_and_data(server):
    base, _ = server
    code, body, _ = _get(base + "/")
    assert code == 200 and b"JLU Toolkit" in body
    assert b"http://" not in body and b"https://" not in body  # 无外部资源
    _, raw, _ = _get(base + "/api/data")
    d = json.loads(raw)
    assert d["courses"] and d["grades"] and d["exams"]
    assert "保研" in d["schemes"]
    assert all("key" in g for g in d["grades"])


def test_ui_rejects_foreign_host(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(base + "/api/data", host="evil.example")
    assert e.value.code == 403


def test_ui_schemes_settings_ics(server):
    base, root = server
    d = _post(base + "/api/schemes", {"name": "综测", "include": ["2024-2025-1|线性代数"]})
    assert d["schemes"]["综测"] == ["2024-2025-1|线性代数"]
    assert json.loads((root / "schemes.json").read_text(encoding="utf-8"))["综测"]
    d = _post(base + "/api/schemes/delete", {"name": "综测"})
    assert "综测" not in d["schemes"]
    with pytest.raises(urllib.error.HTTPError):
        _post(base + "/api/settings", {"first_monday": "2026-09-08"})  # 不是周一
    _post(base + "/api/settings", {"first_monday": "2026-09-07"})
    code, body, hdr = _get(base + "/api/ics")
    assert code == 200 and body.startswith(b"BEGIN:VCALENDAR")


def test_ui_refresh_without_session(server, tmp_path, monkeypatch):
    base, _ = server
    monkeypatch.setattr(jwxt.JwxtClient, "load_session", lambda self, path=None: False)
    with pytest.raises(urllib.error.HTTPError) as e:
        _post(base + "/api/refresh", {})
    assert e.value.code == 400
