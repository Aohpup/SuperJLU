"""Per-user CAS-only transport; never fetches a ticket's campus destination.

The phone keeps academic cookies. The server keeps CAS cookies in memory and
returns a single response at a time so the phone can redeem service tickets.
"""
from __future__ import annotations

import base64
import collections
import http.cookiejar
import http.cookies
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from adapter import jwxt

CAS = "https://cas.jlu.edu.cn"
PATHS = {"/tpass/login", "/tpass/code", "/tpass/mobilecode", "/tpass/recheckcode"}
ERROR_COOKIES = {"mobile_error_info", "recheck_mobile_error_info"}


class CasTransportError(ValueError):
    pass


def target_url(url):
    if not isinstance(url, str) or len(url) > 4096 or re.search(r"[\\\x00-\x20]", url):
        raise CasTransportError("学校认证地址无效")
    u = urllib.parse.urlsplit(url)
    if (u.scheme != "https" or u.netloc not in {"cas.jlu.edu.cn", "cas.jlu.edu.cn:443"}
            or u.path not in PATHS or u.fragment):
        raise CasTransportError("仅支持固定学校认证入口")
    query = urllib.parse.parse_qs(u.query, keep_blank_values=True, max_num_fields=12)
    for service in query.get("service", []):
        p = urllib.parse.urlsplit(service)
        if (p.scheme != "https" or p.netloc != "iedu.jlu.edu.cn" or p.fragment
                or not (p.path == "/" or p.path.startswith("/jwapp/"))
                or "ticket" in urllib.parse.parse_qs(p.query)):
            raise CasTransportError("教务认证回跳地址无效")
    return u, query


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class CasFlow:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        # CAS is public. Explicitly exclude system proxies, including a local
        # proxy left running by desktop software; keep normal TLS validation.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            NoRedirect(), urllib.request.HTTPCookieProcessor(self.jar))
        self.touched = time.monotonic()
        self.created = self.touched

    def request(self, body):
        url = body.get("url")
        u, _ = target_url(url)
        method = body.get("method", "GET")
        if method not in {"GET", "POST"} or method == "POST" and u.path != "/tpass/login":
            raise CasTransportError("不支持该学校认证操作")
        data = body.get("data", "")
        if not isinstance(data, str) or len(data) > 16384 or method == "GET" and data:
            raise CasTransportError("学校认证请求格式无效")
        headers = body.get("headers", {})
        if not isinstance(headers, dict):
            raise CasTransportError("学校认证请求头无效")
        # Only UI preferences cross this boundary. Neither caller supplied
        # session cookies nor cloud CAS/TGC cookies are copied to the phone.
        cookie = next((v for k, v in headers.items() if k.lower() == "cookie"), "")
        if not isinstance(cookie, str) or len(cookie) > 4096:
            raise CasTransportError("认证偏好格式无效")
        for item in cookie.split(";"):
            name, sep, value = item.strip().partition("=")
            valid = ((name == "last_select_type" and value in {"mobile_login", "password_login"})
                     or (name == "is_mobile" and value == "true")
                     or (name == "recheck_djsendtime" and bool(re.fullmatch(r"\d{1,16}", value))))
            if sep and valid:
                self.jar.set_cookie(http.cookiejar.Cookie(0, name, value, None, False,
                    "cas.jlu.edu.cn", False, False, "/tpass", True, True, None, True,
                    None, None, {}, False))
        req_headers = {"User-Agent": jwxt.UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                       "Accept": "image/*" if body.get("binary") else "text/html,application/json,*/*",
                       "Referer": CAS + "/tpass/login", "Cache-Control": "no-cache"}
        if method == "POST":
            req_headers.update({"Origin": CAS, "Content-Type": "application/x-www-form-urlencoded"})
        if u.path.endswith(("mobilecode", "recheckcode")):
            req_headers["X-Requested-With"] = "XMLHttpRequest"
        request = urllib.request.Request(url, data=data.encode() if method == "POST" else None,
                                         method=method, headers=req_headers)
        try:
            response = self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as e:
            response = e
        except (urllib.error.URLError, TimeoutError):
            raise CasTransportError("云端暂时无法连接学校认证，请稍后重试") from None
        with response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise CasTransportError("学校认证响应过大，已停止读取")
            result_headers = {"Content-Type": response.headers.get("Content-Type", "")}
            location = response.headers.get("Location")
            if location:
                resolved = urllib.parse.urljoin(url, location)
                p = urllib.parse.urlsplit(resolved)
                if (p.scheme != "https" or p.netloc not in {"cas.jlu.edu.cn", "iedu.jlu.edu.cn"}
                        or re.search(r"[\\\x00-\x20]", resolved)):
                    raise CasTransportError("学校返回了不支持的认证跳转")
                result_headers["Location"] = resolved
            safe_cookies = []
            for line in response.headers.get_all("Set-Cookie", []):
                parsed = http.cookies.SimpleCookie()
                try:
                    parsed.load(line)
                except http.cookies.CookieError:
                    continue
                for name, item in parsed.items():
                    if name in ERROR_COOKIES and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", item.value):
                        safe_cookies.append(name + "=" + item.value + "; Path=/tpass")
            return {"statusCode": response.status, "header": result_headers,
                    "cookies": safe_cookies, "binary": bool(body.get("binary")),
                    "data": base64.b64encode(raw).decode() if body.get("binary") else
                            raw.decode(response.headers.get_content_charset() or "utf-8", errors="replace")}


