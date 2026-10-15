"""android/app/src/main/python/jlu_android.py：本机随机端口启动、数据目录落在私有目录。"""
import importlib.util
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "android" / "app" / "src" / "main" / "python" / "jlu_android.py"


def _load():
    spec = importlib.util.spec_from_file_location("jlu_android", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_start_serves_ui_on_loopback(tmp_path, monkeypatch):
    for k in ("XDG_CONFIG_HOME", "JLU_TOOLKIT_NO_KEYRING"):
        monkeypatch.delenv(k, raising=False)
    m = _load()
    try:
        url = m.start(str(tmp_path))
        assert url.startswith("http://127.0.0.1:") and not url.endswith(":8765/")
        assert m._httpd.server_address[0] == "127.0.0.1"
        assert m.start(str(tmp_path)) == url
        html = urllib.request.urlopen(url, timeout=5).read().decode()
        assert "<html" in html.lower()
        assert os.environ["JLU_TOOLKIT_NO_KEYRING"] == "1"
        assert (tmp_path / "config" / "jlu-toolkit" / "data").is_dir()
    finally:
        m.stop()
