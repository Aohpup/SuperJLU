"""#17 补充：校内网卡片经 VPN 打开（露娜 #18 的 campus.vpn_url）+ 离线缓存界面。"""
import json
import sys
import types

from jlu_toolkit import ui
from jlu_toolkit.ui_page import PAGE


def _fake_campus(monkeypatch, fn):
    m = types.ModuleType("jlu_toolkit.campus")
    m.vpn_url = fn
    monkeypatch.setitem(sys.modules, "jlu_toolkit.campus", m)


def test_campus_only_links_get_vpn_url(monkeypatch, tmp_path):
    _fake_campus(monkeypatch, lambda u: "https://vpn.jlu.edu.cn/https/77726476706e69737468656265737421" + u.split("/", 3)[-1])
    r = ui.campus_links_api(tmp_path / "none.json")
    camp = [x for x in r["links"] if x["campus_only"]]
    assert camp and all(x["vpn_url"].startswith("https://vpn.jlu.edu.cn/https/") for x in camp)
    assert all("vpn_url" not in x for x in r["links"] if not x["campus_only"])


def test_vpn_rewriter_missing_or_broken_is_tolerated(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "jlu_toolkit.campus", None)  # import 失败
    assert ui._vpn_rewriter() is None
    assert all("vpn_url" not in x for x in ui.campus_links_api(tmp_path / "n.json")["links"])

    def boom(u):
        raise ValueError("x")
    _fake_campus(monkeypatch, boom)
    assert all("vpn_url" not in x for x in ui.campus_links_api(tmp_path / "n.json")["links"])
    _fake_campus(monkeypatch, lambda u: "https://evil.example.com/")
    assert all("vpn_url" not in x for x in ui.campus_links_api(tmp_path / "n.json")["links"])


def test_override_vpn_url_wins(monkeypatch, tmp_path):
    _fake_campus(monkeypatch, lambda u: "https://vpn.jlu.edu.cn/https/aaaa/")
    o = tmp_path / "o.json"
    first = next(x for x in ui.campus_links_api(tmp_path / "n.json")["links"] if x["campus_only"])
    o.write_text(json.dumps({"links": [{"id": first["id"], "vpn_url": "https://vpn.jlu.edu.cn/https/bbbb/"}]}))
    got = next(x for x in ui.campus_links_api(o)["links"] if x["id"] == first["id"])
    assert got["vpn_url"] == "https://vpn.jlu.edu.cn/https/bbbb/"


def test_real_campus_vpn_url_if_present(tmp_path):
    fn = ui._vpn_rewriter()
    if fn is None:
        return  # #18 还没合进 base
    r = ui.campus_links_api(tmp_path / "n.json")
    for x in r["links"]:
        if x["campus_only"]:
            assert x["vpn_url"].startswith("https://vpn.jlu.edu.cn/")


def test_page_offline_ui():
    assert 'id="offl"' in PAGE
    assert "离线数据 · 更新于" in PAGE
    # 401 + offline 缓存时不抛错，直接返回缓存
    assert "j.offline===true&&j.ok!==false&&(r.ok||r.status===401))return j" in PAGE
    assert "经 WebVPN" in PAGE
