"""Anonymous startup checks. Never log login HTML, cookies or token values."""
import concurrent.futures
import json
import os
import re
import ssl
import time
import http.cookiejar
import hashlib
import html
import socket
import io
import gzip
import email.message
from types import SimpleNamespace
import urllib.error
import urllib.parse
import urllib.request

TARGETS = {"wechat": "https://api.weixin.qq.com/sns/jscode2session",
           "cas": "https://cas.jlu.edu.cn/tpass/login", "school": "https://iedu.jlu.edu.cn",
           "vpn": "https://vpn.jlu.edu.cn/",
           "vpn_login": "https://vpn.jlu.edu.cn/login",
           "vpn_cas": "https://vpn.jlu.edu.cn/login?cas_login=true",
           # Observed by following the official portal's CAS login link on
           # 2026-10-17; this is a public login page, never an access credential.
           "vpn_official_cas": "https://vpn.jlu.edu.cn/https/48714f71342f7a336d582f7e285737375ccd605402c6dbebb4864756174f/tpass/login?service=https://vpn.jlu.edu.cn/login?cas_login%3Dtrue"}


def safe_error_text(value):
    """Only used for an anonymous error page, never a successful login page."""
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", " ", value, flags=re.I | re.S)
    value = html.unescape(re.sub(r"<[^>]*>", " ", value))
    value = re.sub(r"https?://[^\s<>\"']+", "[url]", value)
    value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[ip]", value)
    value = re.sub(r"(?i)\b(?:token|ticket|password|secret|session|csrf|nonce)\b\s*[:=]\s*[^\s,;]+", "[redacted]", value)
    value = re.sub(r"\b[A-Za-z0-9_-]{24,}\b", "[id]", value)
    return re.sub(r"\s+", " ", value).strip()[:1600]


def tls_probe(host):
    """Validate the named school's certificate and record network stage only."""
    result = {"target": host, "event": "network_tls_probe"}
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        result["dns_addresses"] = sorted({entry[4][0] for entry in addresses})
        with socket.create_connection((host, 443), timeout=6) as sock:
            result["tcp_connected"] = True
            with ssl.create_default_context().wrap_socket(sock, server_hostname=host) as conn:
                cert = conn.getpeercert()
                result.update({"tls_verified": True, "tls_version": conn.version(),
                               "issuer": [v for row in cert.get("issuer", ()) for k, v in row if k in ("organizationName", "commonName")]})
    except Exception as error:
        result["error_type"] = type(error).__name__
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def inspect_response(response, url):
    raw = response.read(65536)
    decoded = raw
    if raw.startswith(b'\x1f\x8b'):
        try:
            decoded = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(65536)
        except (OSError, EOFError):
            decoded = b''
    text = decoded.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    status = response.status
    title = re.search(r"<title[^>]*>([^<]*)</title>", text, re.I)
    # Titles may be set by remote content. Emit only known generic descriptions.
    known_titles = {"Forbidden", "403 Forbidden", "Access Denied", "404 Not Found", "智慧校园", "网页版VPN系统"}
    safe_title = title.group(1).strip() if title else ""
    result = {"status": status, "http_status": status,
            "encoding": response.headers.get("Content-Encoding"),
            "content_type": response.headers.get("Content-Type"),
            "response_bytes_read": len(raw),
            "page_title": safe_title if safe_title in known_titles else None,
            "cas_login_form": bool(re.search(r'<form\b[^>]*\bid=[\"\']loginForm[\"\']', text, re.I)),
            "webvpn_login_link": "cas_login=true" in text,
            "wechat_redirect_script": "wxRedirect=" in text,
            "access_denied_page": bool(re.search(r"access denied|403 forbidden|request blocked|访问被拒绝|禁止访问", text, re.I)),
            "campus_navigation_redirect": "nic.jlu.edu.cn/info/1016/2037.htm" in text,
            "final_host": urllib.parse.urlsplit(url).hostname}
    if status in (403, 451):
        result.update({"error_page_text": safe_error_text(text),
                       "body_sha256": hashlib.sha256(raw).hexdigest(),
                       "server": safe_error_text(response.headers.get("Server", "")),
                       "via": safe_error_text(response.headers.get("Via", "")),
                       "error_title": safe_error_text(title.group(1)) if title else None})
    return result

