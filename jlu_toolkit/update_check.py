"""Quiet "new version available" check against the public GitHub release.

Read-only: one anonymous GET to the public releases API, no account data sent.
Never raises and never forces an update; the UI only shows a small hint.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request

from . import __version__

REPO = "Runa-Asahi/SuperJLU"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
TTL = 6 * 3600          # 成功结果缓存 6 小时
FAIL_TTL = 30 * 60      # 失败后 30 分钟内不再重试
_lock = threading.Lock()
_cache: dict = {"at": 0.0, "ttl": 0, "result": None}


def parse_version(s):
    """'v1.2.3' / '1.2' / 'v1.2.3-beta' -> (1, 2, 3); None if unparseable."""
    m = re.match(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(s or ""))
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def is_newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def _safe_url(u):
    u = str(u or "")
    return u if u.startswith(f"https://github.com/{REPO}/releases") else RELEASES_PAGE


def summarize(release, current=__version__):
    """Turn a GitHub release JSON into the small payload the UI needs."""
    if not isinstance(release, dict) or not release.get("tag_name") or release.get("draft") or release.get("prerelease"):
        return {"ok": True, "current": current, "has_update": False}
    tag = str(release.get("tag_name") or "")
    latest = tag.lstrip("vV") or None
    out = {"ok": True, "current": current, "latest": latest,
           "has_update": is_newer(tag, current), "url": _safe_url(release.get("html_url"))}
    if release.get("published_at"):
        out["published_at"] = str(release["published_at"])[:10]
    return out


def _request():
    return urllib.request.Request(API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"SuperJLU/{__version__}"})


def _fetch_urllib(timeout):
    with urllib.request.urlopen(_request(), timeout=timeout) as r:
        return json.loads(r.read(200_000).decode("utf-8"))


def _fetch_native(timeout):
    """Android/Windows system HTTPS stack (system CA store)."""
    from . import network
    if not network.native_available():
        raise OSError("no native transport")
    r = network.native_open(_request(), timeout)
    code = getattr(r, "code", 200)
    if code == 404:
        return {}  # 仓库还没有正式版：视为没有更新，而不是失败
    if code >= 400:
        raise OSError(f"HTTP {code}")
    return json.loads(r.read(200_000).decode("utf-8"))


def _fetch(timeout):
    # 安卓上内置 Python 的 ssl 拿不到系统 CA 证书，直接 urllib 访问
    # api.github.com 会证书校验失败，于是“手动检查更新”总被当成查询失败。
    # 先走系统 HTTPS（与教务请求同一条通道），失败再退回 urllib。
    errors = []
    for fn in (_fetch_native, _fetch_urllib):
        try:
            return fn(timeout)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            errors.append(e)
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    raise errors[-1]


def check(force=False, timeout=6, fetch=None, now=None):
    now = time.time() if now is None else now
    with _lock:
        c = _cache
        if not force and c["result"] is not None and now - c["at"] < c["ttl"]:
            return dict(c["result"], cached=True)
    try:
        result, ttl = summarize((fetch or _fetch)(timeout)), TTL
    except Exception:
        # 查不到就安静地当作没有更新，不打扰用户。
        result, ttl = {"ok": True, "current": __version__, "has_update": False, "unavailable": True}, FAIL_TTL
    with _lock:
        _cache.update(at=now, ttl=ttl, result=result)
    return dict(result)
