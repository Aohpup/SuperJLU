"""通用 EMAP 应用发现（只读）：进入应用入口 → 扫描页面脚本/视图 → 拉取模块元数据。

空教室（kxjas）用同样的方法找到了真实接口；这里推广到任意应用（如成绩 cjcx）。
产出只包含代码层面的信息：路径、模块名、动作 URL、字段名。不含任何个人数值。
"""
from __future__ import annotations

import json
import re
import urllib.parse as up
from typing import Optional

from . import jwxt

HOST = "https://iedu.jlu.edu.cn"
_DO_RE = re.compile(r"""["'(]([\w./*-]*?\.do)\b""")
_SRC_RE = re.compile(r"""(?:src|href)\s*=\s*["']([^"'#?]+\.(?:js|json|html))""", re.I)
_JS_REF = re.compile(r"""["']([\w./*-]+\.(?:js|html))["']""")


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



def rows_any(obj):
    """EMAP 响应 → (datas_key, rows, totalSize|None)；兼容 datas.<k>.rows / datas.<k> 列表 / datas 列表。"""
    if not isinstance(obj, dict):
        return None
    d = obj.get("datas")
    if isinstance(d, dict):
        for k, blk in d.items():
            if isinstance(blk, dict) and isinstance(blk.get("rows"), list):
                tot = blk.get("totalSize", blk.get("total"))
                try:
                    tot = int(tot) if tot is not None else None
                except (TypeError, ValueError):
                    tot = None
                return k, blk["rows"], tot
            if isinstance(blk, list):
                return k, blk, None
    if isinstance(d, list):
        return "datas", d, None
    return None


def post_json(client, path: str, form: dict, referer: str):
    """POST → (status, obj|None)；网络错误返回 (None, None)。"""
    try:
        code, text, _ = client.post_raw(path, form, referer)
    except jwxt.NetworkError:
        return None, None
    try:
        return code, json.loads(text) if text else None
    except (json.JSONDecodeError, ValueError):
        return code, None


class TooLarge(jwxt.JwxtError):
    """totalSize 超过上限：视为未过滤的全校数据，拒绝翻页。"""


def fetch_paged(client, path: str, form: dict, referer: str, page_size: int = 200,
                max_pages: int = 30, max_total: Optional[int] = None) -> list:
    """按 pageSize/pageNumber 拉全；任何一页 totalSize > max_total 立即拒绝。"""
    from .endpoints import MAX_TOTAL
    limit = MAX_TOTAL if max_total is None else max_total
    out: list = []
    for page in range(1, max_pages + 1):
        code, obj = post_json(client, path, {**form, "pageSize": str(page_size), "pageNumber": str(page)}, referer)
        hit = rows_any(obj) if code == 200 else None
        if not hit or not hit[1]:
            break
        if hit[2] is not None and hit[2] > limit:
            raise TooLarge(f"refused: unfiltered source total {hit[2]} > {limit}")
        out += [r for r in hit[1] if isinstance(r, dict)]
        if (hit[2] is not None and len(out) >= hit[2]) or len(hit[1]) < page_size:
            break
    return out


def call_known(client, name: str, ctx: Optional[dict] = None, paged: bool = True,
               trace: Optional[list] = None) -> Optional[list]:
    """调用 endpoints.KNOWN[name]；缺少上下文或失败返回 None（调用方据此回退到发现）。"""
    from . import endpoints as E
    ep = E.get(name)
    try:
        client.enter_emap_app(ep.index)
    except jwxt.LoginError:
        raise
    except jwxt.JwxtError:
        return None
    rec: dict = {"name": name, "path": ep.path, "entered": True}
    if trace is not None:
        trace.append(rec)
    if ep.paged and paged:
        form = E.build_form(ep, ctx)
        rec["param_names"] = sorted(form) if form is not None else None
        if form is None:
            rec["skipped"] = "missing_ctx"
            return None
        if trace is not None:  # 先单独取第 1 页记录 total（仅计数）
            code, obj = post_json(client, ep.path, {**form, "pageSize": "200", "pageNumber": "1"}, ep.referer)
            hit = rows_any(obj) if code == 200 else None
            rec.update({"status": code, "code": str((obj or {}).get("code", ""))[:8] if isinstance(obj, dict) else None,
                        "rows_page1": len(hit[1]) if hit else None, "total": hit[2] if hit else None})
        rows = fetch_paged(client, ep.path, form, ep.referer)
        rec["rows"] = len(rows)
        return rows
    form = E.build_form(ep, ctx)
    rec["param_names"] = sorted(form) if form is not None else None
    if form is None:
        rec["skipped"] = "missing_ctx"
        return None
    code, obj = post_json(client, ep.path, form, ep.referer)
    hit = rows_any(obj) if code == 200 else None
    rec.update({"status": code, "rows": len(hit[1]) if hit else None, "total": hit[2] if hit else None})
    if hit is None:
        return None
    if hit[2] is not None and hit[2] > E.MAX_TOTAL:
        raise TooLarge(f"refused: total {hit[2]}")
    return [r for r in hit[1] if isinstance(r, dict)]


