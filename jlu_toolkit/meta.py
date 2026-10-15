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
import re
from typing import Optional

from . import jwxt

APP_WDKB = jwxt.REF_SCHEDULE
APP_CJCX = jwxt.REF_GRADES
APP_XSFACX = "https://iedu.jlu.edu.cn/jwapp/sys/xsfacx/*default/index.do"
APP_XYWCCX = "https://iedu.jlu.edu.cn/jwapp/sys/xywccx/*default/index.do"

EP_CALENDAR = "/jwapp/sys/wdkb/modules/xskcb/cxxljc.do"
EP_PERIODS = "/jwapp/sys/wdkb/modules/jshkcb/jc.do"
EP_GPA = "/jwapp/sys/cjcx/modules/cjcx/cxzxfaxfjd.do"
# 吉大实测 cxzxfaxfjd 返回 {"code":"404"}；依次尝试候选（探测用，均为只读查询）
GPA_CANDIDATES = [
    (EP_GPA, "XH1..6"),
    (EP_GPA, "XH"),
    ("/jwapp/sys/cjcx/modules/cjcx/cxxsjdtj.do", "XH"),
    ("/jwapp/sys/cjcx/modules/cjcx/cxpjxfjd.do", "XH"),
    ("/jwapp/sys/cjcx/modules/cjcx/xspjxfjd.do", "XH"),
]
EP_PLAN_COURSES = "/jwapp/sys/jwpubapp/modules/pyfa/kzkccx.do"


