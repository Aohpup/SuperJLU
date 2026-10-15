import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from jlu_toolkit import oa_subscribe as osub, ui


def row(i, title, dept, top=False):
    t = f"<font color=red>[置顶]</font>{title}" if top else title
    return (f'<div class="li rel"><a class="font14" href="PortalInformation!getInformation.action?id={i}&channelId=179577">{t}</a>'
            f'<span>2026年10月15日 09:00</span><a href="#">{dept}</a></div>')


class Fake:
    def __init__(self):
        self.rows, self.urls = [row(1, "放假安排", "校长办公室", True), row(2, "选课通知", "教务处")], []

    def _request(self, url, data=None, headers=None, method=None, allow_redirects=True):
        assert data is None
        self.urls.append(url)
        h = "<html><body>" + "".join(self.rows) + "<span>共 2508 页</span></body></html>"
        return 200, h, url, h.encode()


@pytest.fixture(autouse=True)
def nosleep(monkeypatch):
    monkeypatch.setattr(osub.time, "sleep", lambda s: None)


def test_rules_crud_and_validation(tmp_path):
    r = osub.add_rule("讲座， 奖学金,讲座", "教务处", root=tmp_path)
    assert r["keywords"] == ["讲座", "奖学金"] and r["depts"] == ["教务处"] and r["channel"] == "179577"
    assert osub.list_rules(tmp_path) == [r]
    for bad in ("", [], [1], "x" * 41):
        with pytest.raises(ValueError):
            osub.add_rule(bad, root=tmp_path)
    with pytest.raises(ValueError):
        osub.add_rule("a", channel="abc", root=tmp_path)
    assert osub.remove_rule(r["id"], tmp_path) and not osub.remove_rule(r["id"], tmp_path)
    assert osub.list_rules(tmp_path) == []


def test_match():
    n = {"title": "学术讲座预告", "dept": "研究生院", "channel": "179577"}
    assert osub.match(n, {"keywords": ["讲座", "补考"]}) == ["讲座"]
    assert osub.match(n, {"keywords": ["讲座"], "depts": ["教务处"]}) == []
    assert osub.match(n, {"keywords": ["研究生"], "depts": ["研究生院"]}) == ["研究生"]
    assert osub.match(n, {"keywords": ["讲座"], "channel": "1"}) == []


def test_sync_page1_only_and_seed(tmp_path):
    c = Fake()
    first = osub.sync(c, root=tmp_path)
    assert first["first_run"] and first["new"] == [] and first["seeded"] == 2
    assert len(c.urls) == 1 and "startPage=1" in c.urls[0]
    c.rows.insert(1, row(3, "奖学金评审通知", "学生处"))
    again = osub.sync(c, root=tmp_path)
    assert [i["id"] for i in again["new"]] == ["3"] and all("startPage=1" in u for u in c.urls)
    assert osub.sync(c, root=tmp_path)["new"] == []
    assert (tmp_path / "oa_notices.json").exists()


def test_watch_once_seeds_then_notifies(tmp_path):
    c, sent, out = Fake(), [], []
    osub.add_rule("奖学金", root=tmp_path)
    res = osub.watch_once(c, tmp_path, notifier=lambda t, m: sent.append((t, m)), out=out.append)
    assert res == {"new": 0, "matches": 0} and sent == [] and "首次运行" in out[0]
    c.rows.append(row(4, "2026 奖学金名单", "学生处"))
    c.rows.append(row(5, "食堂通知", "后勤"))
    res = osub.watch_once(c, tmp_path, notifier=lambda t, m: sent.append((t, m)), out=out.append)
    assert res == {"new": 2, "matches": 1} and len(sent) == 1 and "奖学金" in sent[0][0]
    m = osub.recent_matches(root=tmp_path)
    assert m[0]["notice"]["id"] == "4" and m[0]["keywords_hit"] == ["奖学金"]
    assert osub.recent_matches(since="9999", root=tmp_path) == []


def test_notify_never_crashes(monkeypatch):
    import builtins
    real = builtins.__import__
    monkeypatch.setattr(builtins, "__import__",
                        lambda n, *a, **k: (_ for _ in ()).throw(ImportError()) if n == "plyer" else real(n, *a, **k))
    monkeypatch.setattr(osub.shutil, "which", lambda n: None)
    assert osub.notify("t", "m") == "print"
    monkeypatch.setattr(osub.shutil, "which", lambda n: "/bin/" + n if n == "notify-send" else None)
    monkeypatch.setattr(osub.sys, "platform", "linux")
    calls = []
    assert osub.notify("t", "m", runner=lambda a, **k: calls.append(a)) == "notify-send" and calls[0][0] == "notify-send"

    def boom(*a, **k):
        raise OSError("x")
    assert osub.notify("t", "m", runner=boom) == "print"


def test_http_api(tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(ui.Store(tmp_path)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/api/oa/subscriptions"

    def call(method, url, body=None):
        req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        assert call("GET", base) == (200, {"ok": True, "rules": [], "matches": []})
        code, d = call("POST", base, {"keywords": ["讲座"], "depts": "教务处"})
        assert code == 201 and d["rule"]["keywords"] == ["讲座"] and d["rule"]["depts"] == ["教务处"]
        rid = d["rule"]["id"]
        assert call("POST", base, {"keywords": []})[0] == 400
        assert call("POST", base, ["x"])[0] == 400
        assert call("GET", base)[1]["rules"][0]["id"] == rid
        assert call("DELETE", base + "/nope")[0] == 404
        assert call("DELETE", base + "?id=" + rid) == (200, {"ok": True, "removed": rid})
        rid2 = call("POST", base, {"keywords": "补考"})[1]["rule"]["id"]
        assert call("DELETE", base + "/" + rid2)[0] == 200
        assert call("DELETE", base)[0] == 405
    finally:
        srv.shutdown()


def test_cli_subscribe(tmp_path, monkeypatch, capsys):
    from jlu_toolkit import cli
    monkeypatch.setattr(ui, "data_dir", lambda: tmp_path)
    cli.main(["oa", "subscribe", "add", "-k", "讲座,补考", "--dept", "教务处", "--json"])
    rid = json.loads(capsys.readouterr().out)["id"]
    cli.main(["oa", "subscribe", "list"])
    assert rid in capsys.readouterr().out
    cli.main(["oa", "subscribe", "remove", rid])
    assert osub.list_rules(tmp_path) == []
    with pytest.raises(SystemExit):
        cli.main(["oa", "subscribe", "remove", "zzz"])


def test_list_json_includes_matches(tmp_path, monkeypatch, capsys):
    from jlu_toolkit import oa_subscribe as osub, cli
    monkeypatch.setattr(osub, "_root", lambda root=None: tmp_path)
    r = osub.add_rule("通知")
    osub.record_matches([{"id": "1", "title": "放假通知", "dept": "校办", "channel": "179577"}])
    rc = None
    try:
        cli.main(["oa", "subscribe", "list", "--json"])
    except SystemExit as e:
        rc = e.code
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert rc in (None, 0) and out["rules"][0]["id"] == r["id"] and len(out["matches"]) == 1
