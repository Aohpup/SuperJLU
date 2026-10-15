"""教务元数据：校历、节次时间、官方学分绩点、学业完成/培养方案。

字段名依据吉大 explore 报告（2026-10）与 Youwenqwq/ysu-sdk（同为金智 EMAP）：
  校历   wdkb/modules/xskcb/cxxljc.do   {XN, XQ}           → XQKSRQ, ZZC, ZJXZC
  节次   wdkb/modules/jshkcb/jc.do                         → DM/PX, MC, KSSJ, JSSJ, SFSY, XXXQ
  当前学期 wdkb/modules/jshkcb/dqxnxq.do                     → DM, QSSYRQ
  绩点   cjcx/modules/cjcx/cxzxfaxfjd.do  {XH1..XH6=学号}    → PPJDCX, PPJDZG, BXKPPJD, JQPJF ...
  培养方案 xsfacx/modules/pyfacxepg/grpyfacx.do               → PYFAMC, ZSYQXF, YWCXF, XH, PYFADM
  学业完成 xywccx/modules/xywccx/cxxsscfa.do  {SCLBDM=04}     → YQXF, WCXF, XKXF, JSSFTG, CZSJ
  课组明细 xywccx/modules/xywccx/cxscfakz.do {XH,PYFADM,BYNJDM,SCLBDM} → KZM, KZH, YQXF, WCXF, WCMS, SFTG
个人取值（学号等）只用于请求体，绝不写入日志或报告。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from typing import Optional

from . import jwxt

APP_WDKB = jwxt.REF_SCHEDULE
APP_CJCX = jwxt.REF_GRADES
APP_XSFACX = "https://iedu.jlu.edu.cn/jwapp/sys/xsfacx/*default/index.do"
APP_XYWCCX = "https://iedu.jlu.edu.cn/jwapp/sys/xywccx/*default/index.do"

EP_CALENDAR = "/jwapp/sys/wdkb/modules/xskcb/cxxljc.do"
EP_PERIODS = "/jwapp/sys/wdkb/modules/jshkcb/jc.do"
EP_GPA = "/jwapp/sys/cjcx/modules/cjcx/cxzxfaxfjd.do"
EP_PLAN = "/jwapp/sys/xsfacx/modules/pyfacxepg/grpyfacx.do"
EP_COMPLETION = "/jwapp/sys/xywccx/modules/xywccx/cxxsscfa.do"
EP_COMPLETION_GROUPS = "/jwapp/sys/xywccx/modules/xywccx/cxscfakz.do"

# 官方绩点字段 → 中文标签（ysu-sdk 同款金智字段）
GPA_FIELDS = [
    ("PPJDCX", "平均学分绩点（初修）"),
    ("PPJDZG", "平均学分绩点（最高）"),
    ("BXKPPJD", "必修课平均学分绩点"),
    ("XWKPJJDCX", "学位课绩点（初修）"),
    ("XWKPJJDZG", "学位课绩点（最高）"),
    ("JQPJF", "加权平均分"),
    ("SSPJF", "算术平均分"),
    ("XWKJQPJF", "学位课加权平均分"),
    ("BXKHDXF", "必修课已获学分"),
    ("XXKHDXF", "选修课已获学分"),
    ("XWKHDXF", "学位课已获学分"),
    ("BXKBJGXF", "必修课不及格学分"),
]


# ───────────────────────── 纯解析（可单测） ─────────────────────────

def _s(v) -> str:
    return jwxt._emap_str(v)


def _f(v) -> Optional[float]:
    try:
        return float(_s(v))
    except ValueError:
        return None


def _rows(data: dict, key: str) -> list:
    blk = (data.get("datas") or {}).get(key) or {}
    rows = blk.get("rows") if isinstance(blk, dict) else None
    return rows if isinstance(rows, list) else []


def norm_time(v) -> str:
    """'0800' / '8:00' / '08:00:00' / 800 → '08:00'；无法识别返回 ''。"""
    s = _s(v)
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", s)
    if not m and re.fullmatch(r"\d{3,4}", s):
        m = re.fullmatch(r"(\d{1,2})(\d{2})", s)
    if not m:
        return ""
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return ""
    return f"{h:02d}:{mi:02d}"


def _date(v) -> str:
    s = _s(v)
    m = re.match(r"(\d{4})[-/.]?(\d{1,2})[-/.]?(\d{1,2})", s)
    if not m:
        return ""
    try:
        return dt.date(*map(int, m.groups())).isoformat()
    except ValueError:
        return ""


def parse_calendar(row: dict, term: str = "") -> dict:
    start = _date(row.get("XQKSRQ"))
    first_monday = ""
    if start:
        d = dt.date.fromisoformat(start)
        first_monday = (d - dt.timedelta(days=d.weekday())).isoformat()
    xn, xq = _s(row.get("XN")), _s(row.get("XQ"))
    return {
        "term": term or (f"{xn}-{xq}" if xn and xq else ""),
        "start_date": start,
        "first_monday": first_monday,
        "total_weeks": int(_f(row.get("ZZC")) or 0),
        "teaching_weeks": int(_f(row.get("ZJXZC")) or 0),
    }


def parse_periods(rows: list) -> dict:
    """→ {"1": ["08:00","08:45"], ...}。多校区时取出现最多的 XXXQ；跳过 SFSY=0。"""
    usable = [r for r in rows if _s(r.get("SFSY")) not in ("0", "否", "false")]
    camp = Counter(_s(r.get("XXXQ")) for r in usable).most_common(1)
    if camp:
        usable = [r for r in usable if _s(r.get("XXXQ")) == camp[0][0]]
    out: dict = {}
    for r in usable:
        sec = _f(r.get("DM")) or _f(r.get("PX")) or _f(re.sub(r"\D", "", _s(r.get("MC"))) or None)
        a, b = norm_time(r.get("KSSJ")), norm_time(r.get("JSSJ"))
        if sec and a and b:
            out.setdefault(str(int(sec)), [a, b])
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def parse_official_gpa(row: dict) -> dict:
    items = []
    for k, label in GPA_FIELDS:
        v = _s(row.get(k))
        if v:
            items.append({"key": k, "label": label, "value": v})
    return {"plan": _s(row.get("PYFAMC")), "items": items}


def parse_completion(summary: dict, plan: dict, groups: list) -> dict:
    gs = []
    for g in groups:
        req, done = _f(g.get("YQXF")), _f(g.get("WCXF"))
        missing = max(0.0, (req or 0) - (done or 0)) if req is not None else None
        passed = _s(g.get("SFTG")) in ("1", "是", "true", "通过")
        gs.append({
            "name": _s(g.get("KZM")) or _s(g.get("KCXZDM_DISPLAY")) or "未命名课组",
            "code": _s(g.get("KZH")),
            "parent": _s(g.get("FKZH")),
            "nature": _s(g.get("KCXZDM_DISPLAY")),
            "required": req,
            "earned": done,
            "courses_done": int(_f(g.get("WCMS")) or 0),
            "passed": passed,
            "missing": round(missing, 2) if missing is not None else None,
        })
    req = _f(summary.get("YQXF")) or _f(plan.get("ZSYQXF"))
    done = _f(summary.get("WCXF")) or _f(plan.get("YWCXF"))
    return {
        "plan": _s(summary.get("PYFAMC")) or _s(plan.get("PYFAMC")),
        "required": req,
        "earned": done,
        "selected": _f(summary.get("XKXF")),
        "missing": round(max(0.0, req - (done or 0)), 2) if req is not None else None,
        "passed": _s(summary.get("JSSFTG") or summary.get("ZSSFTG")) in ("1", "是", "true", "通过"),
        "calculated_at": _s(summary.get("CZSJ")),
        "groups": sorted(gs, key=lambda g: (g["passed"], -(g["missing"] or 0))),
    }


# ───────────────────────── 网络（需会话） ─────────────────────────

def _post(client: "jwxt.JwxtClient", path: str, fields: dict, app: str) -> dict:
    code, text, _ = client.post_raw(path, fields, app)
    if code != 200:
        raise jwxt.JwxtError(f"{path} HTTP {code}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        if "loginForm" in text:
            raise jwxt.LoginError("会话已失效，请重新登录") from e
        raise jwxt.JwxtError(f"{path} 返回非 JSON") from e


def fetch_calendar(client, term: Optional[str] = None) -> dict:
    term = term or client.current_semester() or ""
    xn, _, xq = term.rpartition("-")
    client.enter_emap_app(APP_WDKB)
    rows = _rows(_post(client, EP_CALENDAR, {"XN": xn, "XQ": xq}, APP_WDKB), "cxxljc")
    if not rows:
        raise jwxt.JwxtError("校历为空")
    cal = parse_calendar(rows[0], term)
    if not cal["first_monday"]:
        raise jwxt.JwxtError("校历缺少学期开始日期 XQKSRQ")
    return cal


def fetch_periods(client) -> dict:
    client.enter_emap_app(APP_WDKB)
    p = parse_periods(_rows(_post(client, EP_PERIODS, {}, APP_WDKB), "jc"))
    if not p:
        raise jwxt.JwxtError("节次时间为空或格式无法识别")
    return p


def _plan_row(client) -> dict:
    client.enter_emap_app(APP_XSFACX)
    rows = _rows(_post(client, EP_PLAN, {}, APP_XSFACX), "grpyfacx")
    return rows[0] if rows else {}


def fetch_official_gpa(client, xh: Optional[str] = None) -> dict:
    xh = xh or _s(_plan_row(client).get("XH"))
    if not xh:
        raise jwxt.JwxtError("无法取得学号（培养方案接口无 XH）")
    client.enter_emap_app(APP_CJCX)
    data = _post(client, EP_GPA, {f"XH{i}": xh for i in range(1, 7)}, APP_CJCX)
    rows = _rows(data, "cxzxfaxfjd")
    if not rows:
        raise jwxt.JwxtError("学分绩点统计为空")
    return parse_official_gpa(rows[0])


def fetch_completion(client) -> dict:
    plan = _plan_row(client)
    client.enter_emap_app(APP_XYWCCX)
    rows = _rows(_post(client, EP_COMPLETION, {"SCLBDM": "04", "*order": "-CZSJ"}, APP_XYWCCX), "cxxsscfa")
    summary = rows[0] if rows else {}
    groups: list = []
    if summary:
        try:
            groups = _rows(_post(client, EP_COMPLETION_GROUPS, {
                "XH": _s(summary.get("XH") or plan.get("XH")),
                "PYFADM": _s(summary.get("PYFADM") or plan.get("PYFADM")),
                "BYNJDM": _s(summary.get("BYNJDM")) or "-",
                "SCLBDM": _s(summary.get("SCLBDM")) or "04",
            }, APP_XYWCCX), "cxscfakz")
        except jwxt.JwxtError:
            groups = []
    if not summary and not plan:
        raise jwxt.JwxtError("学业完成与培养方案均为空")
    return parse_completion(summary, plan, groups)
