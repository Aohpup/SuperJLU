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


SITES: Dict[str, Site] = {s.id: s for s in (
    Site("jwxt", "教务系统", "iedu.jlu.edu.cn", "cas"),
    Site("pay", "校园缴费", "ip.jlu.edu.cn", "cas"),
    Site("xsxk", "选课系统", "icourses.jlu.edu.cn", "cas"),
    Site("ilearn", "学在吉大", "ilearntec.jlu.edu.cn", "own", captcha=True),
    Site("vpn", "WebVPN", "vpn.jlu.edu.cn", "cas", vpn=False),
    Site("lib", "图书馆", "lib.jlu.edu.cn", "none"),
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
    if site_id == "jwxt":
        j = jwxt.session_status()
        state, checked, reason = j["state"], j.get("checked_at"), ""
    else:
        info = _read_all().get(site_id, {})
        has = _secret(site_id).exists()
        state = (info.get("state") or UNKNOWN) if has else MISSING
        checked, reason = info.get("checked_at"), info.get("reason", "") if has else ""
    if s.auth == "none" and state == MISSING:
        state = OK  # 无需登录的站点
    msg = MESSAGES[state] if s.auth != "none" else "无需登录"
    return {"id": s.id, "name": s.name, "host": s.host, "auth": s.auth, "vpn": s.vpn, "captcha": s.captcha,
            "state": state, "checked_at": checked, "needs_login": state in (EXPIRED, MISSING),
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
