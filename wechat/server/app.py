"""Small single-instance HTTPS-proxy backend. Run: python app.py.

Use a TLS reverse proxy; keep this listener on loopback. Authentication tokens
are opaque, expire, and never contain WeChat session_key or CAS cookies.
"""
from __future__ import annotations

import collections
import gzip
import hashlib
import hmac
import json
import os
import secrets
import shutil
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import adapter
import cas_transport

ROOT = Path(__file__).parent


def load_env():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    if os.environ.get("SUPERJLU_DIRECT_SCHOOL") == "1":
        existing = os.environ.get("no_proxy", os.environ.get("NO_PROXY", ""))
        os.environ["no_proxy"] = existing + ",.jlu.edu.cn,api.weixin.qq.com,127.0.0.1,localhost"


@dataclass
class Session:
    user: str
    expires: float


@dataclass
class UserState:
    lock: object = field(default_factory=threading.RLock)
    flow: object = field(default_factory=adapter.SchoolSession)
    cas: object = field(default_factory=cas_transport.CasFlows)
    last_sync: float = 0
    last_login: float = 0
    last_send: float = 0
    last_verify: float = 0
    job_lock: object = field(default_factory=threading.RLock)
    job: dict = field(default_factory=dict)


class ApiError(Exception):
    def __init__(self, status, message, code="BAD_REQUEST"):
        self.status, self.message, self.code = status, message, code


