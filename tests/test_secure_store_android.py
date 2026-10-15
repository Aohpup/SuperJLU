"""Android Keystore 后端：用纯 Python 模拟 Chaquopy 的 jclass。"""
import os
import sys
import types

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

from jlu_toolkit import secure_store  # noqa: E402


class FakeAndroid:
    def __init__(self):
        self.keys = {}
        self.calls = []
        fa = self

        class KeyStore:
            @staticmethod
            def getInstance(p):
                assert p == "AndroidKeyStore"
                return KeyStore()

            def load(self, x):
                assert x is None

            def containsAlias(self, a):
                return a in fa.keys

            def getKey(self, a, pw):
                return fa.keys[a]

        class KP:
            PURPOSE_ENCRYPT, PURPOSE_DECRYPT = 1, 2
            BLOCK_MODE_GCM, ENCRYPTION_PADDING_NONE, KEY_ALGORITHM_AES = "GCM", "NoPadding", "AES"

        class Builder:
            def __init__(self, alias, purposes):
                assert purposes == 3
                self.d = {"alias": alias}

            def setBlockModes(self, m):
                self.d["modes"] = m
                return self

            def setEncryptionPaddings(self, p):
                self.d["pad"] = p
                return self

            def setKeySize(self, n):
                self.d["size"] = n
                return self

            def build(self):
                return self.d

        class KeyGenerator:
            @staticmethod
            def getInstance(alg, prov):
                assert (alg, prov) == ("AES", "AndroidKeyStore")
                return KeyGenerator()

            def init(self, spec):
                assert spec["modes"] == ["GCM"] and spec["pad"] == ["NoPadding"] and spec["size"] == 256
                self.alias = spec["alias"]

            def generateKey(self):
                fa.calls.append("generate")
                fa.keys[self.alias] = os.urandom(32)
                return fa.keys[self.alias]

        class GCMParameterSpec:
            def __init__(self, tlen, iv):
                assert tlen == 128
                self.iv = bytes(iv)

        class Cipher:
            ENCRYPT_MODE, DECRYPT_MODE = 1, 2

            @staticmethod
            def getInstance(t):
                assert t == "AES/GCM/NoPadding"
                return Cipher()

            def init(self, mode, key, spec=None):
                self.mode, self.key = mode, key
                self.iv = os.urandom(12) if mode == 1 else spec.iv

            def getIV(self):
                return [b - 256 if b > 127 else b for b in self.iv]  # 模拟有符号 Java byte[]

            def doFinal(self, data):
                g = AESGCM(self.key)
                return g.encrypt(self.iv, bytes(data), None) if self.mode == 1 else g.decrypt(self.iv, bytes(data), None)

        self.classes = {"java.security.KeyStore": KeyStore, "android.security.keystore.KeyProperties": KP,
                        "android.security.keystore.KeyGenParameterSpec$Builder": Builder,
                        "javax.crypto.KeyGenerator": KeyGenerator, "javax.crypto.Cipher": Cipher,
                        "javax.crypto.spec.GCMParameterSpec": GCMParameterSpec}

    def jclass(self, name):
        return self.classes[name]


@pytest.fixture
def android(tmp_path, monkeypatch):
    fa = FakeAndroid()
    monkeypatch.setitem(sys.modules, "java", types.SimpleNamespace(jclass=fa.jclass))
    monkeypatch.setenv("ANDROID_ROOT", "/system")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("JLU_TOOLKIT_NO_KEYRING", raising=False)
    return fa


def test_backend_name(android):
    assert secure_store.backend_name() == "android-keystore"


def test_not_android_without_env(monkeypatch, android):
    monkeypatch.delenv("ANDROID_ROOT")
    monkeypatch.delenv("ANDROID_DATA", raising=False)
    monkeypatch.delitem(sys.modules, "chaquopy", raising=False)
    assert secure_store._android() is None


def test_roundtrip_and_format(android, tmp_path):
    d = tmp_path / "jlu-toolkit"
    sf = secure_store.SecretFile(d, "session")
    assert sf.save({"a": 1}) == sf.enc_path
    assert sf.enc_path.read_bytes().startswith(b"JLUT1")  # .enc 格式不变
    wrapped = (d / "storage-key.wrapped").read_bytes()
    assert wrapped.startswith(b"JLUK1") and android.calls == ["generate"]
    assert secure_store.SecretFile(d, "session").load() == {"a": 1}
    sf.save({"b": 2})
    assert android.calls == ["generate"]  # 不重复生成
    assert (d / "storage-key.wrapped").read_bytes() == wrapped


def test_migrates_plaintext(android, tmp_path):
    d = tmp_path / "jlu-toolkit"
    d.mkdir()
    (d / "session.json").write_text('{"c": 3}', encoding="utf-8")
    assert secure_store.SecretFile(d, "session").load() == {"c": 3}
    assert not (d / "session.json").exists() and (d / "session.enc").exists()


def test_lost_keystore_key_raises(android, tmp_path):
    d = tmp_path / "jlu-toolkit"
    secure_store.SecretFile(d, "session").save({"a": 1})
    android.keys.clear()
    with pytest.raises(secure_store.SecureStoreError):
        secure_store.SecretFile(d, "session").load()
