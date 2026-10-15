"""App / Web UI 内登录：把 CLI 的交互式登录拆成几个无状态的 HTTP 步骤。

流程（都在 127.0.0.1 本机服务上）：
  1. ``start(username, password, remember)``：提交统一认证账号密码；
     成功则直接落盘会话，需要二次认证则返回一张图形验证码（data URI）。
  2. ``captcha()``：换一张图形验证码。
  3. ``send_code(captcha)``：用图形验证码请求微信验证码（「智慧吉大」里查看）。
  4. ``verify(captcha, wechat_code)``：完成二次认证，进入教务应用并保存会话。

会话与（勾选「记住我」时的）账号密码都走 jwxt 的 secure_store：
Android 上由 Android Keystore 保护的 AES-GCM 密钥加密，桌面端用系统钥匙串。
密码只在内存里停留到登录结束，不写日志、不回传给前端。
"""
from __future__ import annotations

import base64
import threading
from typing import Callable, Optional

from . import jwxt


class LoginFlow:
    def __init__(self, client_factory: Callable[[], "jwxt.JwxtClient"] = jwxt.JwxtClient):
        self._factory = client_factory
        self._lock = threading.Lock()
        self._client: Optional[jwxt.JwxtClient] = None
        self._cred: Optional[tuple[str, str]] = None
        self._remember = False

    # ---- helpers ----
    def _captcha_uri(self) -> str:
        c = self._client
        path = c.download_captcha()
        raw = c.last_captcha_bytes or path.read_bytes()
        mime = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(raw).decode()

    def _finish(self) -> dict:
        c = self._client
        try:
            c.bootstrap_emap_apps()
        except jwxt.JwxtError:
            pass
        c.save_session()
        if self._remember and self._cred:
            jwxt.save_credentials(*self._cred)
        self._reset()
        return {"step": "success"}

    def _reset(self) -> None:
        self._client = None
        self._cred = None
        self._remember = False

    def _need(self) -> "jwxt.JwxtClient":
        if self._client is None:
            raise ValueError("登录流程已失效，请重新输入账号密码")
        return self._client

    # ---- steps ----
    def saved_username(self) -> Optional[str]:
        try:
            cred = jwxt.load_credentials()
        except Exception:  # noqa: BLE001
            return None
        return cred[0] if cred else None

    def start(self, username: str, password: str, remember: bool = True) -> dict:
        username = (username or "").strip()
        if not password:
            saved = jwxt.load_credentials()
            if saved and (not username or saved[0] == username):
                username, password = saved
        if not username or not password:
            raise ValueError("请填写统一身份认证账号（邮箱前缀）和密码")
        with self._lock:
            self._reset()
            self._client = self._factory()
            self._cred = (username, password)
            self._remember = bool(remember)
            step = self._client.login_password(username, password)
            if step == jwxt.LoginStep.SUCCESS:
                return self._finish()
            if step == jwxt.LoginStep.NEED_SECOND_FACTOR:
                return {"step": "need_second_factor", "captcha": self._captcha_uri()}
            err = getattr(self._client, "last_error_text", "") or ""
            self._reset()
            if step == jwxt.LoginStep.WRONG_PASSWORD:
                raise ValueError(err or "用户名或密码错误（账号用邮箱前缀，不是学号）")
            raise ValueError(err or f"登录未完成（{step.value}）")

    def captcha(self) -> dict:
        with self._lock:
            self._need()
            return {"step": "need_second_factor", "captcha": self._captcha_uri()}

    def send_code(self, captcha: str) -> dict:
        captcha = (captcha or "").strip()
        if not captcha:
            raise ValueError("请输入图形验证码")
        with self._lock:
            c = self._need()
            r = c.request_wechat_code(captcha)
            if r == jwxt.WechatCodeResult.SUCCESS:
                return {"step": "code_sent"}
            if r == jwxt.WechatCodeResult.CAPTCHA_ERROR:
                return {"step": "need_second_factor", "error": "图形验证码错误", "captcha": self._captcha_uri()}
            if r == jwxt.WechatCodeResult.TOO_FREQUENT:
                raise ValueError("发送太频繁，请稍后再试")
            self._reset()
            if r == jwxt.WechatCodeResult.SESSION_EXPIRED:
                raise ValueError("二次认证会话已失效，请重新输入账号密码")
            raise ValueError(f"发送微信验证码失败（{r.value}）")

    def verify(self, captcha: str, wechat_code: str) -> dict:
        if not (wechat_code or "").strip():
            raise ValueError("请输入微信验证码")
        with self._lock:
            c = self._need()
            step = c.login_second_factor((captcha or "").strip(), wechat_code.strip())
            if step == jwxt.LoginStep.SUCCESS:
                return self._finish()
            return {"step": "code_sent", "error": "微信验证码不正确或已过期"}

    def cancel(self) -> dict:
        with self._lock:
            self._reset()
        return {"step": "idle"}
