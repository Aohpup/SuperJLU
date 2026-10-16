"""校园各站点的会话层（通用）。

- 站点注册表 SITES：id / 名称 / host / 认证方式（cas/own/none）/ 能否经 VPN 访问
- 每站 cookie：SecretFile(config_dir(), f"session-{site}") 加密保存（secure_store）；
  教务（jwxt）沿用原有 session.enc / session_status.json，不改行为
- 每站状态：config_dir()/sessions_status.json → {site: {state, checked_at, reason}}（不含任何秘密）
- 存活检查钩子：可选导入 jlu_toolkit.campus（露娜的探测模块），取 check_<site_id>(session)；
  也可用 register_check() 显式注册。默认没有钩子 → 不检查。不做后台轮询，不绕过验证码。
- vpn_url(url)：取 campus.vpn_url 或 register_vpn_url() 注册的实现；尚无实现时抛 NotImplementedError。

策略：所有站点的 cookie 只经加密存储保存；从不保存支付信息（pay 站只读、只看状态）；
带验证码的站点（ilearn）不保存密码，除非用户明确选择保存。
"""
from __future__ import annotations

import importlib
import json
import time
import urllib.parse
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional

from . import jwxt, secure_store

OK, EXPIRED, MISSING, UNKNOWN = jwxt.SESSION_OK, jwxt.SESSION_EXPIRED, jwxt.SESSION_MISSING, jwxt.SESSION_UNKNOWN


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    host: str
    auth: str              # cas / own / none
    vpn: bool = True       # 校外能否经 vpn.jlu.edu.cn 访问
    captcha: bool = False  # 登录需要验证码（不保存密码，除非用户明确保存）
    readonly: bool = True  # 本工具只读
    optional_login: bool = False  # 不登录也能用基本功能（登录只为个人中心）
    service: str = ""      # CAS service URL（refresh_via_cas 用；空 = 尚未探明，不刷新）
    follows: str = ""      # 登录状态跟随另一站点（如学在吉大经教务统一认证免登进入）


SITES: Dict[str, Site] = {s.id: s for s in (
    Site("jwxt", "教务系统", "iedu.jlu.edu.cn", "cas", service=jwxt.CAS_SERVICE),
    # 以下认证方式来自露娜的探测（PR #18）
    Site("pay", "校园缴费", "ip.jlu.edu.cn", "own", captcha=True),      # 卡号+密码+验证码
    Site("xsxk", "选课系统", "icourses.jlu.edu.cn", "own", captcha=True),  # AES 加密密码+验证码，token 头鉴权
    # 邮箱+密码+验证码；课程中心入口可能走 CAS，尚未确认
    # 经 /api/sso/jump 用统一认证免登进入，登录状态与教务一致
    Site("ilearn", "学在吉大", "ilearntec.jlu.edu.cn", "own", captcha=True, follows="jwxt"),
    Site("vpn", "WebVPN", "vpn.jlu.edu.cn", "cas", vpn=False),
    # 首页无需登录；个人中心走 CAS（optional_login：没登录也算可用）
    Site("lib", "图书馆", "lib.jlu.edu.cn", "cas", optional_login=True),
    # 统一认证本身：保存登录后 CAS 主机上的全部 cookie（含 TGC 类长期票据），用于静默换票
    Site("cas", "统一认证", "cas.jlu.edu.cn", "cas"),
)}

MESSAGES = {OK: "已登录", EXPIRED: "登录已过期，请重新登录", MISSING: "尚未登录", UNKNOWN: "已保存会话，尚未验证"}
CheckFn = Callable[[object], dict]
_checks: Dict[str, CheckFn] = {}
_vpn_impl: Optional[Callable[[str], str]] = None


class SiteSessionExpired(jwxt.SessionExpiredError):
    """某站点会话失效；Web API 返回 401 + {session_expired: true, site}。"""

    def __init__(self, site: str, msg: str = ""):
        self.site = site
        name = SITES[site].name if site in SITES else site
        super().__init__(msg or f"{name} 登录会话已过期，请重新登录")


def site(site_id: str) -> Site:
    if site_id not in SITES:
        raise ValueError(f"未知站点：{site_id}（可选：{', '.join(SITES)}）")
    return SITES[site_id]


def _secret(site_id: str) -> secure_store.SecretFile:
    site(site_id)
    if site_id == "jwxt":
        return jwxt._secret(jwxt.default_session_path())
    return secure_store.SecretFile(jwxt.config_dir(), f"session-{site_id}")


# ───────── cookie ─────────

