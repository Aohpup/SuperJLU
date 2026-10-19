"""校园站点探测与会话存活钩子（只读 GET）。

供 `jlu_toolkit.sessions` 自动导入：
  - check_<id>(session) -> {"logged_in": True|False|None, "reason": str}
    session 是带该站 cookie 的 JwxtClient；只用 session._request 发一次无副作用 GET。
    判定已过期时：sessions.mark_expired(id, reason) 然后 raise sessions.SiteSessionExpired(id)。
    其他异常由 sessions.check 记为 unknown。
  - vpn_url(url) -> str
    把校内 http(s) URL 写成经 vpn.jlu.edu.cn 的 WebVPN 地址。

站点 id：jwxt / pay / xsxk / ilearn / vpn / lib。

本模块绝不提交登录、缴费、选课或退课。--probe 只输出可达性/重定向/登录类型/
候选只读接口字段名与计数，不打印任何个人数值。
"""
from __future__ import annotations

import json
import re
import urllib.parse
from binascii import hexlify
from typing import Any, Optional

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
try:
    from cryptography.hazmat.decrepit.ciphers.modes import CFB as _CFB
except ImportError:  # pragma: no cover
    from cryptography.hazmat.primitives.ciphers.modes import CFB as _CFB

from . import jwxt

# ───────── 常量（探测结论，2026-10-15 校园网实测） ─────────

PAY_HOME = "https://ip.jlu.edu.cn/pay/?menu=home"
PAY_LOGIN = "https://ip.jlu.edu.cn/pay/"
XSXK_NOW = "https://icourses.jlu.edu.cn/xsxk/web/now"
XSXK_INDEX = "https://icourses.jlu.edu.cn/xsxk/profile/index.html"
ILEARN_MAIN = "https://ilearntec.jlu.edu.cn/coursecenter/main/index"
VPN_PORTAL = "https://vpn.jlu.edu.cn/"
LIB_HOME = "https://lib.jlu.edu.cn/"
LIB_LOGIN = "https://lib.jlu.edu.cn/login"

# 当前 WebVPN 主机密文密钥（AES-128-CFB，key=iv）。
# 已用公开 OA 链接前缀校验：Didida1127Didida → oa.jlu.edu.cn。
# 历史密钥：wrdvpnisthebest! / jluvpnisthegood!（仍可解码旧链接）。
VPN_BASE = "https://vpn.jlu.edu.cn"
# 2026-10-18 公共 /login?cas_login=true 跳转；用已知 cas 主机校验 AES-CFB 编码。
VPN_KEY = b"HqOq4/z3mX/~(W77"
VPN_KEY_LEGACY = (b"Didida1127Didida", b"jluvpnisthegood!", b"wrdvpnisthebest!")

_SITES_PROBE = (
    ("pay", PAY_LOGIN, "校园缴费"),
    ("xsxk", XSXK_INDEX, "选课"),
    ("ilearn", "https://ilearntec.jlu.edu.cn/", "学在吉大"),
    ("vpn", VPN_PORTAL, "WebVPN"),
    ("lib", LIB_HOME, "图书馆"),
)


def _expire(site_id: str, reason: str) -> None:
    from . import sessions

    sessions.mark_expired(site_id, reason)
    raise sessions.SiteSessionExpired(site_id)


def _get(session, url: str, headers: Optional[dict] = None) -> tuple[int, str, str]:
    code, text, final, _ = session._request(url, headers=headers)
    return code, text or "", final or url


def _host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower()


def _path(url: str) -> str:
    return urllib.parse.urlparse(url).path or ""


# ───────── vpn_url ─────────

def _encrypt_host(hostname: str, key: bytes = VPN_KEY) -> str:
    key16 = key[:16]
    enc = Cipher(algorithms.AES(key16), _CFB(key16)).encryptor()
    ct = enc.update(hostname.encode("utf-8")) + enc.finalize()
    return hexlify(key16).decode("ascii") + hexlify(ct).decode("ascii")