class App:
    def __init__(self, name: str, route: str):
        self.name, self.route = name, route
        self.root = f"/jwapp/sys/{name}/"
        self.index = f"{HOST}{self.root}*default/index.do"
        self.base = self.root + "modules/"

    def abs(self, a: str) -> str:
        """解析 EMAP 元数据里的相对 URL。

        元数据常给 ``cjcx/cxxspjjdxx.do`` 或 ``./modules/cjcx/xxx.do``，
        正确绝对路径是 ``/jwapp/sys/<app>/modules/...``（不是 ``/<app>/cjcx/...``）。
        """
        a = (a or "").split("?")[0].strip()
        if not a:
            return a
        if a.startswith("/"):
            return a
        a = a.lstrip("./")
        if a.startswith("jwapp/"):
            return "/" + a
        if a.startswith("modules/"):
            return self.root + a
        # ``cjcx/xxx.do`` → modules/cjcx/xxx.do
        return self.base + a

    def view_files(self) -> list[str]:
        r = self.route
        return [f"modules/{r}/{r}.js", f"modules/{r}.js", f"{r}/{r}.js", f"pages/{r}/{r}.js", f"{r}.js",
                "index.js", "config.js", "router.js", "public/js/index.js", "public/js/config.js",
                f"modules/{r}/{r}.html", f"{r}/{r}.html", "*default/config.json"]


def discover(client, app: App, max_files: int = 30) -> dict:
    out: dict = {"app": app.name, "route": app.route}
    try:
        code, html, final, _ = client._request(app.index + "?EMAP_LANG=zh", headers={"Referer": jwxt.IEDU_PORTAL})
    except jwxt.NetworkError as e:
        return {"error": type(e).__name__}
    out["index_status"], out["index_bytes"] = code, len(html or "")
    out["index_final"] = up.urlparse(final or "").path
    srcs = [up.urljoin(final or app.index, s) for s in _SRC_RE.findall(html or "")]
    out["script_srcs"] = [up.urlparse(s).path for s in srcs][:60]
    queue = list(dict.fromkeys([s for s in srcs if app.root in s] + [HOST + app.root + f for f in app.view_files()]))
    paths = set(_DO_RE.findall(html or ""))
    fetched, seen = [], set()
    while queue and len(seen) < max_files:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        try:
            c, txt, _, _ = client._request(u, headers={"Referer": app.index})
        except jwxt.NetworkError:
            continue
        if c != 200 or not txt or "loginForm" in txt:
            continue
        fetched.append({"path": up.urlparse(u).path, "bytes": len(txt)})
        paths.update(_DO_RE.findall(txt))
        for ref in _JS_REF.findall(txt)[:40]:
            v = up.urljoin(u, ref)
            if app.root in v and v not in seen:
                queue.append(v)
    out["fetched"] = fetched
    out["do_paths"] = sorted(p for p in paths if len(p) < 160)
    mods = {app.route}
    for p in out["do_paths"]:
        m = re.search(r"modules/(\w+)\.do$", p) or re.search(r"modules/(\w+)/\w+\.do$", p)
        if m:
            mods.add(m.group(1))
    out["modules_seen"] = sorted(mods)
    return out


