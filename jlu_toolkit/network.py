"""HTTPS recovery shared by desktop and Android; never disables certificate checks.

urllib still owns redirects and cookies. Native transports perform exactly one hop,
so a recovered GET can select the same TLS implementation for subsequent POSTs
without replaying a password, SMS request, or an ambiguous POST response.
"""
from __future__ import annotations

import http.client
import io
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.response
from email.parser import Parser

MAX_RESPONSE = 24 * 1024 * 1024


def cause(error):
    while isinstance(error, urllib.error.URLError) and isinstance(error.reason, BaseException):
        error = error.reason
    return error


def error_kind(error):
    error = cause(error)
    if isinstance(error, ssl.SSLCertVerificationError):
        return "certificate"
    if isinstance(error, ssl.SSLError):
        return "tls"
    if getattr(error, "errno", None) == 12175:  # WinHTTP secure-channel failure
        return "tls"
    if isinstance(error, socket.gaierror):
        return "dns"
    if isinstance(error, (TimeoutError, socket.timeout)) or getattr(error, "errno", None) == 12002:
        return "timeout"
    return "connection"


def safe_to_retry(req):
    parsed = urllib.parse.urlsplit(req.full_url)
    # Sending the WeChat code is a GET in TPASS. HTTP method alone does not
    # make that request safe, nor can a single-use service ticket be replayed.
    return req.get_method() in ("GET", "HEAD") and not any(
        part in parsed.path.lower() for part in ("recheckcode", "logout", "logoff", "sendcode")
    ) and not any(key.lower() == "ticket" for key, _ in urllib.parse.parse_qsl(parsed.query))


def error_message(url, error):
    """No service/ticket, account, proxy URL, or cookie appears in the message."""
    target = urllib.parse.urlsplit(url)
    host = getattr(error, "school_host", None) or target.hostname or "服务器"
    port = getattr(error, "school_port", None) or target.port or (443 if target.scheme == "https" else 80)
    kind = error_kind(error)
    messages = {
        "tls": "HTTPS 安全连接被异常中断（TLS/SSL），尚不能判断登录是否失效",
        "certificate": "HTTPS 证书校验失败，请检查系统时间及网络证书",
        "dns": "域名解析失败，请检查当前网络",
        "timeout": "连接或响应超时，请稍后重试",
        "connection": "网络连接中断或服务器不可达，请稍后重试",
    }
    stage = getattr(error, "school_stage", "")
    return (stage + "时，" if stage else "") + f"{messages[kind]}：{host}:{port}。已保留本地数据。"


def annotate(error, req):
    target = urllib.parse.urlsplit(req.full_url)
    error.school_host = target.hostname
    error.school_port = target.port or 443
    stage = "连接学校服务"
    if "/tpass/login" in target.path:
        if req.get_method() == "POST":
            names = {k for k, _ in urllib.parse.parse_qsl((req.data or b"").decode("utf-8", "replace"))}
            stage = "提交二次认证验证码" if "WxCode" in names else "提交账号认证"
        else:
            stage = "获取统一认证页面"
    elif target.hostname == "iedu.jlu.edu.cn":
        stage = "访问教务或完成认证回跳"
    error.school_stage = stage
    return error


def native_available():
    return sys.platform == "win32" or "ANDROID_ROOT" in os.environ


def _response(req, code, raw_headers, body):
    # HTTPErrorProcessor, HTTPRedirectHandler and HTTPCookieProcessor need the
    # original duplicate headers (especially Set-Cookie), not a collapsed dict.
    headers = Parser().parsestr(raw_headers)
    response = urllib.response.addinfourl(io.BytesIO(body), headers, req.full_url, code)
    response.msg = http.client.responses.get(code, "")
    return response


def native_open(req, timeout):
    if "ANDROID_ROOT" in os.environ:
        from java import jclass
        import json
        from .secure_store import _jbytes
        try:
            result = jclass("cn.superjlu.app.SchoolHttp").request(
                req.full_url, req.get_method(), json.dumps(dict(req.header_items())),
                req.data or b"", max(1, int(timeout * 1000)))
        except Exception as error:
            # Classify the exception without returning its URL or payload.
            if "SSL" in type(error).__name__ or "SSL" in str(error):
                raise ssl.SSLError("Android HTTPS secure-channel failure") from error
            raise OSError("Android HTTPS request failed") from error
        return _response(req, result.code, str(result.headers), _jbytes(result.body))
    if sys.platform == "win32":
        return _windows_open(req, timeout)
    raise OSError("No native HTTPS transport on this platform")


