"""学院新闻（csw 软件学院 / ccst 计算机学院）：解析 + 缓存 + UI 接口，全部用离线 fixture。"""
from pathlib import Path

from jlu_toolkit import college, oa_subscribe, ui

FX = Path(__file__).parent / "fixtures" / "college"


def test_channels_named():
    ch = college.channels()
    assert ch["csw-xytz"] == "软件学院·学院通知"
    assert ch["ccst-xyxw"] == "计算机学院·学院新闻"


def test_parse_csw():
    items = college.parse_list((FX / "csw_xytz.html").read_text(encoding="utf-8"), "csw-xytz")
    assert len(items) == 15
    i = items[0]
    assert i["url"].startswith("https://csw.jlu.edu.cn/info/") and i["time"].count("-") == 2
    assert i["title"] and i["id"].startswith("csw-xytz:")
    assert all(x["url"].startswith("https://csw.jlu.edu.cn/") for x in items)


def test_parse_ccst():
    items = college.parse_list((FX / "ccst_xytz.html").read_text(encoding="utf-8"), "ccst-xytz")
    assert len(items) == 10 and items[0]["time"] == "2026-09-16"
    assert items[0]["url"] == "https://ccst.jlu.edu.cn/info/1091/21181.htm"


def test_parse_hospital_pages():
    divli = ('<div class="li"><a href="/wujia_detail_g7yU_62/206646.html" target="_blank">'
             '<div class="p">部门决算</div><div class="y">2026.08.10</div></a></div>')
    items = college.parse_list(divli, "zrlyyy-tzgg")
    assert items[0]["title"] == "部门决算" and items[0]["time"] == "2026-08-10"
    assert items[0]["url"] == "https://www.zrlyyy.com/wujia_detail_g7yU_62/206646.html"
    content = ('<a href="/xwzx3/xwdt2/content_105636.html">骨科年会</a><span>2026-10-21</span>'
               '<a href="/tzgg23/rczp/content_9.html">招聘</a>')
    items = college.parse_list(content, "jdey-xwdt")
    assert [i["title"] for i in items] == ["骨科年会"] and items[0]["time"] == "2026-10-21"
    eyou = ('<li><a href="/index.php?m=home&c=View&a=index&aid=82415">巡视公告</a>'
            '<span style="color:#666">2026-10-21</span></li>'
            '<a href="/index.php?m=home&c=View&a=index&aid=1">查看详情</a>'
            '<a href="/index.php?m=home&c=View&a=index&aid=82415">巡视公告</a>')
    items = college.parse_list(eyou, "jdyy-kx")
    assert len(items) == 1 and items[0]["title"] == "巡视公告" and items[0]["time"] == "2026-10-21"
    assert "aid=82415" in items[0]["url"] and items[0]["url"].startswith("https://www.jdyy.cn/")


def test_structured_titles_drop_index_date_and_summary():
    dce = ('<li><span>2026-10-19</span><a href="../info/1032/11473.htm">'
           '<strong>1</strong>关于公示研究生学业奖学金的通知</a></li>')
    items = college.parse_list(dce, "dce-tzgg")
    assert items[0]["title"] == "关于公示研究生学业奖学金的通知"
    assert items[0]["time"] == "2026-10-19"
    phy = ('<li><a href="../info/1052/7267.htm"><div class="tl-date"><b>10</b>'
           '<span> / 2026-10</span></div><h3>第十四届CALYPSO研讨会</h3></a></li>')
    items = college.parse_list(phy, "phy-tzgg")
    assert items[0]["title"] == "第十四届CALYPSO研讨会" and items[0]["time"] == "2026-10-10"
    spxy = ('<li><a href="info/1044/4209.htm"><div class="date1"><p>19</p><p>2026.10</p></div>'
            '<p class="title tt1">孵新奖学金评审结果公示</p>'
            '<p class="info tt1">根据办法现将名单公示。2026年1月2日截止。</p></a></li>')
    items = college.parse_list(spxy, "spxy-tztg")
    assert items[0]["title"] == "孵新奖学金评审结果公示" and items[0]["time"] == "2026-10-19"
    jdey = ('<a href="/tzgg23/tzgg4/content_105527.html"><strong>29</strong>2026-09'
            '<span class="tit">拟报废资产评估项目公示</span>'
            '<div>此次报废。2026年9月21日开会。</div><span>探索更多</span></a>')
    items = college.parse_list(jdey, "jdey-gsgg")
    assert items[0]["title"] == "拟报废资产评估项目公示" and items[0]["time"] == "2026-09-29"
    xw = '<a href="/xwzx3/xwdt2/content_1.html">解码&nbsp;路径</a><span>2026-10-21</span>'
    items = college.parse_list(xw, "jdey-xwdt")
    assert items[0]["title"] == "解码 路径" and items[0]["time"] == "2026-10-21"