def vpn_url(url: str) -> str:
    """校内 URL → `https://vpn.jlu.edu.cn/{scheme}/{iv+ct hex}{path}?{query}`。

    主机名用学校公共入口的 AES-128-CFB 参数编码。已是 vpn 域名则原样返回。
    """
    p = urllib.parse.urlparse((url or "").strip())
    if not p.scheme or not p.hostname:
        raise ValueError(f"vpn_url 需要绝对 URL，收到：{url!r}")
    host = p.hostname.lower()
    if host in ("vpn.jlu.edu.cn", "vpns.jlu.edu.cn", "webvpn.jlu.edu.cn"):
        return url
    scheme = p.scheme.lower()
    if p.port and not ((scheme == "https" and p.port == 443) or (scheme == "http" and p.port == 80)):
        scheme = f"{scheme}-{p.port}"
    token = _encrypt_host(host)
    out = f"{VPN_BASE}/{scheme}/{token}{p.path or '/'}"
    if p.query:
        out += "?" + p.query
    if p.fragment:
        out += "#" + p.fragment
    return out


def vpn_url_decode(url: str) -> str:
    """WebVPN URL → 原始 URL（测试/调试用；支持当前与历史密钥）。"""
    p = urllib.parse.urlparse(url)
    segs = (p.path or "/").split("/")  # ['', scheme, token, ...path]
    if len(segs) < 3 or not segs[1] or not segs[2]:
        raise ValueError("不是可识别的 WebVPN 路径")
    scheme_part, token, rest = segs[1], segs[2], segs[3:]
    scheme = scheme_part.split("-")[0]
    port = None
    if "-" in scheme_part:
        try:
            port = int(scheme_part.split("-", 1)[1])
        except ValueError:
            pass
    raw = bytes.fromhex(token)
    iv, ct = raw[:16], raw[16:]
    host = None
    for key in (VPN_KEY, *VPN_KEY_LEGACY):
        try:
            dec = Cipher(algorithms.AES(key[:16]), _CFB(iv)).decryptor()
            cand = (dec.update(ct) + dec.finalize()).decode("utf-8")
            if "." in cand and " " not in cand:
                host = cand
                break
        except Exception:
            continue
    if not host:
        raise ValueError("无法解码 WebVPN 主机密文")
    netloc = host if port is None else f"{host}:{port}"
    path = ("/" + "/".join(rest)) if rest else "/"
    return urllib.parse.urlunparse((scheme, netloc, path, "", p.query, p.fragment))


# ───────── check_* ─────────

def check_jwxt(session) -> dict:
    """教务：GET 课表入口，落在 CAS 登录页则过期。"""
    code, text, final = _get(session, jwxt.REF_SCHEDULE)
    if _host(final) != jwxt.IEDU_HOST or code not in (200, 302) or jwxt.looks_like_login_redirect(final, text):
        _expire("jwxt", "课表入口重定向到登录页" if jwxt.looks_like_login_redirect(final, text) else f"status={code} host={_host(final)}")
    return {"logged_in": True, "reason": f"iedu ok status={code}"}


def check_pay(session) -> dict:
    """校园缴费：GET ?menu=home；未登录会 alert「请先登录」并跳回登录页。"""
    code, text, final = _get(session, PAY_HOME)
    low = text.lower()
    if (
        "请先登录" in text
        or "页面超时" in text
        or 'name="pwd"' in low
        or "img_safecode" in low
    ):
        _expire("pay", "缴费页要求重新登录")
    if code not in (200, 302):
        return {"logged_in": None, "reason": f"status={code}"}
    return {"logged_in": True, "reason": "pay home reachable without login form"}


def check_xsxk(session) -> dict:
    """选课：GET /xsxk/web/now（需 token）；未登录返回错误页 HTML，登录后为 JSON。"""
    code, text, final = _get(
        session,
        XSXK_NOW,
        headers={
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": XSXK_INDEX,
        },
    )
    stripped = (text or "").lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            data = json.loads(stripped)
        except ValueError:
            return {"logged_in": None, "reason": "non-json body starting with brace"}
        code_v = str(data.get("code", ""))
        if code_v in ("401", "402", "403"):
            _expire("xsxk", f"选课 API code={code_v}")
        if code_v == "200" or "data" in data:
            return {"logged_in": True, "reason": f"xsxk /web/now code={code_v or 'ok'}"}
        return {"logged_in": None, "reason": f"xsxk json code={code_v}"}
    # HTML 错误页 / 回登录页
    if "profile/index.html" in (final or "") or "错误" in (text[:200] if text else "") or "loginForm" in text:
        _expire("xsxk", "选课 /web/now 未返回 JSON（未登录）")
    if code not in (200, 302):
        return {"logged_in": None, "reason": f"status={code}"}
    _expire("xsxk", "选课 /web/now 返回非 JSON")


