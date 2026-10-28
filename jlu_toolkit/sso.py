"""Browser handoff using fresh CAS tickets, never exported cookies.

Only a redirect Location may contain a ticket. Status records contain enums only.
The browser redeems the ticket; following its callback here would consume it.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
from typing import Optional, Tuple
from . import jwxt, sessions

SSO_TARGETS = {
    "jwxt": (jwxt.IEDU_PORTAL, jwxt.IEDU_PORTAL),
    "ilearn": ("https://jwcidentity.jlu.edu.cn/iplat-pass-jlu/thirdLogin/jlu/login",
               "https://ilearntec.jlu.edu.cn/coursecenter/main/index"),
    "vpn": ("https://vpn.jlu.edu.cn/login?cas_login=true", "https://vpn.jlu.edu.cn/"),
}
BROWSER_TARGETS = {**{k: v[1] for k, v in SSO_TARGETS.items()}, "pay": "https://ip.jlu.edu.cn/pay/"}
MESSAGES = {
    "issued": "已发起免登跳转",
    "missing": "没有可用的统一认证会话，请返回「更多 → 登录」重新登录后重试。",
    "expired": "统一认证会话已过期，请返回「更多 → 登录」重新登录后重试。",
    "network": "连接学校认证服务失败，请检查网络后重试；已保留应用内会话和本地数据。",
    "unconfirmed": "学校没有返回有效的登录票据，尚未完成免登。可重试或在网站独立登录。",
}
_status_lock = threading.Lock()


def _jlu_https(url: str) -> bool:
    try:
        u = urllib.parse.urlsplit(url or "")
        return (u.scheme == "https" and not u.username and not u.password
                and u.port in (None, 443) and not u.fragment
                and (u.hostname == "jlu.edu.cn" or (u.hostname or "").endswith(".jlu.edu.cn")))
    except ValueError:
        return False


def capable(site_id: str) -> bool:
    return site_id in SSO_TARGETS


def with_flag(url: str, flag: str = "sso=failed") -> str:
    return url + ("&" if "?" in url else "?") + flag


def _read_status() -> dict:
    try:
        obj = json.loads((jwxt.config_dir() / "browser-handoff.json").read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def last_status(site_id: str) -> dict:
    with _status_lock:
        r = _read_status().get(site_id, {})
    if not isinstance(r, dict) or r.get("state") not in MESSAGES:
        return {}
    return {"state": r["state"], "message": MESSAGES[r["state"]],
            "route": "webvpn" if r.get("route") == "webvpn" else "direct",
            "checked_at": r.get("checked_at")}


def _record(site_id: str, state: str, route: str) -> None:
    # Never persist URLs, tickets, cookies or raw exception text.
    with _status_lock:
        obj = {k: v for k, v in _read_status().items() if k in SSO_TARGETS}
        obj[site_id] = {"state": state, "route": route, "checked_at": int(time.time())}
        p = jwxt.config_dir() / "browser-handoff.json"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            temp = p.with_suffix(".tmp")
            temp.write_text(json.dumps(obj), encoding="utf-8")
            temp.replace(p)
        except OSError:
            pass  # Do not discard an issued ticket if status persistence fails.


class BrowserJumpError(Exception):
    def __init__(self, state: str):
        self.state = state
        super().__init__(MESSAGES[state])


def issue_ticket(site_id: str, route: str = "direct", c: Optional[jwxt.JwxtClient] = None) -> str:
    """Issue once, without following the callback or replaying credentials."""
    if route not in ("direct", "webvpn") or site_id not in SSO_TARGETS:
        raise ValueError("不支持的校园服务或连接方式")
    service, _ = SSO_TARGETS[site_id]

    def fail(state):
        _record(site_id, state, route)
        raise BrowserJumpError(state)

    try:
        sessions.migrate_cas_from_jwxt()
    except Exception:
        pass
    cas = sessions.load_cookies("cas")
    if not cas:
        fail("missing")
    # CAS is public. App VPN cookies do not authenticate the external browser.
    c = c or jwxt.JwxtClient(timeout=12, route="direct")
    c.jar = jwxt.jar_from_list(cas)
    c._rebuild_opener()
    url = f"{jwxt.CAS_LOGIN}?service={urllib.parse.quote(service, safe='')}"
    try:
        code, html, final, _ = c._request(url, headers={"Accept": "text/html,*/*"}, allow_redirects=False)
    except jwxt.NetworkError:
        fail("network")
    try:
        u, expected = urllib.parse.urlsplit(final or ""), urllib.parse.urlsplit(service)
    except ValueError:
        fail("unconfirmed")
    query = urllib.parse.parse_qs(u.query)
    tickets = query.get("ticket", [])
    exact_service = (u.scheme, u.netloc, u.path) == (expected.scheme, expected.netloc, expected.path)
    expected_query = urllib.parse.parse_qs(expected.query)
    if (code in (301, 302, 303, 307, 308) and _jlu_https(final) and exact_service
            and len(tickets) == 1 and tickets[0].startswith("ST-")
            and all(query.get(k) == v for k, v in expected_query.items())):
        try:
            sessions.save_cas_from_jar(c.jar)
        except Exception:
            pass
        if route == "webvpn" and site_id != "vpn":
            from .campus import vpn_url
            final = vpn_url(final)
        _record(site_id, "issued", route)
        return final
    if jwxt.looks_like_login_redirect(final, html):
        try:
            sessions.mark_expired("cas", "统一认证登录已失效")
        except OSError:
            pass
        fail("expired")
    fail("unconfirmed")


def jump_url(site_id: str, c: Optional[jwxt.JwxtClient] = None) -> Tuple[str, bool]:
    """Legacy helper; new UI reports errors instead of silently falling back."""
    try:
        return issue_ticket(site_id, c=c), True
    except BrowserJumpError:
        return with_flag(SSO_TARGETS[site_id][1]), False
