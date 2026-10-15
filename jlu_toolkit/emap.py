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
from .rooms import parse_meta

HOST = "https://iedu.jlu.edu.cn"
_DO_RE = re.compile(r"""["'(]([\w./*-]*?\.do)\b""")
_SRC_RE = re.compile(r"""(?:src|href)\s*=\s*["']([^"'#?]+\.(?:js|json|html))""", re.I)
_JS_REF = re.compile(r"""["']([\w./*-]+\.(?:js|html))["']""")
_CODE = re.compile(r"^[A-Z][A-Z0-9_]{1,30}$")


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
    """EMAP 元数据里每个模型/动作 → {name, url, fields}（只取名字）。"""
    out = []

    def walk(x):
        if isinstance(x, dict):
            url = x.get("url")
            ctrls = x.get("controls") or x.get("fields") or x.get("items")
            if isinstance(url, str) and url.endswith(".do") and "code" not in url.lower():
                names = sorted({c.get("name") for c in ctrls if isinstance(c, dict)
                                and isinstance(c.get("name"), str) and _CODE.match(c["name"])}) \
                    if isinstance(ctrls, list) else []
                out.append({"name": str(x.get("name") or "")[:40], "url": url, "fields": names})
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for i in x:
                walk(i)

    walk(obj)
    return out


def module_meta(client, app: App, modules) -> dict:
    """对每个模块尝试 4 种元数据取法；返回 {modules:{m:{via, actions:[{name,url,fields}]}}, trace}。"""
    res, trace = {}, []
    for m in modules:
        path = app.base + m + ".do"
        for method, p, form in (("POST", path, {}), ("GET", path + "?*json=1", {}),
                                ("POST", path, {"*json": "1"}), ("GET", path, {})):
            code, obj = _try(client, app, method, p, form)
            rec = {"module": m, "method": method, "path": p, "form_keys": sorted(form), "status": code}
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
                if models or flat["actions"]:
                    known = {x["url"] for x in models}
                    models += [{"name": "", "url": a, "fields": []} for a in flat["actions"] if a not in known]
                    res[m] = {"via": f"{method} {p[len(app.base):]}" + (" *json" if form else ""),
                              "actions": models, "all_fields": flat["fields"]}
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