def probe(item):
    name, url = item
    chain = []
    deadline = time.monotonic() + 12
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        allowed = {urllib.parse.urlsplit(url).hostname, "cas.jlu.edu.cn", "vpn.jlu.edu.cn"}
        for _ in range(5):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"target": name, "error_type": "TimeoutError", "chain": chain}
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                                                          "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                                                          "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
            try:
                response = opener.open(request, timeout=min(8, remaining))
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status = response.status
                chain.append({"host": urllib.parse.urlsplit(url).hostname, "status": status,
                              "proxied_cas": "/https/" in urllib.parse.urlsplit(url).path and "/tpass/login" in urllib.parse.urlsplit(url).path})
                location = response.headers.get("Location")
                if status in (301, 302, 303, 307, 308) and location:
                    next_url = urllib.parse.urljoin(url, location)
                    parsed = urllib.parse.urlsplit(next_url)
                    if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.port not in (None, 443) or parsed.username or parsed.password:
                        return {"target": name, "status": status, "redirect_blocked": True, "chain": chain}
                    url = next_url
                    continue
                return {"target": name, **inspect_response(response, url), "chain": chain}
        return {"target": name, "redirect_limit": True, "chain": chain}
    except Exception as error:
        reason = getattr(error, "reason", None)
        return {"target": name, "error_type": type(error).__name__,
                "reason_type": type(reason).__name__ if reason else None,
                "http_status": getattr(error, "code", None),
                "certificate_error": getattr(reason, "verify_code", None), "chain": chain}


def browser_probe(profile, entry="vpn_cas"):
    """Compare ordinary libcurl and Chrome TLS against the same public entry.

    No account, no CAPTCHA, no proxy, normal certificate validation. Stop at
    any authentication page; never infer an authenticated session from HTTP 200.
    """
    from curl_cffi import requests, CurlOpt
    if entry not in {"vpn_cas", "vpn_official_cas"}:
        raise ValueError("Only fixed public VPN login entries are supported")
    result = {"event": "vpn_browser_probe", "client": profile, "target": entry, "chain": []}
    url = TARGETS[entry]
    deadline = time.monotonic() + 15
    try:
        with requests.Session(trust_env=False, impersonate="chrome124" if profile == "chrome124" else None,
                              curl_options={CurlOpt.PROXY: ""}) as session:
            for _ in range(5):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    result["error_type"] = "TimeoutError"
                    return result
                # A streamed response preserves the same 64 KiB log input cap.
                response = session.get(url, timeout=min(8, remaining), allow_redirects=False, stream=True)
                try:
                    parsed = urllib.parse.urlsplit(url)
                    result["chain"].append({"host": parsed.hostname, "status": response.status_code,
                                             "proxied_cas": "/https/" in parsed.path and "/tpass/login" in parsed.path})
                    location = response.headers.get("Location")
                    if response.status_code in (301, 302, 303, 307, 308) and location:
                        next_url = urllib.parse.urljoin(url, location)
                        target = urllib.parse.urlsplit(next_url)
                        if target.scheme != "https" or target.hostname not in {"vpn.jlu.edu.cn", "cas.jlu.edu.cn"} or target.port not in (None, 443) or target.username or target.password:
                            result["redirect_blocked"] = True
                            return result
                        url = next_url
                        continue
                    raw = bytearray()
                    for chunk in response.iter_content(chunk_size=4096):
                        raw.extend(chunk[:65536 - len(raw)])
                        if len(raw) >= 65536:
                            break
                    headers = email.message.Message()
                    for key in ("Content-Type", "Content-Encoding", "Server", "Via"):
                        if response.headers.get(key):
                            headers[key] = response.headers[key]
                    result.update(inspect_response(SimpleNamespace(read=io.BytesIO(raw).read, headers=headers,
                                                                   status=response.status_code), url))
                    return result
                finally:
                    response.close()
            result["redirect_limit"] = True
    except Exception as error:
        result["error_type"] = type(error).__name__
        result["curl_code"] = getattr(error, "code", None)
    return result

def run():
    from cas_transport import anonymous_smoke
    print(json.dumps(anonymous_smoke()), flush=True)
    print(json.dumps({"event": "network_probe", "proxy_types": sorted(k for k in urllib.request.getproxies() if k != "no"),
                      "ca_file_exists": bool(ssl.get_default_verify_paths().cafile)}, ensure_ascii=True), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(probe, TARGETS.items()):
            print(json.dumps({"event": "network_probe", **result}), flush=True)
        for result in pool.map(tls_probe, ("cas.jlu.edu.cn", "iedu.jlu.edu.cn", "vpn.jlu.edu.cn")):
            print(json.dumps(result), flush=True)
        for result in pool.map(browser_probe, ("curl", "chrome124")):
            print(json.dumps(result), flush=True)
    print(json.dumps(browser_probe("chrome124", "vpn_official_cas")), flush=True)
