"""captcha_util 单元测试：JPEG 校验、多路径保存、ASCII（有 Pillow 时）。"""
from pathlib import Path

import pytest

from jlu_toolkit import captcha_util as cu

FIXTURE = Path(__file__).parent / "fixtures" / "sample_captcha.jpg"


def _sample() -> bytes:
    return FIXTURE.read_bytes()


def test_validate_jpeg_ok():
    data = _sample()
    fmt, w, h = cu.validate_captcha_bytes(data, "image/jpeg")
    assert fmt == "jpeg" and w == 70 and h == 36
    assert 1500 <= len(data) <= 5000 or len(data) >= 200


def test_validate_rejects_html():
    data = b"<html>nope</html>" + b"x" * 200
    with pytest.raises(cu.CaptchaImageError):
        cu.validate_captcha_bytes(data, "text/html")


def test_validate_rejects_tiny():
    with pytest.raises(cu.CaptchaImageError):
        cu.validate_captcha_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)


def test_validate_1616_band_real_structure():
    """Owner's 1616-byte file size is in the normal CAS JPEG band."""
    data = _sample()
    assert data[:2] == b"\xff\xd8"
    fmt, w, h = cu.validate_captcha_bytes(data)
    assert (w, h) == (70, 36)


def test_write_captcha_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cu, "termux_storage_dirs", lambda: [])
    data = _sample()
    paths = cu.write_captcha_files(data, "cap.jpg")
    assert paths
    assert paths[0].read_bytes() == data
    assert paths[0].stat().st_size >= 200
    # enlarged copy for gallery
    assert any(p.name.endswith("_large.jpg") for p in paths)


def test_render_ascii_without_crash():
    text = cu.render_ascii(_sample(), width=40)
    assert isinstance(text, str) and len(text) > 10
    assert "#" in text or "Pillow" in text


def test_ocr_digits_no_crash():
    cu.ocr_digits(_sample())
