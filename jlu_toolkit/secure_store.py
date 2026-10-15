"""本地凭据 / 会话的加密存储。

方案：随机 32 字节主密钥存进系统钥匙串（keyring：Windows 凭据管理器 / macOS 钥匙串 /
Linux Secret Service），数据用 AES-256-GCM 加密后写到 ``<config>/<name>.enc``。
会话 cookie 往往超过 Windows 凭据管理器的单条大小上限，所以钥匙串里只放密钥。

钥匙串或 cryptography 不可用（如 Termux、无桌面的 Linux）时退回明文 JSON 文件，
权限 0600，并在 stderr 提示一次。设 ``JLU_TOOLKIT_NO_KEYRING=1`` 可强制使用文件。

旧版明文 ``<name>.json`` 会在第一次读取时透明迁移为加密文件并删除明文。
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any, Optional

SERVICE = "jlu-toolkit"
KEY_ENTRY = "storage-key"
_MAGIC = b"JLUT1"
_warned = False
last_error: Optional[str] = None


def _warn(msg: str) -> None:
    if os.environ.get("JLU_TOOLKIT_QUIET_STORE"):
        return
    print(f"[jlu-toolkit] 警告：{msg}", file=sys.stderr)


class SecureStoreError(Exception):
    """加密文件无法解密（钥匙串里的密钥丢失或被换掉）。"""


def _chmod600(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _keyring():
    if os.environ.get("JLU_TOOLKIT_NO_KEYRING"):
        return None
    try:
        import keyring
        from keyring.backends import fail
    except Exception:  # noqa: BLE001
        return None
    try:
        kr = keyring.get_keyring()
    except Exception:  # noqa: BLE001
        return None
    if isinstance(kr, fail.Keyring):
        return None
    try:
        if float(getattr(kr, "priority", 1)) <= 0:
            return None
    except Exception:  # noqa: BLE001
        pass
    return keyring


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception:  # noqa: BLE001
        return None
    return AESGCM


def backend_name() -> str:
    kr = _keyring()
    if kr is None or _aesgcm() is None:
        return "file"
    return "keyring:" + type(kr.get_keyring()).__name__


def _get_key(create: bool) -> Optional[bytes]:
    global last_error
    kr = _keyring()
    if kr is None:
        return None
    try:
        raw = kr.get_password(SERVICE, KEY_ENTRY)
        if raw:
            return base64.b64decode(raw)
        if not create:
            return None
        key = secrets.token_bytes(32)
        kr.set_password(SERVICE, KEY_ENTRY, base64.b64encode(key).decode())
        # 回读确认真的写进去了（有些后端静默失败）
        if kr.get_password(SERVICE, KEY_ENTRY) is None:
            last_error = "写入钥匙串后回读为空（后端静默失败）"
            return None
        return key
    except Exception as e:  # noqa: BLE001
        last_error = f"钥匙串读写失败：{type(e).__name__}: {e}"
        return None


def _warn_plain(path: Path) -> None:
    global _warned
    if _warned or os.environ.get("JLU_TOOLKIT_QUIET_STORE"):
        return
    _warned = True
    print(
        f"[jlu-toolkit] 警告：系统钥匙串不可用，凭据/会话以明文保存在 {path}（权限 600）。"
        "请勿在多人共用的设备上保存密码；装好 keyring 与 cryptography 后会自动改为加密存储。",
        file=sys.stderr,
    )


class SecretFile:
    """一个具名的秘密 JSON 对象，例如 SecretFile(dir, "session")。"""

    def __init__(self, directory: Path, name: str):
        self.dir = Path(directory)
        self.name = name

    @property
    def enc_path(self) -> Path:
        return self.dir / f"{self.name}.enc"

    @property
    def plain_path(self) -> Path:
        return self.dir / f"{self.name}.json"

    def exists(self) -> bool:
        return self.enc_path.is_file() or self.plain_path.is_file()

    def save(self, obj: Any) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        AESGCM = _aesgcm()
        key = _get_key(create=True) if AESGCM else None
        if key is not None:
            nonce = secrets.token_bytes(12)
            ct = AESGCM(key).encrypt(nonce, data, (SERVICE + ":" + self.name).encode())
            tmp = self.enc_path.with_suffix(".enc.tmp")
            tmp.write_bytes(_MAGIC + nonce + ct)
            _chmod600(tmp)
            os.replace(tmp, self.enc_path)
            _chmod600(self.enc_path)
            if self.plain_path.is_file():
                self.plain_path.unlink()
            return self.enc_path
        if AESGCM is not None and _keyring() is not None:
            _warn(f"钥匙串后端可用但取不到密钥（{last_error or '原因未知'}），本次以明文保存到 {self.plain_path}")
        else:
            _warn_plain(self.plain_path)
        self.plain_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        _chmod600(self.plain_path)
        if self.enc_path.is_file():
            self.enc_path.unlink()
        return self.plain_path

    def load(self) -> Optional[Any]:
        if self.enc_path.is_file():
            blob = self.enc_path.read_bytes()
            AESGCM = _aesgcm()
            key = _get_key(create=False) if AESGCM else None
            if key is None or not blob.startswith(_MAGIC):
                raise SecureStoreError(
                    f"无法解密 {self.enc_path}：系统钥匙串中的密钥不可用。请删除该文件后重新登录。"
                )
            n = len(_MAGIC)
            try:
                data = AESGCM(key).decrypt(blob[n:n + 12], blob[n + 12:], (SERVICE + ":" + self.name).encode())
            except Exception as e:  # noqa: BLE001
                raise SecureStoreError(f"{self.enc_path} 解密失败，请删除该文件后重新登录") from e
            return json.loads(data.decode("utf-8"))
        if self.plain_path.is_file():
            obj = json.loads(self.plain_path.read_text(encoding="utf-8"))
            # 透明迁移：钥匙串可用时改存加密文件（save 会删除明文）
            if backend_name() != "file":
                try:
                    out = self.save(obj)
                    if out != self.enc_path:
                        _warn(f"{self.plain_path} 未能迁移为加密文件，仍是明文")
                except Exception as e:  # noqa: BLE001
                    _warn(f"{self.plain_path} 迁移为加密文件失败：{type(e).__name__}: {e}")
            else:
                _warn_plain(self.plain_path)
            return obj
        return None

    def delete(self) -> None:
        for p in (self.enc_path, self.plain_path):
            if p.is_file():
                p.unlink()
