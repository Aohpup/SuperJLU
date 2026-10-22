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