def check_ilearn(session) -> dict:
    """学在吉大：GET coursecenter/main/index；未登录会经 ilearn cas-server 跳到 cas.jlu.edu.cn。"""
    code, text, final = _get(session, ILEARN_MAIN)
    host = _host(final)
    path = _path(final)
    if "cas.jlu.edu.cn" in host or "cas-server" in path or jwxt.looks_like_login_redirect(final, text):
        _expire("ilearn", "学在吉大跳到 CAS/cas-server")
    if "login" in path.lower() and "coursecenter" not in path.lower():
        _expire("ilearn", f"落到登录路径 {path}")
    if code not in (200, 302):
        return {"logged_in": None, "reason": f"status={code}"}
    if "coursecenter" in path or "ilearntec.jlu.edu.cn" in host or "ilearn.jlu.edu.cn" in host:
        return {"logged_in": True, "reason": f"coursecenter status={code}"}
    return {"logged_in": None, "reason": f"unexpected final host={host} path={path}"}


def check_vpn(session) -> dict:
    """WebVPN：GET 门户。校园网内若被本地代理劫持可能不可达 → unknown。"""
    try:
        code, text, final = _get(session, VPN_PORTAL)
    except jwxt.NetworkError as e:
        return {"logged_in": None, "reason": f"vpn unreachable: {e}"}
    host = _host(final)
    low = (text or "")[:8000].lower()
    if "cas.jlu.edu.cn" in host or jwxt.looks_like_login_redirect(final, text):
        _expire("vpn", "WebVPN 跳到统一身份认证")
    if _path(final).rstrip("/") == "/login" or "统一身份认证登录" in text \
            or (any(k in (text or "")[:4000] for k in ("统一身份认证", "师生普通登录", "管理员登录")) and "password" in low):
        _expire("vpn", "WebVPN 登录页")
    if code not in (200, 302):
        return {"logged_in": None, "reason": f"status={code}"}
    if host.endswith("vpn.jlu.edu.cn") or host.endswith("vpns.jlu.edu.cn"):
        return {"logged_in": True, "reason": f"vpn portal status={code}"}
    return {"logged_in": None, "reason": f"unexpected host={host}"}


def check_lib(session) -> dict:
    """图书馆：门户匿名可访问；用首页 isLogin 判断个人 SSO 是否有效。"""
    code, text, final = _get(session, LIB_HOME)
    if code not in (200, 302):
        return {"logged_in": None, "reason": f"status={code}"}
    m = re.search(r"isLogin\s*=\s*(true|false)", text or "", re.I)
    if not m:
        return {"logged_in": None, "reason": "homepage missing isLogin"}
    if m.group(1).lower() == "true":
        return {"logged_in": True, "reason": "lib isLogin=true"}
    # 门户无需登录；无个人 SSO 时不记过期（registry auth=none）
    return {"logged_in": None, "reason": "lib isLogin=false (portal public; no personal SSO)"}


# ───────── 匿名探测（campus --probe） ─────────

def _login_type(final: str, text: str) -> str:
    blob = (final or "") + "\n" + (text or "")[:20000]
    if re.search(r"cas\.jlu\.edu\.cn|/tpass/login|authserver", blob, re.I):
        return "cas"
    if re.search(r"captcha|验证码|imgcode|img_safecode|verifyCode|webLogin", blob, re.I) and re.search(
        r"password|pwd|passwd", blob, re.I
    ):
        return "own+captcha"
    if re.search(r'type=["\']password["\']|name=["\']pwd["\']|/auth/login', blob, re.I):
        return "own"
    return "none_or_unknown"


def _cas_reusable(login_type: str, final: str, text: str) -> str:
    if login_type == "cas":
        return "yes"
    if "cas.jlu.edu.cn" in (final + text) or "cas-server" in (final + text):
        return "maybe"
    if login_type.startswith("own"):
        return "no"
    return "unknown"


