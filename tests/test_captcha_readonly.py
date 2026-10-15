import os
from pathlib import Path

from jlu_toolkit import captcha_util


def test_write_captcha_files_survives_readonly_cwd(monkeypatch, tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    os.chmod(ro, 0o500)
    monkeypatch.chdir(ro)
    monkeypatch.setattr(captcha_util, "termux_storage_dirs", lambda: [])
    monkeypatch.setattr(captcha_util, "validate_captcha_bytes", lambda d: None)
    monkeypatch.setattr(captcha_util, "scale_for_gallery", lambda d: d)
    paths = captcha_util.write_captcha_files(b"x" * 100)
    assert paths and all(Path(p).exists() for p in paths)
    assert not str(paths[0]).startswith(str(ro))
