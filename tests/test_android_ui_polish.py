from pathlib import Path
from jlu_toolkit.ui_page import PAGE

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "android/app/src/main/java/cn/superjlu/app/MainActivity.java").read_text(encoding="utf-8")
PICKER = (ROOT / "android/app/src/main/java/cn/superjlu/app/BrowserPicker.java").read_text(encoding="utf-8")


def test_bars_follow_resolved_page_colors():
    assert "setBarColors" in MAIN and "getDecorView().setBackgroundColor(bg)" in MAIN
    assert "window.__sjBars" in PAGE and 'prefers-color-scheme: dark)").addEventListener("change"' in PAGE


def test_android_nav_has_no_double_bottom_inset():
    assert ".in-app nav{padding-bottom:4px}" in PAGE
    assert ".in-app body{padding-bottom:84px}" in PAGE


def test_empty_cell_shows_double_tap_hint():
    assert 'content:"双击添加课程"' in PAGE
    assert "function kbHint(" in PAGE and ".cell.hint::after" in PAGE


def test_manual_update_check_says_latest():
    assert "当前已是最新版本哦！" in PAGE


def test_ask_mode_offered_with_in_app_list():
    assert "browser_always_ask" in PICKER and "showAskDialog" in PICKER
    assert "if (MODE_ASK.equals(mode)) mode = MODE_SYSTEM" not in PICKER


# --- trial feedback round 2 -------------------------------------------------
from pathlib import Path as _P

_ROOT = _P(__file__).resolve().parents[1]


def test_ask_every_time_listed_above_follow_system_but_not_default():
    src = (_ROOT / "android/app/src/main/java/cn/superjlu/app/BrowserPicker.java").read_text("utf-8")
    body = src[src.index("void showSettings()"):]
    assert body.index("R.string.browser_always_ask") < body.index("R.string.browser_follow_system")
    assert "final int[] selection = {1};" in body
    assert 'preferences.getString("mode", MODE_SYSTEM)' in body


def test_update_check_up_to_date_is_not_failure():
    from jlu_toolkit import update_check as uc
    r = uc.check(force=True, fetch=lambda t: {"tag_name": "v" + uc.__version__,
                 "html_url": "https://github.com/Runa-Asahi/SuperJLU/releases/tag/v1"})
    assert r["has_update"] is False and not r.get("unavailable")
    r = uc.check(force=True, fetch=lambda t: {})
    assert r["has_update"] is False and not r.get("unavailable")
    def boom(t):
        raise OSError("x")
    assert uc.check(force=True, fetch=boom).get("unavailable") is True


def test_update_check_prefers_native_transport_then_urllib(monkeypatch):
    from jlu_toolkit import update_check as uc
    calls = []
    def native(req, t):
        calls.append("native"); raise OSError("no native")
    def plain(req, t):
        calls.append("urllib")
        class R:
            code = 200
            headers = {}
            def read(self, n=-1): return b'{"tag_name": "v0.0.1"}'
        return R()
    monkeypatch.setattr(uc, "_native_ok", lambda: True)
    monkeypatch.setattr(uc, "_open_native", native)
    monkeypatch.setattr(uc, "_open_urllib", plain)
    assert uc._fetch(1) == {"tag_name": "v0.0.1"} and calls == ["native", "native", "urllib"]


def test_room_form_is_grouped_and_compact():
    from jlu_toolkit.ui_page import PAGE
    sec = PAGE[PAGE.index('id="t-js"'):PAGE.index('id="t-ks"')]
    for i in ("rcs", "rc", "rd", "rwd", "rw", "rp1", "rp2", "rst", "ret", "rst-presets",
              "rb", "rt", "rhs", "rs1", "rs2", "re1", "re2", "rextra", "rq"):
        assert f'id="{i}"' in sec, i
    assert sec.count('class="rgrp-h"') == 3
    assert "按照日期" not in sec and "按自习时间" not in sec
    assert 'class="btn ghost" data-sp' not in sec
