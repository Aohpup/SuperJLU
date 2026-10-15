"""图形验证码：校验、多路径保存、终端 ASCII 渲染、可选 OCR。

依赖均为可选：
  - Pillow：ASCII 渲染、放大保存、简单预处理
  - ddddocr：四位数字自动识别（失败则回退手动输入）
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Optional


class CaptchaImageError(ValueError):
    """下载到的字节不是可用的验证码图片。"""


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """从基线 JPEG SOF0/SOF2 标记读取宽高，无需完整解码。"""
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise CaptchaImageError("不是 JPEG（缺少 SOI）")
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break
        marker = data[i]
        i += 1
        if marker in (0xD8, 0xD9):  # SOI/EOI
            continue
        if marker == 0xDA:  # SOS
            break
        if i + 1 >= len(data):
            break
        seglen = (data[i] << 8) | data[i + 1]
        if seglen < 2 or i + seglen > len(data):
            break
        # SOF0..SOF3, SOF5..SOF7, SOF9..SOF11, SOF13..SOF15
        if marker in (
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        ):
            if seglen < 8:
                break
            height = (data[i + 3] << 8) | data[i + 4]
            width = (data[i + 5] << 8) | data[i + 6]
            if width < 10 or height < 10 or width > 2000 or height > 2000:
                raise CaptchaImageError(f"JPEG 尺寸异常：{width}x{height}")
            return width, height
        i += seglen
    raise CaptchaImageError("JPEG 中未找到 SOF 尺寸信息")


def validate_captcha_bytes(data: bytes, content_type: Optional[str] = None) -> tuple[str, int, int]:
    """校验验证码字节。返回 (format, width, height)。失败抛 CaptchaImageError。"""
    if not data:
        raise CaptchaImageError("验证码响应为空")
    if len(data) < 200:
        raise CaptchaImageError(f"验证码过小（{len(data)} bytes），可能未拿到图片")
    ct = (content_type or "").lower()
    if data[:2] == b"\xff\xd8":
        w, h = jpeg_dimensions(data)
        return "jpeg", w, h
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if len(data) < 24:
            raise CaptchaImageError("PNG 过短")
        w = int.from_bytes(data[16:20], "big")
        h = int.from_bytes(data[20:24], "big")
        return "png", w, h
    if "html" in ct or data.lstrip()[:1] in (b"<", b"{"):
        raise CaptchaImageError(
            f"服务器返回的不是图片（Content-Type={content_type!r}，开头={data[:40]!r}）"
        )
    raise CaptchaImageError(
        f"无法识别的验证码格式（Content-Type={content_type!r}，magic={data[:8]!r}）"
    )


def _pillow():
    try:
        from PIL import Image, ImageOps  # noqa: F401
    except ImportError:
        return None
    from PIL import Image, ImageOps

    return Image, ImageOps


def has_pillow() -> bool:
    return _pillow() is not None


def has_ddddocr() -> bool:
    try:
        import ddddocr  # noqa: F401

        return True
    except ImportError:
        return False


def render_ascii(data: bytes, width: int = 60) -> str:
    """把验证码渲染成终端可读的 ASCII 块图。需要 Pillow；否则返回说明文字。"""
    mods = _pillow()
    if not mods:
        try:
            fmt, w, h = validate_captcha_bytes(data)
            return (
                f"[未安装 Pillow，无法在终端绘制验证码。图片已保存（{fmt} {w}x{h}，"
                f"{len(data)} bytes）。Termux 可执行：pkg install python-pillow]"
            )
        except CaptchaImageError as e:
            return f"[验证码无法渲染：{e}]"
    Image, ImageOps = mods
    import io

    img = Image.open(io.BytesIO(data)).convert("L")
    img = ImageOps.autocontrast(img)
    # 近邻放大再二值化，数字更清晰
    img = img.resize((img.width * 6, img.height * 6), Image.NEAREST)
    img = img.point(lambda p: 255 if p > 140 else 0)
    # 若黑底白字则反相，保证输出为白底黑字（# 为笔画）
    avg = sum(img.get_flattened_data() if hasattr(img, "get_flattened_data") else list(img.getdata())) / (img.width * img.height)
    if avg < 128:
        img = ImageOps.invert(img)
    tw = max(24, width)
    th = max(8, int(img.height * (tw / img.width) * 0.55))
    small = img.resize((tw, th), Image.NEAREST)
    lines = []
    for y in range(small.height):
        row = []
        for x in range(small.width):
            row.append("#" if small.getpixel((x, y)) < 128 else " ")
        lines.append("".join(row).rstrip())
    border = "+" + "-" * tw + "+"
    body = "\n".join("|" + ln.ljust(tw) + "|" for ln in lines)
    return border + "\n" + body + "\n" + border


def scale_for_gallery(data: bytes, factor: int = 8) -> bytes:
    """放大后保存，避免 70x36 在相册里几乎看不见。无 Pillow 则原样返回。"""
    mods = _pillow()
    if not mods:
        return data
    Image, _ImageOps = mods
    import io

    img = Image.open(io.BytesIO(data))
    big = img.resize((img.width * factor, img.height * factor), Image.NEAREST)
    out = io.BytesIO()
    # 相册兼容：一律存 JPEG
    if big.mode not in ("RGB", "L"):
        big = big.convert("RGB")
    elif big.mode == "L":
        big = big.convert("RGB")
    big.save(out, format="JPEG", quality=95)
    return out.getvalue()


def termux_storage_dirs() -> list[Path]:
    """Termux shared storage 候选目录（已存在的）。"""
    home = Path.home()
    candidates = [
        home / "storage" / "downloads",
        home / "storage" / "shared" / "Download",
        home / "storage" / "shared" / "Pictures",
        home / "storage" / "pictures",
        home / "storage" / "dcim",
        home / "storage" / "shared" / "DCIM",
    ]
    seen = set()
    out = []
    for p in candidates:
        try:
            rp = p.resolve()
        except OSError:
            continue
        if not p.is_dir():
            continue
        key = str(rp)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def captcha_candidate_paths(filename: str = "jlu_cas_captcha.jpg") -> list[Path]:
    paths = [d / filename for d in termux_storage_dirs()]
    paths.append(Path.cwd() / filename)
    # 去重保序
    seen = set()
    uniq = []
    for p in paths:
        k = str(p)
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def write_captcha_files(data: bytes, filename: str = "jlu_cas_captcha.jpg") -> list[Path]:
    """写入多个位置（原图像素 + 放大版 *_large.jpg）。返回成功写入的路径。"""
    validate_captcha_bytes(data)
    large = scale_for_gallery(data)
    saved: list[Path] = []
    for path in captcha_candidate_paths(filename):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if path.stat().st_size < 50:
                raise CaptchaImageError(f"写入后文件过小：{path}")
            saved.append(path)
            # 放大副本便于相册查看
            large_path = path.with_name(path.stem + "_large.jpg")
            large_path.write_bytes(large)
            if large_path.stat().st_size >= 50:
                saved.append(large_path)
        except OSError:
            continue
    if not saved:
        # 最后手段：当前目录
        fallback = Path.cwd() / filename
        fallback.write_bytes(data)
        saved.append(fallback)
    return saved


def media_scan(paths: Iterable[Path]) -> Optional[str]:
    """调用 termux-media-scan 让相册立刻看到新文件。"""
    exe = shutil.which("termux-media-scan")
    if not exe:
        return None
    args = [exe]
    existing = [str(p) for p in paths if p.is_file()]
    if not existing:
        return None
    try:
        subprocess.run(args + existing, check=False, capture_output=True, timeout=15)
        return "termux-media-scan ok: " + ", ".join(existing)
    except (OSError, subprocess.SubprocessError) as e:
        return f"termux-media-scan failed: {e}"


_ocr_engine = None


def ocr_digits(data: bytes) -> Optional[str]:
    """尝试识别 4 位数字验证码。优先内置 Pillow kNN 求解器，再尝试 ddddocr。"""
    try:
        from . import captcha_solver

        pred = captcha_solver.solve_captcha(data)
        if pred:
            return pred
    except Exception:
        pass

    global _ocr_engine
    try:
        import ddddocr
    except ImportError:
        return None

    try:
        if _ocr_engine is None:
            _ocr_engine = ddddocr.DdddOcr(show_ad=False)
        text = _ocr_engine.classification(data)
    except Exception:
        return None

    digits = re.sub(r"\D", "", text or "")
    if len(digits) == 4:
        return digits
    return None


def _ocr_digits_pillow_simple(data: bytes) -> Optional[str]:
    """无 ddddocr 时不做不可靠猜测，直接返回 None（保留扩展点）。"""
    if not has_pillow():
        return None
    # 预留：可在此加模板匹配；CAS 验证码噪声较多，默认不瞎猜
    return None