class Application:
    def __init__(self, key, data_dir, appid="", secret="", allow_dev=False, exchange=None):
        if len(key) != 32:
            raise ValueError("SUPERJLU_MASTER_KEY must be 64 hex characters")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        AESGCM(key)  # Fail closed: never fall back to plaintext storage.
        adapter.master_key, adapter.data_root = key, Path(data_dir).resolve()
        self.appid, self.secret, self.allow_dev = appid, secret, allow_dev
        self.exchange = exchange or self.exchange_wechat
        self.sessions, self.users = {}, {}
        self.lock = threading.RLock()
        self.rates = collections.OrderedDict()

    def exchange_wechat(self, code):
        if not self.appid or not self.secret:
            raise ApiError(503, "服务器尚未配置微信 AppID 和 AppSecret", "NOT_CONFIGURED")
        query = urllib.parse.urlencode({"appid": self.appid, "secret": self.secret,
                                       "js_code": code, "grant_type": "authorization_code"})
        # Never log this URL: it contains the AppSecret and temporary code.
        try:
            with urllib.request.urlopen("https://api.weixin.qq.com/sns/jscode2session?" + query, timeout=10) as r:
                payload = r.read()
                if r.headers.get("Content-Encoding", "").lower() == "gzip":
                    payload = gzip.decompress(payload)
                value = json.loads(payload)
        except Exception as error:
            reason = getattr(error, "reason", None)
            # Never stringify exceptions: HTTP exceptions can contain the URL,
            # including the AppSecret. Only fixed type names and status codes.
            print(json.dumps({"event": "wechat_exchange_failed", "error_type": type(error).__name__,
                              "reason_type": type(reason).__name__ if reason else None,
                              "http_status": getattr(error, "code", None),
                              "certificate_error": getattr(reason, "verify_code", None)}), flush=True)
            raise ApiError(502, "微信登录服务暂时不可用", "WECHAT_UNAVAILABLE") from None
        if not value.get("openid") or value.get("errcode"):
            raise ApiError(401, "微信登录凭证无效，请重试", "WECHAT_LOGIN_FAILED")
        return value["openid"]

    def rate(self, peer):
        now = time.monotonic()
        with self.lock:
            q = self.rates.setdefault(peer, collections.deque())
            self.rates.move_to_end(peer)
            while q and q[0] < now - 60:
                q.popleft()
            if len(q) >= 20:
                raise ApiError(429, "登录请求太频繁，请一分钟后重试", "RATE_LIMIT")
            q.append(now)
            while len(self.rates) > 4096:
                self.rates.popitem(last=False)

    def issue_token(self, identity):
        user = hmac.new(adapter.master_key, (self.appid + ":" + identity).encode(), hashlib.sha256).hexdigest()
        token = secrets.token_urlsafe(32)
        with self.lock:
            now = time.time()
            self.sessions = {k: v for k, v in self.sessions.items() if v.expires > now}
            active = {v.user for v in self.sessions.values()}
            self.users = {k: v for k, v in self.users.items() if k in active}
            if len(self.sessions) >= 1000:
                raise ApiError(503, "服务繁忙，请稍后重试")
            self.sessions[token] = Session(user, now + 7200)
            self.users.setdefault(user, UserState())
        return {"token": token, "expires_in": 7200}

    def cloud_login(self, headers, peer):
        # Only enable inside the platform-managed CloudRun environment. Its
        # gateway overwrites X-WX identity headers; never enable behind a raw
        # reverse proxy that simply forwards arbitrary client headers.
        self.rate(peer)
        env = os.environ.get("CBR_ENV_ID", "")
        h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        if (not env or h.get("x-wx-env") != env or not h.get("x-wx-source")
                or h.get("x-wx-appid") != self.appid or not h.get("x-wx-openid")
                or len(h["x-wx-openid"]) > 128):
            raise ApiError(403, "请通过本小程序的微信云托管通道登录", "CLOUD_IDENTITY_REQUIRED")
        return self.issue_token(h["x-wx-openid"])

    def login(self, body, peer):
        self.rate(peer)
        code = body.get("code")
        if not isinstance(code, str) or not code or len(code) > 256:
            raise ApiError(400, "缺少微信登录 code")
        if code.startswith("dev:"):
            if not self.allow_dev:
                raise ApiError(403, "开发登录已关闭")
            identity = code
        else:
            identity = self.exchange(code)
        return self.issue_token(identity)

    def dispatch(self, method, path, body, token, peer="127.0.0.1", headers=None):
        if path == "/health" and method == "GET":
            return {"status": "ok"}
        if path == "/api/wechat/login" and method == "POST":
            return self.login(body, peer)
        if path == "/api/wechat/cloud-login" and method == "POST":
            return self.cloud_login(headers, peer)
        with self.lock:
            session = self.sessions.get(token)
            if not session or session.expires <= time.time():
                self.sessions.pop(token, None)
                raise ApiError(401, "微信会话已过期，请重新连接", "TOKEN_EXPIRED")
            state = self.users[session.user]
        if method == "GET" and path == "/api/refresh/status":
            with state.job_lock:
                return dict(state.job) or {"status": "idle"}
        with state.lock:
            ctx = adapter.current_user.set(session.user)
            try:
                return self.authorized(method, path, body, session, state)
            finally:
                adapter.current_user.reset(ctx)

    def authorized(self, method, path, body, session, state):
        if method == "POST" and path == "/api/cas/request":
            return state.cas.request(body)
        if method == "POST" and path == "/api/cas/close":
            flow = body.get("flow", "")
            if not isinstance(flow, str) or len(flow) > 128:
                raise ValueError("Invalid flow")
            state.cas.close(flow)
            return {}
        if method == "POST" and path == "/api/cas/clear":
            state.cas.clear()
            return {}
        if method == "GET" and path == "/api/data":
            return adapter.snapshot()
        if method == "GET" and path == "/api/session":
            return {"logged_in": adapter.jwxt.session_status().get("state") == adapter.jwxt.SESSION_OK}
        if method != "POST":
            raise ApiError(404, "接口不存在")
        now = time.monotonic()
        if path == "/api/login/start":
            if now - state.last_login < 5:
                raise ApiError(429, "请稍候再登录")
            state.last_login = now
            return state.flow.start(body.get("username"), body.get("password"))
        if path == "/api/login/captcha":
            return state.flow.captcha()
        if path == "/api/login/send_code":
            if now - state.last_send < 60:
                raise ApiError(429, "验证码一分钟内只能发送一次")
            state.last_send = now
            return state.flow.send_code(body.get("captcha", ""))
        if path == "/api/login/verify":
            if now - state.last_verify < 2:
                raise ApiError(429, "请稍候再验证")
            state.last_verify = now
            return state.flow.verify(body.get("wechat_code", ""))
        if path == "/api/login/cancel":
            state.flow.cancel()
            return {}
        if path == "/api/refresh":
            with state.job_lock:
                if state.job.get("status") == "running":
                    return {"job_id": state.job["job_id"], "status": "running"}
            if now - state.last_sync < 60:
                raise ApiError(429, "一分钟内只能同步一次")
            state.last_sync = now
            job_id = secrets.token_hex(12)
            with state.job_lock:
                state.job = {"job_id": job_id, "status": "running"}
            threading.Thread(target=self.refresh_job, args=(session.user, state, job_id), daemon=True).start()
            return {"job_id": job_id, "status": "running"}
        if path == "/api/rooms":
            return adapter.room_query(body)
        if path == "/api/rooms/buildings":
            campus = str(body.get("campus", ""))
            if campus not in {x["code"] for x in adapter.CAMPUSES}:
                raise ValueError("请选择校区")
            c = adapter.client()
            result = adapter.rooms.list_buildings(c, campus)
            c.save_session()
            return {"buildings": result}
        if path == "/api/notices":
            return adapter.notices(body)
        if path == "/api/grades/import":
            return adapter.import_grades(body)
        if path == "/api/logout":
            state.flow.cancel()
            state.cas.clear()
            root = adapter.config_dir().resolve()
            if root.parent != adapter.data_root.resolve():
                raise RuntimeError("Invalid user path")
            if root.exists():
                shutil.rmtree(root)
            with self.lock:
                self.sessions = {k: v for k, v in self.sessions.items() if v.user != session.user}
            return {}
        raise ApiError(404, "接口不存在")

    def refresh_job(self, user, state, job_id):
        with state.lock:
            ctx = adapter.current_user.set(user)
            try:
                result = {"job_id": job_id, "status": "done", "data": adapter.refresh()}
            except adapter.jwxt.LoginError:
                result = {"job_id": job_id, "status": "error", "error": "教务会话已过期，请重新绑定", "code": "SCHOOL_SESSION_EXPIRED"}
            except Exception:
                result = {"job_id": job_id, "status": "error", "error": "同步暂未完成，请确认学校网络可达后重试"}
            finally:
                adapter.current_user.reset(ctx)
            with state.job_lock:
                state.job = result