def _windows_open(req, timeout):
    """WinHTTP/Schannel, with automatic cookies and redirects disabled.

    Handles, headers and payload stay in this process; no shell, temp files,
    subprocess arguments, relaxed TLS flags, or credential logging.
    """
    import ctypes as c
    from ctypes import wintypes as w

    dll = c.WinDLL("winhttp", use_last_error=True)
    handle, pointer = w.HANDLE, c.c_void_p
    signatures = {
        "WinHttpOpen": ([w.LPCWSTR, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD], handle),
        "WinHttpConnect": ([handle, w.LPCWSTR, w.WORD, w.DWORD], handle),
        "WinHttpOpenRequest": ([handle, w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, pointer, w.DWORD], handle),
        "WinHttpSetTimeouts": ([handle, c.c_int, c.c_int, c.c_int, c.c_int], w.BOOL),
        "WinHttpSetOption": ([handle, w.DWORD, pointer, w.DWORD], w.BOOL),
        "WinHttpSendRequest": ([handle, w.LPCWSTR, w.DWORD, pointer, w.DWORD, w.DWORD, c.c_size_t], w.BOOL),
        "WinHttpReceiveResponse": ([handle, pointer], w.BOOL),
        "WinHttpQueryHeaders": ([handle, w.DWORD, w.LPCWSTR, pointer, c.POINTER(w.DWORD), c.POINTER(w.DWORD)], w.BOOL),
        "WinHttpReadData": ([handle, pointer, w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
        "WinHttpCloseHandle": ([handle], w.BOOL),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = args, result

    def checked(value):
        if not value:
            raise OSError(c.get_last_error(), "Windows HTTPS request failed")
        return value

    url = urllib.parse.urlsplit(req.full_url)
    if url.scheme != "https":
        raise ValueError("Native transport requires HTTPS")
    opened = []
    try:
        # Match urllib's effective HTTPS proxy instead of introducing a second
        # WPAD/PAC decision via WINHTTP_ACCESS_TYPE_AUTOMATIC_PROXY. In
        # particular a working mobile hotspot must not be stalled by WPAD.
        proxy = urllib.request.getproxies().get("https")
        if urllib.request.proxy_bypass(url.hostname):
            proxy = None
        proxy_name = None
        if proxy:
            parsed = urllib.parse.urlsplit(proxy if "://" in proxy else "http://" + proxy)
            if parsed.username or parsed.password:
                raise OSError("Native HTTPS proxy authentication requires explicit configuration")
            if not parsed.hostname:
                raise OSError("Invalid HTTPS proxy configuration")
            proxy_name = parsed.hostname + ":" + str(parsed.port or 80)
        session = checked(dll.WinHttpOpen("SuperJLU", 3 if proxy_name else 1, proxy_name, None, 0))
        opened.append(session)
        ms = max(1, int(timeout * 1000))
        checked(dll.WinHttpSetTimeouts(session, ms, ms, ms, ms))
        connection = checked(dll.WinHttpConnect(session, url.hostname, url.port or 443, 0))
        opened.append(connection)
        path = urllib.parse.urlunsplit(("", "", url.path or "/", url.query, ""))
        request = checked(dll.WinHttpOpenRequest(connection, req.get_method(), path, None, None, None, 0x800000))
        opened.append(request)
        disable = w.DWORD(1 | 2 | 4)  # cookies, redirects, automatic authentication
        checked(dll.WinHttpSetOption(request, 63, c.byref(disable), c.sizeof(disable)))
        headers = "\r\n".join(f"{k}: {v}" for k, v in req.header_items())
        data = req.data or b""
        payload = c.create_string_buffer(data) if data else None
        checked(dll.WinHttpSendRequest(request, headers, len(headers), payload, len(data), len(data), 0))
        checked(dll.WinHttpReceiveResponse(request, None))
        size = w.DWORD(0)
        dll.WinHttpQueryHeaders(request, 22, None, None, c.byref(size), None)
        raw = c.create_unicode_buffer(size.value // c.sizeof(c.c_wchar) + 1)
        checked(dll.WinHttpQueryHeaders(request, 22, None, raw, c.byref(size), None))
        first, _, remaining = raw.value.partition("\r\n")
        code = int(first.split()[1])
        body = bytearray()
        block, count = c.create_string_buffer(65536), w.DWORD()
        deadline = time.monotonic() + timeout
        while True:
            checked(dll.WinHttpReadData(request, block, len(block), c.byref(count)))
            if not count.value:
                break
            body.extend(block.raw[:count.value])
            if len(body) > MAX_RESPONSE:
                raise OSError("HTTPS response exceeds local read limit")
            if time.monotonic() > deadline:
                raise TimeoutError("HTTPS response exceeded time budget")
        return _response(req, code, remaining, bytes(body))
    finally:
        for item in reversed(opened):
            dll.WinHttpCloseHandle(item)


class SchoolHTTPSHandler(urllib.request.HTTPSHandler):
    """At most one recovery of a safe single-hop request, with bounded timeouts."""

    def __init__(self, context, native_hosts=None, report=None, preferred_hosts=()):
        super().__init__(context=context)
        self.native_hosts = native_hosts if native_hosts is not None else set()
        self.report = report or (lambda **kw: None)
        self.preferred_hosts = frozenset(preferred_hosts)

    def https_open(self, req):
        try:
            return self._open(req)
        except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
            raise annotate(error, req)

    def _open(self, req):
        host = urllib.parse.urlsplit(req.full_url).hostname or ""
        school = host == "jlu.edu.cn" or host.endswith(".jlu.edu.cn")
        if school and (host in self.native_hosts or (host in self.preferred_hosts and native_available())):
            response = native_open(req, req.timeout)
            self.native_hosts.add(host)
            return response
        start = time.monotonic()
        try:
            return super().https_open(req)
        except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
            reason = cause(error)
            transient = isinstance(reason, (ssl.SSLError, ConnectionError, TimeoutError, http.client.HTTPException))
            if not school or not safe_to_retry(req) or not transient \
                    or isinstance(reason, ssl.SSLCertVerificationError):
                raise
            remaining = req.timeout - (time.monotonic() - start)
            if remaining < 1:
                raise
            self.report(host=host, error_kind=error_kind(error), recovered=False)
            time.sleep(min(.15, remaining / 10))
            original_timeout = req.timeout
            req.timeout = max(.1, remaining - .15)
            try:
                if native_available():
                    try:
                        response = native_open(req, req.timeout)
                    except OSError as native_error:
                        raise error from native_error
                    self.native_hosts.add(host)
                    self.report(host=host, error_kind=error_kind(error), recovered=True, transport="system")
                    return response
                return super().https_open(req)
            finally:
                req.timeout = original_timeout