def _try(client, app: App, method: str, path: str, form: dict):
    try:
        if method == "POST":
            code, text, _ = client.post_raw(path, form, app.index)
        else:
            code, text, _, _ = client._request(HOST + path, headers={
                "Referer": app.index, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json, */*"})
    except jwxt.NetworkError:
        return None, None
    try:
        return code, json.loads(text) if text else None
    except (json.JSONDecodeError, ValueError):
        return code, text


def parse_models(obj) -> list[dict]:
    """EMAP 元数据里每个模型/动作 → {name, url, fields, captions}。

    captions: {字段名: 中文标题}，来自 control.caption / title / label（代码层，非个人数据）。
    """
    out = []

    def walk(x):
        if isinstance(x, dict):
            url = x.get("url")
            ctrls = x.get("controls") or x.get("fields") or x.get("items")
            if isinstance(url, str) and url.endswith(".do") and "code" not in url.lower():
                names, captions = [], {}
                if isinstance(ctrls, list):
                    for c in ctrls:
                        if not isinstance(c, dict):
                            continue
                        n = c.get("name")
                        if isinstance(n, str) and _CODE.match(n):
                            names.append(n)
                            cap = c.get("caption") or c.get("title") or c.get("label") or c.get("JSONParam")
                            if isinstance(cap, str) and cap.strip() and not re.search(r"\d{6,}", cap):
                                captions[n] = cap.strip()[:40]
                out.append({"name": str(x.get("name") or "")[:40], "url": url,
                            "fields": sorted(set(names)), "captions": captions})
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(obj)
    return out


def parse_captions(obj) -> dict:
    """整份元数据里所有字段名 → caption（后者覆盖前者）。"""
    caps = {}
    for a in parse_models(obj):
        caps.update(a.get("captions") or {})
    return caps



def module_meta(client, app: App, modules) -> dict:
    """对每个模块尝试 4 种元数据取法；返回 {modules:{m:{via, actions, captions}}, trace}。"""
    res, trace = {}, []
    for mname in modules:
        paths = list(dict.fromkeys([
            app.base + mname + ".do",
            app.base + app.route + "/" + mname + ".do",
        ]))
        found = False
        for path in paths:
            if found:
                break
            for method, pth, form in (("GET", path + "?*json=1", {}), ("POST", path, {}),
                                      ("POST", path, {"*json": "1"}), ("GET", path, {})):
                code, obj = _try(client, app, method, pth, form)
                rec = {"module": mname, "method": method, "path": pth, "form_keys": sorted(form), "status": code}
                if isinstance(obj, dict):
                    rec["keys"] = sorted(obj)[:15]
                    if isinstance(obj.get("code"), (str, int)):
                        rec["code"] = str(obj["code"])[:8]
                    if isinstance(obj.get("msg"), str):
                        rec["msg"] = re.sub(r"\d{5,}", "#", obj["msg"])[:60]
                trace.append(rec)
                if isinstance(obj, (dict, list)):
                    models = parse_models(obj)
                    flat = parse_meta(obj)
                    caps = parse_captions(obj)
                    if models or flat["actions"] or caps:
                        known = {x["url"] for x in models}
                        models += [{"name": "", "url": a, "fields": [], "captions": {}}
                                   for a in flat["actions"] if a not in known]
                        res[mname] = {"via": f"{method} {pth[len(app.root):]}" + (" *json" if form else ""),
                                      "actions": models, "all_fields": flat["fields"], "captions": caps}
                        found = True
                        break
    return {"modules": res, "trace": trace}



def explore_app(client, app: App) -> dict:
    """完整发现报告（脱敏）。"""
    client.enter_emap_app(app.index)
    d = discover(client, app)
    mm = module_meta(client, app, d.get("modules_seen", [app.route]))
    actions = sorted({app.abs(a["url"]) for m in mm["modules"].values() for a in m["actions"]}
                     | {app.abs(p) for p in d.get("do_paths", []) if not re.search(r"modules/\w+\.do$", p)
                        and "code" not in p.lower()})
    return {"discover": d, "meta": mm["modules"], "meta_trace": mm["trace"], "action_urls": actions}