def make_handler(application):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SuperJLU-WeChat"

        def log_message(self, *args):
            pass  # No access logs containing school data or authentication URLs.

        def reply(self, status, data):
            raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def handle_api(self):
            self.connection.settimeout(20)
            try:
                body = {}
                if self.command == "POST":
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 0 or length > 7 * 1024 * 1024:
                        raise ApiError(413, "请求不能超过 7 MB")
                    if self.headers.get_content_type() != "application/json":
                        raise ApiError(415, "需要 JSON 请求")
                    try:
                        body = json.loads(self.rfile.read(length))
                    except (ValueError, UnicodeError):
                        raise ApiError(400, "JSON 格式错误")
                    if not isinstance(body, dict):
                        raise ApiError(400, "请求应为 JSON 对象")
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                value = application.dispatch(self.command, urllib.parse.urlsplit(self.path).path, body,
                                             token, self.client_address[0], self.headers)
                self.reply(200, {"ok": True, **value})
            except ApiError as e:
                self.reply(e.status, {"ok": False, "error": e.message, "code": e.code})
            except adapter.jwxt.LoginError:
                self.reply(401, {"ok": False, "error": "教务会话已失效，请重新绑定", "code": "SCHOOL_SESSION_EXPIRED"})
            except adapter.jwxt.NetworkError:
                self.reply(502, {"ok": False, "error": "无法连接学校，请确认服务器处于校园网或 VPN 网络"})
            except cas_transport.CasTransportError as e:
                self.reply(400, {"ok": False, "error": str(e), "code": "CAS_TRANSPORT_FAILED"})
            except (ValueError, TypeError, KeyError):
                self.reply(400, {"ok": False, "error": "输入无效或学校验证未通过，请核对后重试"})
            except Exception:
                self.reply(500, {"ok": False, "error": "服务暂时不可用，请稍后重试"})

        do_GET = handle_api
        do_POST = handle_api

    return Handler


if __name__ == "__main__":
    load_env()
    try:
        key = bytes.fromhex(os.environ.get("SUPERJLU_MASTER_KEY", ""))
        data_path = Path(os.environ.get("SUPERJLU_DATA_DIR", ".data"))
        app = Application(key, data_path if data_path.is_absolute() else ROOT / data_path,
                          os.environ.get("WECHAT_APP_ID", ""), os.environ.get("WECHAT_APP_SECRET", ""),
                          os.environ.get("SUPERJLU_ALLOW_DEV_LOGIN") == "1")
    except (ValueError, ImportError):
        raise SystemExit("请安装 requirements.txt 并在 server/.env 配置 64 位十六进制 SUPERJLU_MASTER_KEY")
    host, port = os.environ.get("SUPERJLU_HOST", "127.0.0.1"), int(os.environ.get("SUPERJLU_PORT", "8787"))
    print(f"SuperJLU backend http://{host}:{port}; place an HTTPS reverse proxy in front.", flush=True)
    if os.environ.get("SUPERJLU_STARTUP_NETWORK_CHECK") == "1":
        from network_probe import run
        run()
    ThreadingHTTPServer((host, port), make_handler(app)).serve_forever()
