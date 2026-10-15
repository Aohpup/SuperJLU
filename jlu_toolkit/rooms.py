"""空教室查询（金智 EMAP「空闲教室查询」kxjscx 应用）。

用户确认：该功能可用，但必须带校区、空闲日期、空闲节次等条件；不带条件只会返回错误包。
吉大实际的接口名/字段名尚未确认，所以本模块：
  1. 先进入应用（GET kxjscx/*default/index.do，换取 _WEU）；
  2. 读取 EMAP 模块元数据（POST modules/<模块>.do，不带动作名），拿到动作 URL、
     查询字段名、字典 URL（校区/教学楼代码表）；
  3. 按「元数据推断」加若干常见金智参数方案依次尝试，第一个返回 datas.*.rows 的组合
     会保存为 rooms_profile.json，之后直接复用。
全部为只读查询。探测输出只含状态码/code/msg/字段名。
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional

from . import jwxt

APP = "https://iedu.jlu.edu.cn/jwapp/sys/kxjscx/*default/index.do"
BASE = "/jwapp/sys/kxjscx/modules/"
META_MODULES = ("kxjscx", "kxjs", "cxkxjs", "kxjas", "jscx")
ENDPOINTS = (
    BASE + "kxjscx/cxkxjs.do",
    BASE + "kxjscx/kxjscx.do",
    BASE + "kxjscx/cxkxjas.do",
    BASE + "kxjscx/jscx.do",
    BASE + "kxjs/cxkxjs.do",
)


@dataclass
class RoomQuery:
    campus: str
    date: str  # YYYY-MM-DD
    start: int
    end: int
    building: str = ""
    term: str = ""
    week: int = 0
    weekday: int = 0  # 1-7

    @property
    def jc_list(self) -> str:
        return ",".join(str(i) for i in range(self.start, self.end + 1))


@dataclass
class Room:
    name: str
    building: str = ""
    campus: str = ""
    seats: str = ""
    kind: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _s(v) -> str:
    return jwxt._emap_str(v)


def parse_periods_arg(s: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{1,2})\s*(?:-\s*(\d{1,2}))?\s*", s or "")
    if not m:
        raise ValueError("节次格式应为 3 或 3-4")
    a = int(m.group(1))
    b = int(m.group(2) or a)
    if not 1 <= a <= b <= 14:
        raise ValueError("节次范围应在 1-14 且起始 ≤ 结束")
    return a, b


def week_and_weekday(date: str, first_monday: Optional[str]) -> tuple[int, int]:
    d = dt.date.fromisoformat(date)
    if not first_monday:
        return 0, d.isoweekday()
    return (d - dt.date.fromisoformat(first_monday)).days // 7 + 1, d.isoweekday()


# ───────────────────────── EMAP 元数据 ─────────────────────────

_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,30}$")


def parse_meta(obj) -> dict:
    """从 EMAP 模块元数据里提取动作 URL、字段名、字段→字典 URL（全是代码，不含个人数据）。"""
    actions, fields, dicts = set(), set(), {}

    def walk(x, parent_name=None):
        if isinstance(x, dict):
            name = x.get("name")
            if isinstance(name, str) and _CODE.match(name):
                fields.add(name)
                for k in ("url", "dict", "dictUrl"):
                    u = x.get(k)
                    if isinstance(u, str) and ".do" in u and "code" in u.lower():
                        dicts[name] = u
            for k, v in x.items():
                if isinstance(v, str) and v.endswith(".do") and k in ("url", "action", "actionUrl"):
                    if "code" in v.lower() and isinstance(name, str):
                        dicts.setdefault(name, v)
                    else:
                        actions.add(v)
                walk(v, name)
        elif isinstance(x, list):
            for i in x:
                walk(i, parent_name)

    walk(obj)
    return {"actions": sorted(actions), "fields": sorted(fields), "dicts": dicts}


def fetch_meta(client) -> dict:
    merged = {"modules_ok": [], "actions": [], "fields": [], "dicts": {}}
    for m in META_MODULES:
        try:
            code, text, _ = client.post_raw(BASE + m + ".do", {}, APP)
        except jwxt.NetworkError:
            continue
        if code != 200:
            continue
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            continue
        meta = parse_meta(obj)
        if meta["actions"] or meta["fields"]:
            merged["modules_ok"].append(m)
            merged["actions"] = sorted(set(merged["actions"]) | set(meta["actions"]))
            merged["fields"] = sorted(set(merged["fields"]) | set(meta["fields"]))
            merged["dicts"].update(meta["dicts"])
    return merged


# ───────────────────────── 参数方案 ─────────────────────────

def _meta_scheme(fields: list[str]) -> Optional[Callable[[RoomQuery], dict]]:
    """按元数据字段名推断参数。"""
    f = set(fields)
    pick = lambda *cands: next((c for c in cands if c in f), None)  # noqa: E731
    campus = pick("XXXQDM", "XQDM", "XXXQ", "SZXQ")
    date = pick("KXRQ", "RQ", "CXRQ", "KXSJ")
    if not campus or not date:
        return None
    ks, js, jc = pick("KSJC", "QSJC"), pick("JSJC", "ZZJC"), pick("JC", "KXJC", "JCS")
    zc, xq = pick("ZC", "SKZC"), pick("XQJ", "SKXQ", "XQ")
    bld = pick("JXLDM", "JZWDM", "LH")

    def build(q: RoomQuery) -> dict:
        d = {campus: q.campus, date: q.date}
        if ks and js:
            d[ks], d[js] = str(q.start), str(q.end)
        if jc:
            d[jc] = q.jc_list
        if zc and q.week:
            d[zc] = str(q.week)
        if xq and xq != campus:
            d[xq] = str(q.weekday)
        if bld and q.building:
            d[bld] = q.building
        if "XNXQDM" in f and q.term:
            d["XNXQDM"] = q.term
        return d

    return build


def _qs(items: list[tuple[str, str]]) -> str:
    return json.dumps([{"name": k, "value": v, "linkOpt": "AND", "builder": "equal"} for k, v in items],
                      ensure_ascii=False)


SCHEMES: dict[str, Callable[[RoomQuery], dict]] = {
    "form_kxrq_ksjc": lambda q: {k: v for k, v in {
        "XXXQDM": q.campus, "KXRQ": q.date, "KSJC": str(q.start), "JSJC": str(q.end),
        "XNXQDM": q.term, "ZC": str(q.week or ""), "XQ": str(q.weekday), "JXLDM": q.building,
        "pageSize": "500", "pageNumber": "1"}.items() if v},
    "form_rq_jc": lambda q: {k: v for k, v in {
        "XXXQDM": q.campus, "RQ": q.date, "JC": q.jc_list, "XNXQDM": q.term,
        "ZC": str(q.week or ""), "XQJ": str(q.weekday), "JXLDM": q.building,
        "pageSize": "500", "pageNumber": "1"}.items() if v},
    "form_zc_xq": lambda q: {k: v for k, v in {
        "XXXQDM": q.campus, "XNXQDM": q.term, "ZC": str(q.week or ""), "XQ": str(q.weekday),
        "KSJC": str(q.start), "JSJC": str(q.end), "JXLDM": q.building,
        "pageSize": "500", "pageNumber": "1"}.items() if v},
    "querySetting": lambda q: {
        "querySetting": _qs([(k, v) for k, v in (("XXXQDM", q.campus), ("KXRQ", q.date),
                             ("KSJC", str(q.start)), ("JSJC", str(q.end)), ("JXLDM", q.building)) if v]),
        "XNXQDM": q.term, "pageSize": "500", "pageNumber": "1"},
    "requestParamStr": lambda q: {"requestParamStr": json.dumps({k: v for k, v in {
        "XXXQDM": q.campus, "KXRQ": q.date, "KSJC": str(q.start), "JSJC": str(q.end),
        "XNXQDM": q.term, "ZC": q.week or "", "XQ": q.weekday, "JXLDM": q.building}.items() if v},
        ensure_ascii=False)},
}


def _rows_any(obj) -> Optional[tuple[str, list]]:
    if not isinstance(obj, dict):
        return None
    for name, blk in (obj.get("datas") or {}).items():
        if isinstance(blk, dict) and isinstance(blk.get("rows"), list):
            return name, blk["rows"]
        if isinstance(blk, list):
            return name, blk
    return None


def row_to_room(r: dict) -> Optional[Room]:
    first = lambda *ks: next((_s(r.get(k)) for k in ks if _s(r.get(k))), "")  # noqa: E731
    name = first("JASMC", "JSMC", "MC", "JASDM")
    if not name:
        return None
    return Room(
        name=name,
        building=first("JXLDM_DISPLAY", "JXLMC", "JZWMC", "JXLDM"),
        campus=first("XXXQDM_DISPLAY", "XXXQMC", "XQMC"),
        seats=first("SKZWS", "ZWS", "KSZWS", "RNRS"),
        kind=first("JASLXDM_DISPLAY", "JASLXMC", "JSLXMC"),
    )


def _attempts(meta: dict, profile: Optional[dict]):
    actions = [a if a.startswith("/") else BASE + a.lstrip("./") for a in meta.get("actions", [])
               if re.search(r"(kx|cx|jscx)", a)]
    endpoints = list(dict.fromkeys(actions + list(ENDPOINTS)))
    schemes = dict(SCHEMES)
    ms = _meta_scheme(meta.get("fields", []))
    if ms:
        schemes = {"meta": ms, **schemes}
    if profile and profile.get("endpoint") in endpoints and profile.get("scheme") in schemes:
        yield profile["endpoint"], profile["scheme"], schemes[profile["scheme"]]
    for ep in endpoints:
        for name, fn in schemes.items():
            yield ep, name, fn


def query_rooms(client, q: RoomQuery, profile_path: Optional[Path] = None,
                meta: Optional[dict] = None, max_tries: int = 40) -> tuple[list[Room], dict]:
    """返回 (空教室列表, 命中的 profile)。全部失败则抛 JwxtError（附各尝试的 code/msg）。"""
    client.enter_emap_app(APP)
    meta = meta if meta is not None else fetch_meta(client)
    profile = None
    if profile_path and profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            profile = None
    errs = []
    for i, (ep, sname, fn) in enumerate(_attempts(meta, profile)):
        if i >= max_tries:
            break
        code, text, _ = client.post_raw(ep, fn(q), APP)
        if code != 200:
            errs.append(f"{ep.rsplit('/', 1)[-1]}/{sname}:HTTP{code}")
            continue
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            errs.append(f"{ep.rsplit('/', 1)[-1]}/{sname}:非JSON")
            continue
        hit = _rows_any(obj)
        if hit is None:
            msg = re.sub(r"\d{5,}", "#", _s(obj.get("msg")))[:40] if isinstance(obj, dict) else ""
            errs.append(f"{ep.rsplit('/', 1)[-1]}/{sname}:code={_s(obj.get('code')) if isinstance(obj, dict) else '?'} {msg}")
            continue
        prof = {"endpoint": ep, "scheme": sname, "datas_key": hit[0]}
        if profile_path:
            profile_path.write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        return [r for r in (row_to_room(x) for x in hit[1] if isinstance(x, dict)) if r], prof
    raise jwxt.JwxtError("空教室查询未成功；尝试：" + "；".join(errs[:12]))


def fetch_code_list(client, url: str, parent: dict | None = None) -> list[dict]:
    """EMAP 代码表 → [{code, name}]（校区/教学楼是公共信息）。"""
    path = url if url.startswith("/") else "/jwapp/" + url.lstrip("./")
    code, text, _ = client.post_raw(path, parent or {}, APP)
    if code != 200:
        return []
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    hit = _rows_any(obj)
    rows = hit[1] if hit else (obj if isinstance(obj, list) else [])
    out = []
    for r in rows:
        if isinstance(r, dict):
            c = _s(r.get("id") or r.get("DM") or r.get("code"))
            n = _s(r.get("name") or r.get("MC") or r.get("text"))
            if c:
                out.append({"code": c, "name": n or c})
    return out


def campus_codes_from_jc(client) -> list[str]:
    """兜底：节次时间表里的 XXXQ 就是校区代码。"""
    from . import meta as _m
    client.enter_emap_app(_m.APP_WDKB)
    data = _m._post(client, _m.EP_PERIODS, {}, _m.APP_WDKB)
    return sorted({_s(r.get("XXXQ")) for r in _m._rows(data, "jc") if _s(r.get("XXXQ"))})


def list_campuses(client, meta: Optional[dict] = None) -> list[dict]:
    client.enter_emap_app(APP)
    meta = meta if meta is not None else fetch_meta(client)
    for k in ("XXXQDM", "XQDM", "XXXQ"):
        if k in meta.get("dicts", {}):
            got = fetch_code_list(client, meta["dicts"][k])
            if got:
                return got
    return [{"code": c, "name": c} for c in campus_codes_from_jc(client)]


def list_buildings(client, campus: str = "", meta: Optional[dict] = None) -> list[dict]:
    client.enter_emap_app(APP)
    meta = meta if meta is not None else fetch_meta(client)
    for k in ("JXLDM", "JZWDM"):
        if k in meta.get("dicts", {}):
            return fetch_code_list(client, meta["dicts"][k], {"XXXQDM": campus} if campus else None)
    return []


# ───────────────────────── 探测（只打印结构） ─────────────────────────

def probe(client, first_monday: Optional[str], term: str, campuses: Optional[list[str]] = None,
          date: Optional[str] = None, periods: tuple[int, int] = (1, 2), log=print) -> dict:
    date = date or dt.date.today().isoformat()
    week, weekday = week_and_weekday(date, first_monday)
    rep: dict = {"date_is_today": date == dt.date.today().isoformat(), "week": week, "weekday": weekday,
                 "periods": list(periods)}
    try:
        client.enter_emap_app(APP)
        rep["entered"] = True
    except jwxt.JwxtError as e:
        rep["entered"] = f"{type(e).__name__}"
    meta = fetch_meta(client)
    rep["meta"] = {"modules_ok": meta["modules_ok"], "actions": meta["actions"], "fields": meta["fields"],
                   "dict_fields": sorted(meta["dicts"]), "dict_urls": sorted(set(meta["dicts"].values()))}
    log(f"[元数据] 模块={meta['modules_ok']} 动作={len(meta['actions'])} 字段={len(meta['fields'])}")
    if not campuses:
        try:
            cl = list_campuses(client, meta)
            campuses = [c["code"] for c in cl]
            rep["campus_source"] = "dict" if cl and cl[0]["name"] != cl[0]["code"] else "jc.XXXQ"
        except jwxt.JwxtError as e:
            rep["campus_source"] = f"error:{type(e).__name__}"
            campuses = []
    rep["campus_count"] = len(campuses)
    tries = []
    for camp in campuses[:3] or [""]:
        q = RoomQuery(campus=camp, date=date, start=periods[0], end=periods[1], term=term,
                      week=week, weekday=weekday)
        for ep, sname, fn in _attempts(meta, None):
            item = {"campus_idx": campuses.index(camp) if camp in campuses else -1,
                    "endpoint": ep, "scheme": sname, "param_names": sorted(fn(q))}
            try:
                code, text, _ = client.post_raw(ep, fn(q), APP)
                item["status"] = code
                obj = json.loads(text) if code == 200 and text else None
                if isinstance(obj, dict):
                    item["code"] = _s(obj.get("code"))[:6]
                    if isinstance(obj.get("msg"), str):
                        item["msg"] = re.sub(r"\d{5,}", "#", obj["msg"])[:60]
                    hit = _rows_any(obj)
                    if hit:
                        item["datas_key"], item["rows"] = hit[0], len(hit[1])
                        item["fields"] = sorted({k for r in hit[1][:20] if isinstance(r, dict) for k in r})
            except (json.JSONDecodeError, ValueError):
                item["non_json"] = True
            except jwxt.JwxtError as e:
                item["error"] = type(e).__name__
            tries.append(item)
            if "rows" in item:
                log(f"[命中] {ep} / {sname}: {item['rows']} 行")
                break
        if any("rows" in t for t in tries):
            break
    rep["tries"] = tries
    rep["hit"] = next(({"endpoint": t["endpoint"], "scheme": t["scheme"], "rows": t["rows"],
                        "fields": t["fields"]} for t in tries if "rows" in t), None)
    log(f"[空教室] 尝试 {len(tries)} 次，命中：{bool(rep['hit'])}")
    return rep
