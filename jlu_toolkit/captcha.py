"""可复用的图形验证码自动识别（CAS /tpass/code 四位数字，CLI 与 App 登录共用）。

    from jlu_toolkit import captcha
    code = captcha.solve(image_bytes)          # 识别不出返回 ""
    result = captcha.solve_with_retry(fetch, submit, tries=6)

``fetch()`` 返回一张新验证码的 bytes；``submit(code)`` 返回 True 表示通过，
False 表示验证码错误需换一张，其他异常原样抛出。供以后的缴费 / 选课登录复用；
识别器是 ``captcha_solver``（内置模板 + Pillow），可选回退 ddddocr。
"""
from __future__ import annotations

from typing import Callable, Optional

from . import captcha_util


def available() -> bool:
    return captcha_util.has_pillow() or captcha_util.has_ddddocr()


def solve(image_bytes: bytes) -> str:
    if not image_bytes:
        return ""
    try:
        return captcha_util.ocr_digits(image_bytes) or ""
    except Exception:  # noqa: BLE001
        return ""


def solve_with_retry(fetch: Callable[[], bytes], submit: Callable[[str], bool],
                     tries: int = 6, skip: tuple = (), budget: Optional[float] = None) -> Optional[str]:
    """反复取图→识别→提交，成功返回所用验证码，全失败返回 None。``skip`` 内的异常视为本次失败继续。
    ``budget``：总耗时上限（秒），超过后不再开始新一轮，避免单个请求挂几分钟。"""
    import time
    t0 = time.monotonic()
    for i in range(max(1, tries)):
        if budget is not None and i and time.monotonic() - t0 > budget:
            break
        try:
            code = solve(fetch())
        except skip:
            continue
        if code and submit(code):
            return code
    return None