class Unavailable(jwxt.JwxtError):
    """接口在吉大不存在/无数据：不是故障。"""
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
        missing = max(0.0, req - done) if req is not None and done is not None else None
        passed = _s(g.get("SFTG")) in ("1", "是", "true", "通过")
        gs.append({
            "name": _s(g.get("KZM")) or _s(g.get("KCXZDM_DISPLAY")) or "未命名课组",
            "code": _s(g.get("KZH")),
            "parent": _s(g.get("FKZH")),
            "nature": _s(g.get("KCXZDM_DISPLAY")),
            "required": req,
            "earned": done,
            "courses_done": int(_f(g.get("WCMS")) or 0),
            "earned_source": "jw" if done is not None else None,
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


def _passed(score: str) -> bool:
    from . import core
    s = (score or "").strip()
    if s in ("通过", "合格"):
        return True
    p = core.score_to_point(s) if s else None
    return bool(p and p > 0)


def derive_group_earned(completion: dict, plan_courses: list, grades) -> dict:
    """教务课组无 WCXF 时：按「培养方案课程 → 课组」映射 + 已通过成绩推算各课组已获学分。

    课程按课程名匹配（成绩 CSV 无课程号）；父课组（FKZH）汇总子课组。
    """
    passed: dict = {}
    for g in grades or []:
        if _passed(g.score):
            passed[g.name.strip()] = max(passed.get(g.name.strip(), 0.0), float(g.credit))
    direct: dict = {}
    seen: set = set()
    for c in plan_courses:
        kzh, name = _s(c.get("KZH")), _s(c.get("KCM"))
        if not kzh or not name or (kzh, name) in seen:
            continue
        seen.add((kzh, name))
        if name in passed:
            direct[kzh] = direct.get(kzh, 0.0) + passed[name]
    groups = completion.get("groups") or []
    children: dict = {}
    for g in groups:
        if g.get("parent"):
            children.setdefault(g["parent"], []).append(g["code"])

    memo: dict = {}

    def total(code, depth=0):
        if code in memo:
            return memo[code]
        v = direct.get(code, 0.0)
        if depth < 10:
            v += sum(total(ch, depth + 1) for ch in children.get(code, []))
        memo[code] = v
        return v

    changed = 0
    for g in groups:
        if g.get("earned") is None and g.get("code"):
            g["earned"] = round(total(g["code"]), 2)
            g["earned_source"] = "derived"
            if g.get("required") is not None:
                g["missing"] = round(max(0.0, g["required"] - g["earned"]), 2)
                g["passed"] = g["missing"] == 0
            changed += 1
    completion["groups"] = sorted(groups, key=lambda g: (g["passed"], -(g["missing"] or 0)))
    completion["groups_derived"] = changed
    return completion


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


def gpa_from_jw_points(grades) -> Optional[dict]:
    """用教务返回的单科绩点按学分加权（与自算公式无关）。无教务绩点则 None。"""
    tot = pts = 0.0
    n = 0
    for g in grades or []:
        jp = getattr(g, "jw_point", None)
        if jp is None or not g.credit:
            continue
        tot += g.credit
        pts += jp * g.credit
        n += 1
    if not n:
        return None
    return {"plan": "", "source": "grades_jw_point",
            "items": [{"key": "JW_WEIGHTED", "label": "教务单科绩点学分加权（全部课程）",
                       "value": f"{pts / tot:.3f}"},
                      {"key": "JW_COUNT", "label": "含教务绩点的课程数", "value": str(n)}]}


GPA_ACTION_HINT = re.compile(r"(xfjd|pjxfjd|pjxf|jqpjf|sspjf|gpa|jdtj|xftj|cxzxfa|cxpj|xspj)", re.I)


def _xh_fields(xh: str, fields: list[str]) -> dict:
    f = set(fields)
    if any(k.startswith("XH") and k[2:].isdigit() for k in f):
        return {k: xh for k in f if k.startswith("XH")}
    if "XH" in f:
        return {"XH": xh}
    if any(k.startswith("XH") for k in f):
        return {k: xh for k in f if k.startswith("XH")}
    return {f"XH{i}": xh for i in range(1, 7)} | {"XH": xh}


def _gpaish(name: str, url: str, fields: list[str]) -> bool:
    blob = f"{name} {url} {' '.join(fields)}"
    return bool(GPA_ACTION_HINT.search(blob))


def probe_gpa(client, log=print) -> dict:
    """扫描 cjcx 应用：动作/字段名列表 + 绩点候选试调用结果（无个人数值）。"""
    from . import emap
    app = emap.App("cjcx", "cjcx")
    report = emap.explore_app(client, app)
    actions = []
    for m, info in report["meta"].items():
        for a in info["actions"]:
            url = app.abs(a["url"])
            actions.append({"module": m, "name": a["name"], "url": url, "fields": a["fields"],
                            "gpaish": _gpaish(a["name"], url, a["fields"])})
    for u in report["action_urls"]:
        if not any(a["url"] == u for a in actions):
            actions.append({"module": "", "name": "", "url": u, "fields": [],
                            "gpaish": _gpaish("", u, [])})
    report["actions"] = actions
    candidates = [a for a in actions if a["gpaish"]] + [
        {"module": "guess", "name": n, "url": p, "fields": [], "gpaish": True}
        for p, n in [(p, p.rsplit("/", 1)[-1]) for p, _ in GPA_CANDIDATES]
        if not any(a["url"] == p for a in actions)]
    # 去重
    seen, uniq = set(), []
    for a in candidates:
        if a["url"] not in seen:
            seen.add(a["url"]); uniq.append(a)
    xh = _s(_plan_row(client).get("XH"))
    report["has_xh"] = bool(xh)
    tries = []
    for a in uniq:
        fields = _xh_fields(xh, a["fields"]) if xh else {}
        item = {"url": a["url"], "name": a["name"], "param_names": sorted(fields)}
        try:
            code, text, _ = client.post_raw(a["url"], fields, APP_CJCX)
            item["status"] = code
            obj = json.loads(text) if text else {}
            item["code"] = _s(obj.get("code"))[:8]
            if isinstance(obj.get("msg"), str):
                item["msg"] = re.sub(r"\d{5,}", "#", obj["msg"])[:60]
            for name, blk in (obj.get("datas") or {}).items():
                if isinstance(blk, dict) and isinstance(blk.get("rows"), list) and blk["rows"]:
                    row = blk["rows"][0]
                    item["datas_key"] = name
                    item["fields"] = sorted(row.keys()) if isinstance(row, dict) else []
                    item["matched_labels"] = [k for k, _ in GPA_FIELDS if isinstance(row, dict) and k in row]
                    break
                if isinstance(blk, dict) and any(k in blk for k, _ in GPA_FIELDS):
                    item["datas_key"] = name
                    item["fields"] = sorted(blk.keys())
                    item["matched_labels"] = [k for k, _ in GPA_FIELDS if k in blk]
                    break
        except (json.JSONDecodeError, ValueError):
            item["non_json"] = True
        except jwxt.JwxtError as e:
            item["error"] = type(e).__name__
        tries.append(item)
        log(f"[绩点] {a['url'].rsplit('/',1)[-1]} → status={item.get('status')} code={item.get('code')} match={item.get('matched_labels')}")
    report["tries"] = tries
    report["hit"] = next(({"url": t["url"], "matched_labels": t["matched_labels"], "datas_key": t.get("datas_key")}
                          for t in tries if t.get("matched_labels")), None)
    # 脱敏：去掉可能含学号的请求体
    return {k: report[k] for k in ("discover", "meta", "meta_trace", "actions", "tries", "hit", "has_xh")}


def _call_gpa_action(client, url: str, fields: list[str], xh: str) -> Optional[dict]:
    data = _post(client, url, _xh_fields(xh, fields), APP_CJCX)
    for blk in (data.get("datas") or {}).values():
        if isinstance(blk, dict) and isinstance(blk.get("rows"), list) and blk["rows"]:
            g = parse_official_gpa(blk["rows"][0])
            if g["items"]:
                g["source"] = "official"
                g["endpoint"] = url
                return g
        if isinstance(blk, dict):
            g = parse_official_gpa(blk)
            if g["items"]:
                g["source"] = "official"
                g["endpoint"] = url
                return g
    return None


def fetch_official_gpa(client, xh: Optional[str] = None, grades=None) -> dict:
    from . import emap
    tried = []
    xh = xh or _s(_plan_row(client).get("XH"))
    client.enter_emap_app(APP_CJCX)
    app = emap.App("cjcx", "cjcx")
    try:
        disc = emap.discover(client, app)
        mm = emap.module_meta(client, app, disc.get("modules_seen", ["cjcx"]))
        candidates = []
        for m, info in mm["modules"].items():
            for a in info["actions"]:
                url = app.abs(a["url"])
                if _gpaish(a["name"], url, a["fields"]):
                    candidates.append((url, a["fields"]))
        for path, _ in GPA_CANDIDATES:
            if path not in {u for u, _ in candidates}:
                candidates.append((path, []))
        if xh:
            for url, fields in candidates:
                try:
                    g = _call_gpa_action(client, url, fields, xh)
                    if g:
                        return g
                    tried.append(f"{url.rsplit('/',1)[-1]}:empty")
                except jwxt.LoginError:
                    raise
                except jwxt.JwxtError as e:
                    tried.append(f"{url.rsplit('/',1)[-1]}:{str(e)[-12:]}")
    except jwxt.LoginError:
        raise
    except jwxt.JwxtError as e:
        tried.append(f"discover:{type(e).__name__}")
    alt = gpa_from_jw_points(grades)
    if alt:
        return alt
    raise Unavailable("未找到可用的官方绩点接口（已尝试：" + "; ".join(tried[:8]) + "）")


def fetch_plan_courses(client, pyfadm: str, page_size: int = 500) -> list:
    out: list = []
    for page in range(1, 6):
        data = _post(client, EP_PLAN_COURSES, {"PYFADM": pyfadm, "pageSize": str(page_size),
                                               "pageNumber": str(page)}, APP_XSFACX)
        rows = _rows(data, "kzkccx")
        out += rows
        total = ((data.get("datas") or {}).get("kzkccx") or {}).get("totalSize") or 0
        if not rows or len(out) >= int(total or 0):
            break
    return out


def fetch_completion(client, grades=None) -> dict:
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
    comp = parse_completion(summary, plan, groups)
    if grades is not None and any(g["earned"] is None for g in comp["groups"]):
        pyfadm = _s(summary.get("PYFADM") or plan.get("PYFADM"))
        if pyfadm:
            try:
                client.enter_emap_app(APP_XSFACX)
                comp = derive_group_earned(comp, fetch_plan_courses(client, pyfadm), grades)
            except jwxt.LoginError:
                raise
            except jwxt.JwxtError:
                pass
    return comp
