import os
from pathlib import Path

from jlu_toolkit import captcha_util, jwxt


def test_captcha_save_path_skips_readonly(tmp_path, monkeypatch):
    ro = tmp_path / "ro"
    ro.mkdir()
    monkeypatch.setattr(captcha_util, "captcha_candidate_paths",
                        lambda fn="x.jpg": [ro / fn])
    real_access = os.access
    monkeypatch.setattr(jwxt.os, "access",
                        lambda p, m: False if Path(p) == ro else real_access(p, m))
    p = jwxt.captcha_save_path("jlu_cas_captcha.jpg")
    assert p.parent != ro
    p.write_bytes(b"ok")  # 必须可写