def test_offsite_links_dropped():
    html = ('<ul><li><span>2026-01-02</span><a href="https://evil.example/info/1/2.htm" title="x">x</a></li>'
            '<li><span>2026-01-03</span><a href="../info/9/8.htm" title="好">好</a></li></ul>')
    items = college.parse_list(html, "csw-xytz")
    assert [i["title"] for i in items] == ["好"]


def test_unreachable_preserves_cache_without_assuming_campus_requirement(tmp_path):
    def boom(url):
        raise TimeoutError("t")
    r = college.fetch("ccst-xytz", getter=boom)
    assert r["ok"] is False and r["status"] == "network_error" and "本地通知" in r["hint"]
    college.save(tmp_path, r)
    s = ui.oa_notices_api(ui.Store(tmp_path), {"category": "ccst-xytz"})
    assert s["status"] == "network_error" and s["count"] == 0


def test_ui_api(tmp_path):
    html = (FX / "csw_xytz.html").read_text(encoding="utf-8")
    college.save(tmp_path, college.fetch("csw-xytz", getter=lambda u: html))
    st = ui.Store(tmp_path)
    chs = {c["id"]: c["name"] for c in ui.oa_channels_api(st)["channels"]}
    assert "179577" in chs and chs["ccst-xytz"] == "计算机学院·学院通知"
    r = ui.oa_notices_api(st, {"category": "csw-xytz", "keyword": "蓝桥杯"})
    assert r["count"] == 1 and r["source"] == "college"
    d = ui.oa_notice_api(st, r["items"][0]["id"])
    assert d["item"]["url"].startswith("https://csw.jlu.edu.cn/") and d["item"]["source"] == "college"


def test_subscription_on_college(tmp_path, monkeypatch):
    html = (FX / "csw_xytz.html").read_text(encoding="utf-8")
    monkeypatch.setattr(college, "_get", lambda u, timeout=10: html)
    rule = oa_subscribe.add_rule("蓝桥杯", channel="csw-xytz", root=tmp_path)
    first = oa_subscribe.sync(None, "csw-xytz", tmp_path)
    assert first["first_run"] and first["fetched"] == 15
    monkeypatch.setattr(college, "_get", lambda u, timeout=10: html.replace("8077.htm", "9999.htm"))
    res = oa_subscribe.sync(None, "csw-xytz", tmp_path)
    hits = oa_subscribe.record_matches(res["new"], tmp_path)
    assert len(hits) == 1 and hits[0]["rule_id"] == rule["id"]


def test_channel_order_college_before_hospitals(tmp_path):
    import json
    from jlu_toolkit import ui, college
    d = tmp_path
    (d / "oa_channels.json").write_text(json.dumps({"1": "第二医院", "2": "教务通知", "3": "第一医院", "4": "动科"}, ensure_ascii=False), encoding="utf-8")
    st = ui.Store(tmp_path)
    names = [c["name"] for c in ui.oa_channels_api(st)["channels"]]
    cn = list(college.channels().values())
    i = names.index(cn[0])
    assert names[:i] == ["校内通知", "教务通知"]
    assert names[i:i + len(cn)] == cn
    assert names[i + len(cn):] == ["第二医院", "第一医院", "动科"]