class CasFlows:
    def __init__(self):
        self.flows = collections.OrderedDict()
        self.requests = collections.deque()
        self.last_sms = 0
        self.last_verify = 0
        self.last_recheck = 0

    def clear(self):
        self.flows.clear()

    def close(self, flow):
        self.flows.pop(flow, None)

    def request(self, body):
        now = time.monotonic()
        _, query = target_url(body.get("url"))
        path = urllib.parse.urlsplit(body["url"]).path
        if path == "/tpass/mobilecode" and query.get("method") not in (["isPhone"], ["isPhone2"]):
            raise CasTransportError("不支持该短信认证操作")
        while self.requests and self.requests[0] < now - 60:
            self.requests.popleft()
        if len(self.requests) >= 120:
            raise CasTransportError("认证操作过于频繁，请稍后再试")
        self.requests.append(now)
        self.flows = collections.OrderedDict((k, v) for k, v in self.flows.items() if now - v.created < 7200)
        flow_id = body.get("flow", "")
        if flow_id and (not isinstance(flow_id, str) or flow_id not in self.flows):
            raise CasTransportError("云端认证会话已过期，请重新开始登录")
        if not flow_id:
            while len(self.flows) >= 6:
                self.flows.popitem(last=False)
            flow_id = secrets.token_urlsafe(24)
            self.flows[flow_id] = CasFlow()
        flow = self.flows[flow_id]
        if query.get("method") == ["isPhone"]:
            if self.last_sms and now - self.last_sms < 120:
                raise CasTransportError("请等待两分钟后再发送短信验证码")
            self.last_sms = now
        if query.get("method") == ["isPhone2"]:
            if self.last_verify and now - self.last_verify < 2:
                raise CasTransportError("请稍候再校验短信验证码")
            self.last_verify = now
        if path == "/tpass/recheckcode":
            if self.last_recheck and now - self.last_recheck < 60:
                raise CasTransportError("请等待一分钟后再发送学校微信验证码")
            self.last_recheck = now
        flow.touched = now
        result = flow.request(body)
        return {**result, "flow": flow_id}


def anonymous_smoke():
    """Run the actual transport, without credentials, and emit safe flags."""
    flows = CasFlows()
    try:
        page = flows.request({"url": CAS + "/tpass/login?service=https%3A%2F%2Fiedu.jlu.edu.cn%2F"})
        text = page["data"]
        image = flows.request({"url": CAS + "/tpass/code?" + str(time.time_ns()),
                               "flow": page["flow"], "binary": True})
        raw = base64.b64decode(image["data"])
        return {"event": "cas_transport_smoke", "login_status": page["statusCode"],
                "login_form": bool(re.search(r'<form\b[^>]*\bid=["\']loginForm["\']', text, re.I)),
                "lt_present": bool(jwxt._extract_lt(text)),
                "captcha_status": image["statusCode"],
                "captcha_image": raw.startswith((b"\xff\xd8", b"\x89PNG")),
                "system_proxy_used": False, "school_destination_requested": False}
    except Exception as e:
        return {"event": "cas_transport_smoke", "error_type": type(e).__name__}
    finally:
        flows.clear()
