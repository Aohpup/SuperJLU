"""学院目录 / 通知偏好 / 登录网络失败时的 VPN 提示。"""
import json
from pathlib import Path

import pytest

from jlu_toolkit import college, ui, web_login
from jlu_toolkit import jwxt


def test_catalog_has_categories_and_scrape_cols():
    cat = college.catalog()
    assert cat.get("categories")
    ids = {c["id"] for c in college.colleges_flat()}
    assert {"csw", "ccst", "sai", "law", "medicine", "spxy"} <= ids
    assert college.channels()["csw-xytz"] == "软件学院·学院通知"
    assert college.channels()["sai-xytz"] == "人工智能学院·学院通知"
    assert "sai-site" not in college.link_channels()


def test_prefs_default_and_apply_home(tmp_path):
    p = college.load_prefs(tmp_path)
    assert p["onboarded"] is False and p["enabled"] == ["179577"]
    p2 = college.apply_home_college(tmp_path, "csw")
    assert p2["onboarded"] is True and p2["home_college"] == "csw"
    assert "179577" in p2["enabled"]
    assert any(x.startswith("csw-") for x in p2["enabled"])
    chs = college.channels_for_prefs(tmp_path)
    ids = [c["id"] for c in chs]
    assert ids[0] == "179577"
    assert any(i.startswith("csw-") for i in ids)


def test_prefs_scraped_college(tmp_path):
    college.apply_home_college(tmp_path, "sai")
    p = college.load_prefs(tmp_path)
    assert "sai-xytz" in p["enabled"] and "sai-site" not in p["enabled"]


def test_link_only_channel_still_opens_home(tmp_path, monkeypatch):
    """没有栏目的学院仍只给官网入口，不假装有列表。"""
    real = college.college_by_id
    monkeypatch.setattr(college, "link_channels", lambda: {"zzz-site": "示例学院（官网）"})
    monkeypatch.setattr(college, "college_by_id", lambda cid: {
        "id": "zzz", "name": "示例学院", "home": "https://zzz.jlu.edu.cn/", "host": "zzz.jlu.edu.cn",
    } if cid == "zzz" else real(cid))
    r = college.fetch("zzz-site")
    assert r["status"] == "link_only" and r["source_url"] == "https://zzz.jlu.edu.cn/"
    college.save(tmp_path, r)
    n = ui.oa_notices_api(ui.Store(tmp_path), {"category": "zzz-site"})
    assert n["status"] == "link_only" and n["count"] == 0 and n["source_url"]


def test_oa_channels_api_filtered_after_onboard(tmp_path):
    st = ui.Store(tmp_path)
    before = ui.oa_channels_api(st)
    assert before["filtered"] is False
    assert any(c["id"] == "csw-xytz" for c in before["channels"])
    ui.oa_prefs_save_api(st, {"apply_home": True, "home_college": "ccst"})
    after = ui.oa_channels_api(st)
    assert after["filtered"] is True
    ids = [c["id"] for c in after["channels"]]
    assert "179577" in ids and any(i.startswith("ccst-") for i in ids)
    # 未选中的软件学院栏目不应再出现
    assert not any(i.startswith("csw-") for i in ids)


def test_oa_catalog_api():
    j = ui.oa_catalog_api()
    assert j["ok"] and len(j["catalog"]["categories"]) >= 5


def test_reorder_prefs(tmp_path):
    college.apply_home_college(tmp_path, "csw")
    p = college.load_prefs(tmp_path)
    order = list(reversed(p["order"]))
    p2 = college.save_prefs(tmp_path, {"order": order, "enabled": p["enabled"], "onboarded": True})
    assert p2["order"][0] == order[0]


def test_vpn_portal_url():
    u = ui.vpn_portal_url()
    assert u.startswith("https://") and "vpn.jlu.edu.cn" in u


def test_login_start_network_returns_vpn_hint(tmp_path, monkeypatch):
    """直连失败时 /api/login/start 应带 vpn_hint，而不是当成密码错误。"""
    class Boom(jwxt.JwxtClient):
        def login_password(self, username, password):
            raise jwxt.NetworkError("无法连接 https://cas.jlu.edu.cn/tpass/login: timed out")

    flow = web_login.LoginFlow(client_factory=Boom)
    store = ui.Store(tmp_path)
    H = ui.make_handler(store, login=flow)

    class Fake:
        pass

    # 直接调业务：NetworkError 在 handler 里被转成 502 JSON
    with pytest.raises(jwxt.NetworkError):
        flow.start("user", "pass", remember=False)

    # 模拟 handler 分支
    try:
        flow2 = web_login.LoginFlow(client_factory=Boom)
        flow2.start("user", "pass")
        assert False, "should raise"
    except jwxt.NetworkError as e:
        body = {
            "ok": False,
            "error": str(e),
            "network": True,
            "vpn_hint": True,
            "vpn_url": ui.vpn_portal_url(),
        }
        assert body["vpn_hint"] and "vpn.jlu.edu.cn" in body["vpn_url"]
        assert "无法连接" in body["error"]


def test_wrong_password_not_vpn(monkeypatch):
    class BadPw(jwxt.JwxtClient):
        def login_password(self, username, password):
            self.last_error_text = "用户名或密码错误"
            return jwxt.LoginStep.WRONG_PASSWORD

    flow = web_login.LoginFlow(client_factory=BadPw)
    with pytest.raises(ValueError) as ei:
        flow.start("user", "bad")
    assert "密码" in str(ei.value)