def save_cookies(site_id: str, cookies: List[dict]) -> None:
    if site_id == "jwxt":
        raise ValueError("教务会话请用 JwxtClient.save_session()")
    _secret(site_id).save({"cookies": cookies})
    _write_status(site_id, OK)


def load_cookies(site_id: str) -> Optional[List[dict]]:
    try:
        d = _secret(site_id).load()
    except secure_store.SecureStoreError:
        return None
    return (d or {}).get("cookies") if isinstance(d, dict) else None


def client(site_id: str) -> jwxt.JwxtClient:
    """带该站 cookie 的 HTTP 客户端（jwxt 用原有会话）。"""
    c = jwxt.JwxtClient()
    if site_id == "jwxt":
        c.load_session()
    else:
        c.jar = jwxt.jar_from_list(load_cookies(site_id) or [])
        c._rebuild_opener()
    return c


def clear(site_id: str) -> None:
    _secret(site_id).delete()
    if site_id == "jwxt":
        try:
            jwxt.session_status_path().unlink()
        except OSError:
            pass
    else:
        _write_status(site_id, MISSING, "已清除")


# ───────── 状态 ─────────

def _status_path():
    return jwxt.config_dir() / "sessions_status.json"


def _read_all() -> dict:
    try:
        d = json.loads(_status_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_status(site_id: str, state: str, reason: str = "") -> None:
    if site_id == "jwxt":
        if state == EXPIRED:
            jwxt.mark_session_expired(reason)
        elif state in (OK, UNKNOWN):
            jwxt._write_session_status(state, reason)
        return
    d = _read_all()
    d[site_id] = {"state": state, "checked_at": int(time.time()), "reason": str(reason)[:200]}
    p = _status_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def mark_expired(site_id: str, reason: str = "") -> None:
    site(site_id)
    _write_status(site_id, EXPIRED, reason)


def status(site_id: str) -> dict:
    s = site(site_id)
    if s.follows:
        src = status(s.follows)
        return {**src, "id": s.id, "name": s.name, "host": s.host, "auth": s.auth, "vpn": s.vpn,
                "captcha": s.captcha, "follows": s.follows, "has_check": False}
    if site_id == "jwxt":
        j = jwxt.session_status()
        state, checked, reason = j["state"], j.get("checked_at"), ""
    else:
        info = _read_all().get(site_id, {})
        has = _secret(site_id).exists()
        state = (info.get("state") or UNKNOWN) if has else MISSING
        checked, reason = info.get("checked_at"), info.get("reason", "") if has else ""
    optional = s.auth == "none" or s.optional_login
    if s.auth == "none" and state == MISSING:
        state = OK  # 无需登录的站点
    msg = "无需登录" if s.auth == "none" else MESSAGES[state]
    if s.optional_login and state == MISSING:
        msg = "未登录（基本功能无需登录，个人中心需统一认证）"
    return {"id": s.id, "name": s.name, "host": s.host, "auth": s.auth, "vpn": s.vpn, "captcha": s.captcha,
            "state": state, "checked_at": checked, "needs_login": state in (EXPIRED, MISSING) and not (optional and state == MISSING),
            "optional_login": optional,
            "message": msg + (f"（{reason}）" if reason and state != OK else ""),
            "has_check": find_check(site_id) is not None}


def all_status() -> dict:
    return {"ok": True, "sites": [status(i) for i in SITES]}


# ───────── 钩子 ─────────

def _campus():
    try:
        return importlib.import_module("jlu_toolkit.campus")
    except ImportError:
        return None


def register_check(site_id: str, fn: CheckFn) -> None:
    site(site_id)
    _checks[site_id] = fn


def find_check(site_id: str) -> Optional[CheckFn]:
    if site_id in _checks:
        return _checks[site_id]
    fn = getattr(_campus(), f"check_{site_id}", None)
    return fn if callable(fn) else None


def check(site_id: str) -> dict:
    """按需（用户触发）跑一次存活检查；没有钩子时状态不变。"""
    fn = find_check(site_id)
    if fn is None:
        return status(site_id)
    try:
        r = fn(client(site_id)) or {}
        li, reason = r.get("logged_in"), str(r.get("reason", ""))
    except SiteSessionExpired:
        # campus.check_* 已 mark_expired
        return status(site_id)
    except jwxt.NetworkError as e:
        li, reason = None, f"网络不可达：{e}"
    except Exception as e:  # noqa: BLE001
        li, reason = None, f"{type(e).__name__}: {e}"
    if site_id != "jwxt" and not _secret(site_id).exists() and li is not True:
        return status(site_id)
    _write_status(site_id, OK if li is True else EXPIRED if li is False else UNKNOWN, reason)
    return status(site_id)


def register_vpn_url(fn: Callable[[str], str]) -> None:
    global _vpn_impl
    _vpn_impl = fn


def vpn_url(url: str) -> str:
    """把校内 URL 换成经 vpn.jlu.edu.cn 访问的 URL。

    实现默认取 jlu_toolkit.campus.vpn_url；也可 register_vpn_url() 覆盖。
    """
    fn = _vpn_impl or getattr(_campus(), "vpn_url", None)
    if not callable(fn):
        raise NotImplementedError("vpn_url 尚未实现：等待 vpn.jlu.edu.cn URL 格式探测结果")
    return fn(url)


def site_dict(s: Site) -> dict:
    return asdict(s)


# ───────── CAS 单点登录持久化 ─────────

def _is_cas_cookie(d: dict) -> bool:
    dom = (d.get("domain") or "").lstrip(".").lower()
    return dom == SITES["cas"].host


def save_cas_from_jar(jar) -> int:
    """把 jar 中 CAS 主机的全部 cookie 加密保存为站点 'cas'；返回保存条数（0 = 没有，不覆盖旧值）。"""
    cs = [d for d in jwxt.jar_to_list(jar) if _is_cas_cookie(d)]
    if cs:
        save_cookies("cas", cs)
    return len(cs)


def migrate_cas_from_jwxt(jar=None) -> int:
    """一次性透明迁移：站点 'cas' 为空时，从教务会话（jar 或已保存的 session）抽出 CAS 主机 cookie。

    #20 之前登录的 session.enc 往往已含 cas.jlu.edu.cn 的 cookie，但没有单独的 session-cas；
    幂等：已有 cas 会话则返回 0，不覆盖。按 domain 过滤，不假定 cookie 名。
    """
    existing = load_cookies("cas")
    if existing:
        return 0
    if jar is None:
        try:
            data = _secret("jwxt").load()
        except secure_store.SecureStoreError:
            data = None
        items = (data or {}).get("cookies") if isinstance(data, dict) else None
        if not items:
            return 0
        jar = jwxt.jar_from_list(items)
    return save_cas_from_jar(jar)


def refresh_via_cas(site_id: str, c: Optional[jwxt.JwxtClient] = None) -> bool:
    """站点会话过期时，用已保存的 CAS cookie 对该站 service 换票，成功则保存新会话。

    只适用于 auth == "cas" 且已知 service 的站点。CAS 落到登录页 → 标记 'cas' 过期，返回 False
    （UI 应显示应用内登录）。不提交任何密码/验证码。
    """
    s = site(site_id)
    if s.auth != "cas" or not s.service or site_id == "cas":
        return False
    c = c or client(site_id)
    # #20 之前的教务会话里可能已有 CAS cookie，先迁到站点 cas
    migrate_cas_from_jwxt(c.jar if any(True for _ in c.jar) else None)
    cas = load_cookies("cas")
    if not cas:
        return False
    if getattr(c, "_cas_refreshing", False):
        return False
    c._cas_refreshing = True
    try:
        for ck in jwxt.jar_from_list(cas):
            c.jar.set_cookie(ck)
        url = f"{jwxt.CAS_LOGIN}?service={urllib.parse.quote(s.service, safe='')}"
        try:
            code, html, final, _ = c._request(url, headers={"Accept": "text/html,*/*"})
        except jwxt.NetworkError:
            return False
        host = (urllib.parse.urlparse(final or "").hostname or "").lower()
        if jwxt.looks_like_login_redirect(final, html) or host == SITES["cas"].host:
            mark_expired("cas", "统一认证登录已失效")
            return False
        if host != s.host or code >= 400:
            return False
        if site_id == "jwxt":
            c.save_session()  # 同时更新 'cas'
        else:
            save_cookies(site_id, jwxt.jar_to_list(c.jar))
            save_cas_from_jar(c.jar)
        return True
    finally:
        c._cas_refreshing = False


def keepalive() -> dict:
    """一次轻量 GET 刷新教务会话（供 App 前台定时调用，约 15 分钟一次；本模块不做后台循环）。

    返回 {ok, alive, refreshed_via_cas, session}；alive=False 且 session.session_expired=True 表示需重新登录。
    """
    c = jwxt.JwxtClient()
    if not c.load_session():
        return {"ok": True, "alive": False, "refreshed_via_cas": False, "session": jwxt.session_status()}
    alive = c.session_alive()
    if alive:
        c.save_session()
    return {"ok": True, "alive": alive, "refreshed_via_cas": bool(getattr(c, "_cas_refreshed", False)),
            "session": jwxt.session_status()}