def _api_candidates(site_id: str, text: str) -> list[str]:
    """从 HTML/JS 抽出只读向候选路径（字段名级，无个人数据）。"""
    found = sorted(set(re.findall(r'["\'](/[a-zA-Z0-9_./?=&%-]{3,})["\']', text or "")))
    interesting = [
        u
        for u in found
        if re.search(
            r"api|auth|user|info|balance|fee|elective|student|course|homework|assignment|loan|borrow|captcha|now|login",
            u,
            re.I,
        )
    ]
    presets = {
        "pay": [
            "/pay/?menu=home",
            "/pay/img_safecode.php",
            "/pay/ (POST menu=chklogin — 探测仅记录，不调用)",
        ],
        "xsxk": [
            "/xsxk/auth/captcha",
            "/xsxk/web/now",
            "/xsxk/web/studentInfo",
            "/xsxk/elective/user",
            "/xsxk/elective/batch/confirm",
        ],
        "ilearn": [
            "/user/webLoginV2",
            "/user/checkSchoolEnable",
            "/coursecenter/main/index",
            "https://ilearn.jlu.edu.cn/cas-server/login",
            "https://ilearn.jlu.edu.cn/coursecenter/",
        ],
        "lib": [
            "/login → cas.jlu.edu.cn/tpass/login?service=.../sso/login/3rd/30569",
            "homepage isLogin flag",
            "/page/ck/library_first_banner",
        ],
        "vpn": [
            "https://vpn.jlu.edu.cn/ (CAS 师生普通登录)",
            "vpn_url rewrite /https/<token>/...",
        ],
    }
    out = list(presets.get(site_id, []))
    for u in interesting[:20]:
        if u not in out:
            out.append(u)
    return out[:30]


def probe_site(session, site_id: str, url: str, name: str) -> dict[str, Any]:
    """对单站做匿名只读探测，不打印个人数值。"""
    rep: dict[str, Any] = {
        "id": site_id,
        "name": name,
        "url": url,
        "reachable": False,
        "status": None,
        "final_host": None,
        "redirects_to_cas": False,
        "login_type": None,
        "cas_reusable": "unknown",
        "candidate_readonly": [],
        "vpn_url_sample": None,
        "needs_login_to_confirm": [],
        "error": None,
    }
    try:
        rep["vpn_url_sample"] = vpn_url(url)
    except Exception as e:  # noqa: BLE001
        rep["vpn_url_sample"] = f"error:{type(e).__name__}"
    try:
        code, text, final = _get(session, url)
    except jwxt.NetworkError as e:
        rep["error"] = str(e)[:200]
        rep["needs_login_to_confirm"] = ["portal reachable off-campus / without local proxy"]
        return rep
    rep["reachable"] = True
    rep["status"] = code
    rep["final_host"] = _host(final)
    rep["final_path"] = _path(final)
    rep["redirects_to_cas"] = "cas.jlu.edu.cn" in (final or "") or jwxt.looks_like_login_redirect(final, text)
    rep["login_type"] = _login_type(final, text)
    rep["cas_reusable"] = _cas_reusable(rep["login_type"], final, text)
    rep["title"] = (re.search(r"<title[^>]*>(.*?)</title>", text or "", re.I | re.S) or [None, ""])[1]
    if isinstance(rep["title"], str):
        rep["title"] = re.sub(r"\s+", " ", rep["title"]).strip()[:80]
    rep["candidate_readonly"] = _api_candidates(site_id, text)
    # site-specific enrich
    if site_id == "pay":
        rep["login_type"] = "own+captcha"
        rep["cas_reusable"] = "no"
        rep["notes"] = "fields: card,pwd,imgcode; captcha GET img_safecode.php; unauth home → 请先登录"
        rep["needs_login_to_confirm"] = ["balance/usage field names after login"]
    elif site_id == "xsxk":
        rep["login_type"] = "own+captcha"
        rep["cas_reusable"] = "no"
        # pull index.min.js paths anonymously
        try:
            _, js, _ = _get(session, "https://icourses.jlu.edu.cn/xsxk/profile/js/index.min.js")
            rep["candidate_readonly"] = _api_candidates("xsxk", js)
        except jwxt.NetworkError:
            pass
        rep["notes"] = "POST /auth/login (AES password+captcha); token in header; casServerLogoutUrl optional"
        rep["needs_login_to_confirm"] = ["studentInfo / elective/user JSON field names"]
    elif site_id == "ilearn":
        # coursecenter forces cas-server bridge
        try:
            c2, t2, f2 = _get(session, ILEARN_MAIN)
            rep["coursecenter_final_host"] = _host(f2)
            rep["coursecenter_login_type"] = _login_type(f2, t2)
            if "cas.jlu.edu.cn" in (f2 + t2) or "cas-server" in (f2 or ""):
                rep["login_type"] = "own+captcha|cas-bridge"
                rep["cas_reusable"] = "maybe"
        except jwxt.NetworkError as e:
            rep["coursecenter_error"] = str(e)[:120]
        rep["notes"] = "SPA login /user/webLoginV2; coursecenter → ilearn cas-server → cas.jlu.edu.cn"
        rep["needs_login_to_confirm"] = ["homework/assignment/deadline API paths after login"]
    elif site_id == "vpn":
        rep["login_type"] = "cas"
        rep["cas_reusable"] = "yes"
        rep["notes"] = "official: 师生普通登录=统一身份认证; on-campus probe often blocked by local fake-ip proxy"
        rep["needs_login_to_confirm"] = ["resource list JSON after VPN login"]
    elif site_id == "lib":
        m = re.search(r"isLogin\s*=\s*(true|false)", text or "", re.I)
        rep["isLogin"] = m.group(1).lower() if m else None
        rep["login_type"] = "none(portal)/cas(personal)"
        rep["cas_reusable"] = "yes"
        try:
            _, lt, lf = _get(session, LIB_LOGIN)
            svc = re.findall(r"cas\.jlu\.edu\.cn[^\"'\\s]*", lt)
            rep["cas_service"] = svc[:2]
            rep["login_redirect_host"] = _host(lf)
        except jwxt.NetworkError as e:
            rep["login_error"] = str(e)[:120]
        rep["needs_login_to_confirm"] = ["loan/due-date API field names"]
    return rep


