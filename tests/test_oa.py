import json

import pytest

from jlu_toolkit import oa

LIST = """<html><head><meta charset="utf-8"></head><body>
<a href="PortalInformation!jldxList.action?channelId=179577">校内通知</a>
<a href="PortalInformation!jldxList.action?channelId=179578">学术讲座</a>
<div class="li rel"><a class="font14" href="PortalInformation!getInformation.action?id=111&channelId=179577"><font color=red>[置顶]</font>放假安排</a>
<span>2026年10月01日 08:05</span><a href="#">校长办公室</a></div>
<div class="li rel"><a class="font14" href="PortalInformation!getInformation.action?id=222&channelId=179577">教务通知 选课</a>
<span>2026年10月02日 09:00</span><a href="#">教务处</a></div>
<a href="PortalInformation!jldxList.action?channelId=179577&startPage=2">2</a>
<span>共 37 页</span></body></html>"""

DETAIL = """<div class="content_t">放假安排</div><div class="content_time">2026-10-01 <span>校长办公室</span></div>
<div class="content_font"><p>正文</p></div><a href="rd/download/attachdownload.jsp?res=1">附件</a></body>"""


class Fake:
    def __init__(self, pages, login=False):
        self.pages, self.login, self.urls = pages, login, []

    def _request(self, url, data=None, headers=None, method=None, allow_redirects=True):
        assert method in (None, "GET", "POST")
        self.urls.append(url)
        if data is not None or "searchId=" in url:
            q = (data or b"").decode() + url
            ok = (data is not None and "%E" in data.decode()) or "searchId=2025" in q
            h = LIST if ok else "<html></html>"
            return 200, h, url, h.encode()
        if self.login:
            return 200, '<form id="loginForm"><input type="password" name="p"></form>', \
                "https://oa.jlu.edu.cn/defaultroot/login.jsp", b""
        if "getInformation" in url:
            return 200, DETAIL, url, DETAIL.encode()
        if url.endswith("jldx_left.js"):
            h = "var m=[{u:'PortalInformation!jldxList.action?channelId=190002',t:'放假安排'}];"
            return 200, h, url, h.encode()
        if "login.jsp" in url:
            h = '<script src="js/jldx_left.js"></script><a href="x?channelId=190001"><span>学术讲座</span></a><form action="/defaultroot/login.jsp"><input name="userAccount"><input type="password" name="userPassword"></form>'
            return 200, h, url, h.encode()
        page = int(url.split("startPage=")[1].split("&")[0]) if "startPage=" in url else 1
        h = LIST if page <= self.pages else "<html></html>"
        if page > 1:
            h = h.replace("id=111", f"id=1{page}1").replace("id=222", f"id=2{page}2")
        return 200, h, url, h.encode()


def test_parse_list():
    r = oa.parse_list(LIST)
    assert [i["id"] for i in r["items"]] == ["111", "222"]
    a, b = r["items"]
    assert a["top"] and a["title"] == "放假安排" and a["dept"] == "校长办公室" and a["time"] == "2026-10-01 08:05"
    assert not b["top"] and b["url"].endswith("id=222&channelId=179577")
    assert r["channels"] == {"179577": "校内通知", "179578": "学术讲座"} and r["total_pages"] == 37


def test_detail():
    d = oa.parse_detail(DETAIL)
    assert d["title"] == "放假安排" and d["text"] == "正文" and d["attachments"] == 1


def test_fetch_and_save(tmp_path):
    c = Fake(pages=3)
    r = oa.fetch_notices(c, limit=5, max_pages=5)
    assert r["count"] == 5 and len({i["id"] for i in r["items"]}) == 5
    r2 = oa.fetch_notices(Fake(1), keyword="教务")
    assert [i["id"] for i in r2["items"]] == ["222"]
    oa.save(tmp_path, r)
    oa.save(tmp_path, r2)
    d = json.loads((tmp_path / "oa_notices.json").read_text(encoding="utf-8"))
    assert len(d["channels_items"]["179577"]) == 5 and d["channels"]["179578"] == "学术讲座"


def test_login_needed():
    with pytest.raises(oa.jwxt.LoginError):
        oa.fetch_notices(Fake(1, login=True))


def test_probe_ascii_no_titles():
    rep = oa.probe(Fake(2), anon_client=Fake(2))
    s = json.dumps(rep)
    assert s.isascii() and "放假" not in json.dumps(rep, ensure_ascii=False)
    assert rep["list"]["rows"] == 2 and rep["list"]["categories"] == 2 and rep["detail"]["has_title"]
    assert rep["login_page"]["input_names"] == ["userAccount", "userPassword"]
    assert rep["session_reuse"]["ok"]


def test_read_only_guard():
    with pytest.raises(ValueError):
        oa.get(Fake(1), oa.BASE + "/WorkFlowAction!submit.action")


def test_category():
    assert oa.resolve_category("", {}) == "179577"
    assert oa.resolve_category("讲座", {"179578": "学术讲座"}) == "179578"


def test_cli_main_oa_probe_and_notices(monkeypatch, capsys, tmp_path):
    from jlu_toolkit import cli, jwxt, ui
    monkeypatch.setattr(jwxt.JwxtClient, "load_session", lambda self: False)
    monkeypatch.setattr(jwxt.JwxtClient, "_request", lambda self, url, **kw: Fake(2)._request(url, **kw))
    monkeypatch.setattr(ui, "data_dir", lambda: tmp_path)
    cli.main(["oa", "--probe"])
    rep = json.loads(capsys.readouterr().out)
    assert rep["list"]["rows"] == 2 and rep["saved_session"] is False
    cli.main(["oa", "notices", "--limit", "3", "--json"])
    assert json.loads(capsys.readouterr().out)["count"] == 3
    assert (tmp_path / "oa_notices.json").exists()


def test_cli_all_handlers_defined():
    import re
    from jlu_toolkit import cli
    src = open(cli.__file__, encoding="utf-8").read()
    for name in set(re.findall(r"\b(_cmd_\w+)\(x\)", src)):
        assert callable(getattr(cli, name, None)), name


def test_search_variants_and_channels():
    oa._search_pref = None
    c = Fake(1)
    sv = oa.search_variants(c)
    assert sv["post_searchId_utf8"]["cjk"] == 2 and sv["get_searchId_gbk"]["cjk"] == 0
    r = oa.fetch_notices(c, keyword="教务")
    assert [i["id"] for i in r["items"]] == ["222"]
    d = oa.discover_channels(Fake(1))
    assert d["channels"]["190001"] == "学术讲座" and d["channels"]["190002"] == "放假安排"
    assert d["sources"]["jldx_left.js"] == 1
    oa._search_pref = None
