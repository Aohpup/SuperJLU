"""培养方案课程明细（xsfacx / xywccx 等）：EMAP 发现 → 元数据（含标题）→ 调用动作（先不带 XH）。

产出 data/plan_courses.json：每门课 课程号/课程名/学分/学时/性质/类别/建议修读学期/开课单位/课组/状态/成绩。
--probe 只输出 应用/模块/动作名、字段名+标题、行数，不含任何值。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from . import emap, jwxt

APPS = (("xsfacx", "ckgrpyfa"), ("xsfacx", "xsfacx"), ("xywccx", "xywccx"), ("pyfacx", "pyfacx"), ("facx", "facx"),
        ("kcxx", "kcxx"), ("jwpubapp", "pyfa"))
# 已知的候选（发现失败时兜底）
KNOWN = (
    ("xsfacx", "modules/ckgrpyfa/cxkzxx.do"), ("xsfacx", "modules/ckgrpyfa/cxpyfakz.do"),
    ("xsfacx", "modules/ckgrpyfa/kzkccx.do"), ("xsfacx", "modules/pyfacxepg/cxpyfakz.do"),
    ("xsfacx", "modules/pyfacxepg/kzkccx.do"), ("xsfacx", "modules/pyfacxepg/cxfakc.do"),
    ("xsfacx", "modules/pyfacxepg/grpyfakccx.do"), ("xsfacx", "modules/pyfacxepg/pyfakccx.do"),
    ("xywccx", "modules/xywccx/cxscfakzkc.do"), ("xywccx", "modules/xywccx/cxxsscfakc.do"),
    ("xywccx", "modules/xywccx/cxkzkc.do"), ("jwpubapp", "modules/pyfa/kzkccx.do"),
)
_HINT = re.compile(r"(kc|kz|fa|wc|xx|cx)", re.I)
_SKIP = re.compile(r"(save|add|del|update|xg|bc|sc[a-z]*sq|tj[a-z]*sq|submit|export|dc)", re.I)
MAX_TOTAL = 2000  # 超过即视为未过滤（全校数据），拒绝且绝不翻页
COURSE_KEYS = ("KCH", "KCM", "KCDM", "KCMC")
DONE_KEYS = ("ZCJ", "CJ", "XSZCJMC", "SFTG", "TGZT", "XDZT", "XDZTDM", "WCZT", "SFXD", "SFWC", "CJDM")

# 字段 → (候选键, 标题关键词)
COLS = {
    "code": (("KCH", "KCDM"), ("课程号", "课程代码")),
    "name": (("KCM", "KCMC"), ("课程名",)),
    "credit": (("XF", "KCXF"), ("学分",)),
    "hours": (("XS", "ZXS", "KCZXS"), ("学时",)),
    "nature": (("KCXZDM", "KCXZ"), ("课程性质",)),
    "category": (("KCLBDM", "KCLB"), ("课程类别",)),
    "term": (("XNXQDM", "XNXQ", "JYXDXQ", "XDXQ", "JYXDXNXQ", "KKXQ"), ("学年学期", "建议修读", "修读学期", "开课学期")),
    "exam_type": (("KSLXDM", "KSLX"), ("考试类型",)),
    "dept": (("KKDWDM", "KKYXDM", "KKDW"), ("开课单位", "开课院系", "开课学院")),
    "group": (("KZM", "KZMC"), ("课组", "所属课组")),
    "group_code": (("KZH", "KZDM"), ()),
    "score": (("ZCJ", "CJ", "XSZCJMC", "ZZCJ", "ZSCJ"), ("成绩",)),
    "selected": (("SFXK",), ("是否选课",)),
    "sub_rd": (("RDKCH",), ()),
    "sub_td": (("TDKCH",), ()),
    "status_raw": (("XDZTDM", "XDZT", "WCZT", "TGZT", "SFTG", "SFWC", "SFXD"), ("修读状态", "完成", "是否通过", "是否已修")),
}


def _s(v) -> str:
    return jwxt._emap_str(v)


def _rows_any(obj):
    if not isinstance(obj, dict):
        return None
    d = obj.get("datas")
    if isinstance(d, dict):
        for k, blk in d.items():
            if isinstance(blk, dict) and isinstance(blk.get("rows"), list):
                return k, blk["rows"], blk.get("totalSize")
            if isinstance(blk, list):
                return k, blk, None
    if isinstance(d, list):
        return "datas", d, None
    return None


def _post(client, app: emap.App, path: str, form: dict):
    try:
        code, text, _ = client.post_raw(path, form, app.index + "?EMAP_LANG=zh")
    except jwxt.NetworkError:
        return None, None
    try:
        return code, json.loads(text) if text else None
    except (json.JSONDecodeError, ValueError):
        return code, None


def _variants(ctx: dict, path: str = ""):
    base = {"pageSize": "10", "pageNumber": "1"}
    if ctx.get("PYFADM"):
        yield "page+qsPYFADM", {**base, "querySetting": json.dumps(
            [{"name": "PYFADM", "value": ctx["PYFADM"], "linkOpt": "AND", "builder": "equal"}])}
    if "kzkccx" not in path:  # 全校方案课程表：绝不无过滤调用
        yield "page", dict(base)
    if ctx.get("PYFADM"):
        yield "page+PYFADM", {**base, "PYFADM": ctx["PYFADM"]}
    if ctx.get("XH"):
        yield "page+XH", {**base, "XH": ctx["XH"]}
    if ctx.get("XH") and ctx.get("PYFADM"):
        yield "page+XH+PYFADM", {**base, "XH": ctx["XH"], "PYFADM": ctx["PYFADM"],
                                 "BYNJDM": ctx.get("BYNJDM", "-"), "SCLBDM": ctx.get("SCLBDM", "04")}


def _context(client) -> dict:
    """内存中的 XH/PYFADM（从方案/学业完成取，绝不写入报告）。"""
    from . import meta
    ctx: dict = {}
    try:
        p = meta._plan_row(client)
        ctx.update({k: _s(p.get(k)) for k in ("XH", "PYFADM") if _s(p.get(k))})
    except jwxt.JwxtError:
        pass
    try:
        client.enter_emap_app(meta.APP_XYWCCX)
        for act in ("cxxsjbxx", "cxscfa"):
            obj = meta._post(client, f"/jwapp/sys/xywccx/modules/xywccx/{act}.do",
                             {"pageSize": "10", "pageNumber": "1"}, meta.APP_XYWCCX)
            hit = _rows_any(obj)
            if hit and hit[1] and isinstance(hit[1][0], dict):
                for k in ("XH", "PYFADM", "BYNJDM", "SCLBDM"):
                    if _s(hit[1][0].get(k)):
                        ctx.setdefault(k, _s(hit[1][0].get(k)))
    except jwxt.JwxtError:
        pass
    try:
        rows = meta._rows(meta._post(client, meta.EP_COMPLETION, {"SCLBDM": "04", "*order": "-CZSJ"},
                                     meta.APP_XYWCCX), "cxxsscfa")
        if rows:
            for k in ("XH", "PYFADM", "BYNJDM", "SCLBDM"):
                if _s(rows[0].get(k)):
                    ctx.setdefault(k, _s(rows[0].get(k)))
    except jwxt.JwxtError:
        pass
    return ctx


def _actions(client, app: emap.App, rep_app: dict) -> list[tuple[str, dict]]:
    """返回 [(绝对路径, captions)]。"""
    try:
        client.enter_emap_app(app.index)
        rep_app["entered"] = True
    except jwxt.JwxtError as e:
        rep_app["entered"] = type(e).__name__
        return []
    d = emap.discover(client, app)
    rep_app["index_status"] = d.get("index_status")
    rep_app["modules_seen"] = d.get("modules_seen")
    mm = emap.module_meta(client, app, d.get("modules_seen", [app.route]))
    out: dict = {}
    rep_app["modules"] = {}
    for m, info in mm["modules"].items():
        rep_app["modules"][m] = {"via": info["via"], "actions": [
            {"name": a.get("name"), "url": a["url"], "fields": a["fields"],
             "captions": a.get("captions") or {}} for a in info["actions"]]}
        for a in info["actions"]:
            caps = {**info.get("captions", {}), **(a.get("captions") or {})}
            out.setdefault(app.abs(a["url"]), caps)
    for p in d.get("do_paths", []):
        if not re.search(r"modules/\w+\.do$", p) and "code" not in p.lower():
            out.setdefault(app.abs(p), {})
    for an, rel in KNOWN:
        if an == app.name:
            out.setdefault(app.root + rel, {})
    return [(p, c) for p, c in out.items() if _HINT.search(p.rsplit("/", 1)[-1]) and not _SKIP.search(p.rsplit("/", 1)[-1])]


def _is_tree(fields) -> bool:
    f = set(fields)
    return "KZH" in f and bool(f & {"KZM", "KZMC"}) and not (f & {"KCH", "KCDM"})


def _is_course(fields) -> bool:
    f = set(fields)
    return bool(f & {"KCH", "KCDM"}) and bool(f & {"KCM", "KCMC"})


def explore(client, log=lambda s: None) -> tuple[dict, dict]:
    """返回 (脱敏报告, 内部最佳 {plan:..., done:...})。"""
    ctx = _context(client)
    rep: dict = {"ctx_keys": sorted(ctx), "apps": {}, "calls": []}
    best: dict = {}
    for name, route in APPS:
        app = emap.App(name, route)
        ra: dict = {}
        rep["apps"][f"{name}/{route}"] = ra
        acts = _actions(client, app, ra)
        log(f"[{name}] entered={ra.get('entered')} modules={ra.get('modules_seen')} candidates={len(acts)}")
        for path, caps in acts[:40]:
            for vname, form in _variants(ctx, path):
                code, obj = _post(client, app, path, form)
                rec = {"app": name, "action": path.split("/sys/", 1)[-1], "variant": vname, "status": code}
                if isinstance(obj, dict):
                    rec["code"] = _s(obj.get("code"))[:8]
                    if isinstance(obj.get("msg"), str):
                        rec["msg"] = re.sub(r"\d{5,}", "#", obj["msg"])[:50]
                    hit = _rows_any(obj)
                    if hit:
                        k, rows, total = hit
                        flds = sorted({f for r in rows[:20] if isinstance(r, dict) for f in r})
                        rec.update({"datas_key": k, "rows": len(rows), "total": total, "fields": flds,
                                    "captions": {f: caps[f] for f in flds if f in caps}})
                rep["calls"].append(rec)
                if rec.get("rows"):
                    tot = int(rec.get("total") or rec["rows"])
                    if tot > MAX_TOTAL:
                        rec["rejected"] = "unfiltered_total_over_%d" % MAX_TOTAL
                    log(f"  {rec['action']} [{vname}] rows={rec['rows']} total={rec.get('total')} "
                        f"fields={len(rec['fields'])}{' course' if _is_course(rec['fields']) else ''}"
                        f"{' REJECTED' if rec.get('rejected') else ''}")
                    if rec.get("rejected"):
                        continue  # 试下一个（带过滤的）变体
                    if _is_tree(rec["fields"]):
                        best.setdefault("trees", {})[path] = {"app": name, "route": route, "path": path,
                                                              "form": form, "variant": vname, "captions": caps,
                                                              "total": tot}
                    if _is_course(rec["fields"]):
                        # 学生本人方案（xywccx，带 XH/PYFADM）优先
                        kind = "plan"
                        score = (name == "xywccx", "XH" in form or "PYFADM" in form or "querySetting" in form,
                                 tot, len(rec["fields"]))
                        if kind not in best or score > best[kind]["score"]:
                            best[kind] = {"app": name, "route": route, "path": path, "form": form,
                                          "variant": vname, "captions": caps, "score": score, "total": tot}
                    break
    rep["best"] = {k: {"app": v["app"], "action": v["path"].split("/sys/", 1)[-1], "variant": v["variant"],
                       "total": v["total"]} for k, v in best.items() if k != "trees"}
    rep["tree_candidates"] = [{"action": v["path"].split("/sys/", 1)[-1], "variant": v["variant"], "total": v["total"]}
                              for v in best.get("trees", {}).values()]
    rep["calls_with_rows"] = [c for c in rep["calls"] if c.get("rows")]
    return rep, best


def fetch_all(client, b: dict, page_size: int = 200, max_pages: int = 30) -> list:
    app = emap.App(b["app"], b["route"])
    client.enter_emap_app(app.index)
    out: list = []
    for page in range(1, max_pages + 1):
        code, obj = _post(client, app, b["path"], {**b["form"], "pageSize": str(page_size),
                                                    "pageNumber": str(page)})
        hit = _rows_any(obj) if code == 200 else None
        if not hit or not hit[1]:
            break
        if hit[2] is not None and int(hit[2]) > MAX_TOTAL:
            raise jwxt.JwxtError(f"refused: unfiltered source total {hit[2]} > {MAX_TOTAL}")
        out += [r for r in hit[1] if isinstance(r, dict)]
        total = hit[2]
        if (total is not None and len(out) >= int(total)) or len(hit[1]) < page_size:
            break
    return out


def _col(row: dict, caps: dict, col: str) -> str:
    keys, words = COLS[col]
    for k in keys:
        for kk in (k + "_DISPLAY", k):
            v = _s(row.get(kk))
            if v:
                return v
    for f, cap in caps.items():
        if any(w in cap for w in words) and not f.endswith("_DISPLAY"):
            v = _s(row.get(f + "_DISPLAY")) or _s(row.get(f))
            if v:
                return v
    return ""


def _status(raw: str, score: str) -> str:
    r = raw.strip()
    if r in ("在修", "修读中", "正在修读") or "在修" in r:
        return "在修"
    if r in ("1", "是", "已修", "通过", "已通过", "已完成", "完成") or "已修" in r or "通过" in r and "未" not in r:
        return "已修"
    if score:
        from .meta import _passed
        return "已修" if _passed(score) else "未通过"
    return "未修" if r else ""


def normalize(rows: list, caps: dict) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        c = {k: _col(r, caps, k) for k in COLS}
        if not (c["code"] or c["name"]):
            continue
        key = (c["code"] or c["name"], c["group_code"])
        if key in seen:
            continue
        seen.add(key)
        try:
            c["credit"] = float(c["credit"]) if c["credit"] else None
        except ValueError:
            c["credit"] = None
        out.append(c)
    return out


def merge(plan: list, done: list, grades=None, courses_now=None) -> list:
    by_code = {d["code"]: d for d in done if d["code"]}
    by_name = {d["name"]: d for d in done if d["name"]}
    gmap: dict = {}
    for g in grades or []:
        gmap.setdefault(g.name.strip(), (g.score, g.term))
    now = {c.name.strip() for c in (courses_now or [])}
    res = []
    for c in plan or done:
        d = by_code.get(c["code"]) or by_name.get(c["name"]) or {}
        for k in ("score", "status_raw", "group", "group_code"):
            if not c.get(k) and d.get(k):
                c[k] = d[k]
        if not c["score"] and c["name"] in gmap:
            c["score"] = gmap[c["name"]][0]
        if not c.get("term") and c["name"] in gmap:
            c["term"] = gmap[c["name"]][1]
        st = _status(c.get("status_raw", ""), c.get("score", ""))
        sel = (c.pop("selected", "") or "").strip()
        if sel in ("1", "是", "true") and st in ("", "未修") and not c.get("score"):
            st = "在修"
        if not st:
            st = "在修" if c["name"] in now else "未修"
        if st == "未修" and c["name"] in now:
            st = "在修"
        c["status"] = st
        c.pop("status_raw", None)
        res.append(c)
    return res


def _cache_path():
    return jwxt.config_dir() / "data" / "plan_profile2.json"


def fetch_plan(client, grades=None, courses_now=None, use_cache: bool = True) -> dict:
    best: dict = {}
    cp = _cache_path()
    if use_cache and cp.exists():
        try:
            best = json.loads(cp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            best = {}
    if "plan" not in best or "trees" not in best or "kzkccx" in best["plan"].get("path", "") and not any(
            k in best["plan"].get("form", {}) for k in ("PYFADM", "querySetting")):
        _, found = explore(client)
        best = {k: {kk: v[kk] for kk in ("app", "route", "path", "form", "captions")}
                for k, v in found.items() if k != "trees"}
        if found.get("trees"):
            best["trees"] = {p: {kk: v[kk] for kk in ("app", "route", "path", "form", "captions", "variant")}
                             for p, v in found["trees"].items()}
        if not best:
            raise jwxt.JwxtError("未找到培养方案课程接口（运行 jlu-toolkit plan --probe 查看）")
        # 缓存里不保存 XH 等个人参数值：只存参数名，调用时重新取
        strip = lambda v: {**v, "form": {f: ("" if f in ("XH", "PYFADM", "BYNJDM", "SCLBDM") else val)  # noqa: E731
                                         for f, val in v["form"].items()}}
        cache = {k: ({p: strip(x) for p, x in v.items()} if k == "trees" else strip(v)) for k, v in best.items()}
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    allb = [b for k, b in best.items() if k != "trees"] + list((best.get("trees") or {}).values())
    if any(True for b in allb for k, v in b["form"].items() if k in ("XH", "PYFADM") and not v):
        ctx = _context(client)
        for b in allb:
            for k in list(b["form"]):
                if k in ctx and not b["form"][k]:
                    b["form"][k] = ctx[k]
    plan = normalize(fetch_all(client, best["plan"]), best["plan"].get("captions") or {}) if "plan" in best else []
    done = []
    if "done" in best and best["done"]["path"] != best["plan"]["path"]:
        try:
            done = normalize(fetch_all(client, best["done"]), best["done"].get("captions") or {})
        except jwxt.JwxtError:
            done = []
    courses = merge(plan, done, grades, courses_now)
    kzh = {c["group_code"] for c in courses if c.get("group_code")}
    tree, tree_src = None, None
    for pth, b in (best.get("trees") or {}).items():
        try:
            nodes = tree_nodes(fetch_all(client, b))
        except jwxt.JwxtError:
            continue
        cov = len(kzh & {n["code"] for n in nodes})
        if nodes and (tree is None or cov > tree[0]):
            tree, tree_src = (cov, nodes), pth.split("/sys/", 1)[-1]
    res = {"source": {k: {"app": v["app"], "action": v["path"].split("/sys/", 1)[-1]}
                      for k, v in best.items() if k != "trees"},
           "count": len(courses), "courses": courses}
    if tree:
        res["tree_nodes"] = tree[1]
        res["source"]["tree"] = {"action": tree_src}
    return res


def _f(v):
    try:
        return float(v) if _s(v) else None
    except ValueError:
        return None


def tree_nodes(rows: list) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        k = _s(r.get("KZH"))
        if not k or k in seen:
            continue
        seen.add(k)
        out.append({"code": k, "name": _s(r.get("KZM") or r.get("KZMC")) or k,
                    "parent": _s(r.get("FKZH") or r.get("SJKZH") or r.get("FKZDM")),
                    "required": _f(r.get("YQXF") if _s(r.get("YQXF")) else r.get("ZSYQXF") if _s(r.get("ZSYQXF")) else r.get("XF")),
                    "earned": _f(r.get("WCXF") if _s(r.get("WCXF")) else r.get("YHXF")),
                    "nature": _s(r.get("KCXZDM_DISPLAY") or r.get("KCXZDM"))})
    return out


def build_tree(nodes: list[dict], courses: list[dict], comp_groups=None) -> dict:
    """嵌套课组树；课程按 KZH 挂载；返回 {roots, unmatched, stats}。"""
    idx = {n["code"]: {**n, "children": [], "courses": []} for n in nodes}
    for g in comp_groups or []:  # 学业完成里的已获学分补齐
        n = idx.get(g.get("code"))
        if n and n["earned"] is None and g.get("earned") is not None:
            n["earned"] = g["earned"]
        if n and n["required"] is None and g.get("required") is not None:
            n["required"] = g["required"]
    roots = []
    for n in idx.values():
        par = idx.get(n["parent"]) if n["parent"] and n["parent"] != n["code"] else None
        (par["children"] if par else roots).append(n)
    unmatched, reasons = [], {}
    for c in courses:
        n = idx.get(c.get("group_code") or "")
        if n:
            n["courses"].append(c)
            continue
        why = ("substitute" if c.get("sub_rd") or c.get("sub_td")
               else "no_kzh" if not c.get("group_code") else "kzh_not_in_tree")
        c["unmatched_reason"] = why
        reasons[why] = reasons.get(why, 0) + 1
        unmatched.append(c)

    def roll(n, depth=0):
        tot = sum((x["credit"] or 0) for x in n["courses"] if x["status"] == "已修")
        if depth < 12:
            tot += sum(roll(ch, depth + 1) for ch in n["children"])
        n["earned_courses"] = round(tot, 2)
        if n["earned"] is None:
            n["earned"] = n["earned_courses"]
            n["earned_source"] = "plan_courses"
        else:
            n.setdefault("earned_source", "jw")
        n["missing"] = round(max(0.0, n["required"] - n["earned"]), 2) if n["required"] is not None else None
        return tot

    for r in roots:
        roll(r)
    kzh = {c.get("group_code") for c in courses if c.get("group_code")}
    return {"roots": roots, "unmatched": unmatched,
            "stats": {"groups": len(idx), "roots": len(roots), "courses": len(courses),
                      "matched": len(courses) - len(unmatched), "unmatched": len(unmatched),
                      "unmatched_kzh": len(kzh - set(idx)), "reasons": reasons}}


def diagnose(client, best: dict, comp_groups=None) -> dict:
    """只输出计数：各候选课组树覆盖了多少课程 KZH。"""
    out: dict = {"course_source": None, "trees": []}
    if "plan" not in best:
        return out
    courses = merge(normalize(fetch_all(client, best["plan"]), best["plan"].get("captions") or {}), [])
    kzh = {c["group_code"] for c in courses if c["group_code"]}
    out.update({"course_source": best["plan"]["path"].split("/sys/", 1)[-1], "courses": len(courses),
                "course_kzh_distinct": len(kzh), "courses_without_kzh": sum(1 for c in courses if not c["group_code"]),
                "substitute_courses": sum(1 for c in courses if c.get("sub_rd") or c.get("sub_td"))})
    cands = [(v["path"].split("/sys/", 1)[-1], v) for v in best.get("trees", {}).values()]
    for name, v in cands:
        try:
            nodes = tree_nodes(fetch_all(client, v))
        except jwxt.JwxtError as e:
            out["trees"].append({"action": name, "error": type(e).__name__})
            continue
        st = build_tree(nodes, [dict(c) for c in courses])["stats"]
        out["trees"].append({"action": name, "variant": v["variant"], "groups": st["groups"],
                             "roots": st["roots"], "kzh_in_tree": len(kzh & {n["code"] for n in nodes}),
                             "matched": st["matched"], "unmatched": st["unmatched"],
                             "unmatched_kzh": st["unmatched_kzh"], "reasons": st["reasons"]})
    if comp_groups:
        st = build_tree([{"code": g.get("code"), "name": g.get("name"), "parent": g.get("parent"),
                          "required": g.get("required"), "earned": g.get("earned"), "nature": ""}
                         for g in comp_groups if g.get("code")], [dict(c) for c in courses])["stats"]
        out["trees"].append({"action": "completion.json (cxscfakz)", "groups": st["groups"], "roots": st["roots"],
                             "kzh_in_tree": len(kzh) - st["unmatched_kzh"], "matched": st["matched"],
                             "unmatched": st["unmatched"], "unmatched_kzh": st["unmatched_kzh"],
                             "reasons": st["reasons"]})
    return out


def attach_to_completion(comp: dict, plan: dict) -> dict:
    """把课程挂到课组；服务器 WCXF 优先，缺失才用课程明细合计。另附嵌套课组树 comp['tree']。"""
    groups = comp.get("groups") or []
    nodes = plan.get("tree_nodes") or [{"code": g.get("code"), "name": g.get("name"), "parent": g.get("parent"),
                                         "required": g.get("required"), "earned": g.get("earned"),
                                         "nature": g.get("nature", "")} for g in groups if g.get("code")]
    if nodes:
        t = build_tree(nodes, [dict(c) for c in plan.get("courses", [])], groups)
        comp["tree"] = t["roots"]
        comp["unmatched"] = t["unmatched"]
        comp["tree_stats"] = t["stats"]
        comp["tree_source"] = (plan.get("source") or {}).get("tree", {}).get("action") or "completion"
    idx = {g.get("code"): g for g in groups if g.get("code")}
    by_name = {g.get("name"): g for g in groups}
    for c in plan.get("courses", []):
        g = idx.get(c.get("group_code")) or by_name.get(c.get("group"))
        if g is not None:
            g.setdefault("courses", []).append(c)
    for g in groups:
        if g.get("earned") is None and g.get("courses"):
            g["earned"] = round(sum(c["credit"] or 0 for c in g["courses"] if c["status"] == "已修"), 2)
            g["earned_source"] = "plan_courses"
    return comp