def probe(session=None) -> dict:
    """探测全部校园站点（匿名 GET）。返回结构报告，无个人数值。"""
    client = session or jwxt.JwxtClient()
    sites = [probe_site(client, sid, url, name) for sid, url, name in _SITES_PROBE]
    # also summarize jwxt reachability lightly
    jw: dict[str, Any] = {"id": "jwxt", "name": "教务", "url": jwxt.REF_SCHEDULE}
    try:
        code, text, final = _get(client, "https://iedu.jlu.edu.cn/")
        jw.update(
            {
                "reachable": True,
                "status": code,
                "final_host": _host(final),
                "login_type": "cas",
                "cas_reusable": "yes",
                "redirects_to_cas": jwxt.looks_like_login_redirect(final, text) or "cas.jlu.edu.cn" in (final or ""),
                "candidate_readonly": ["jwapp schedule/grades (existing jwxt module)"],
                "vpn_url_sample": vpn_url("https://iedu.jlu.edu.cn/"),
                "needs_login_to_confirm": [],
            }
        )
    except jwxt.NetworkError as e:
        jw.update({"reachable": False, "error": str(e)[:200], "login_type": "cas", "cas_reusable": "yes"})
    return {
        "ok": True,
        "vpn_key": VPN_KEY.decode("ascii"),
        "vpn_format": "https://vpn.jlu.edu.cn/{scheme}/{hex(iv+AES-CFB(hostname))}{path}?{query}",
        "sites": [jw] + sites,
    }


def probe_table(report: dict) -> str:
    """把 probe() 结果收成一行一站的可读表。"""
    lines = [
        f"{'id':<8}{'login':<22}{'CAS reuse':<10}{'reach':<6}{'candidates (head)'}",
        "-" * 72,
    ]
    for s in report.get("sites") or []:
        cand = ", ".join((s.get("candidate_readonly") or [])[:3]) or "-"
        lines.append(
            f"{s.get('id','?'):<8}{str(s.get('login_type') or '?'):<22}"
            f"{str(s.get('cas_reusable') or '?'):<10}"
            f"{'yes' if s.get('reachable') else 'no':<6}{cand[:40]}"
        )
    return "\n".join(lines)
