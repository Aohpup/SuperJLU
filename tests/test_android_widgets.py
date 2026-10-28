import shutil, subprocess
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_swipe_and_widget_export_js():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, str(ROOT / "tests" / "js_swipe_widget_test.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_page_has_android_extras_card():
    from jlu_toolkit.ui_page import PAGE
    assert 'id="android-extras"' in PAGE and "<!--ANDROID_EXTRAS_CARD-->" not in PAGE


def test_manifest_declares_widgets_and_boot():
    m = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    for s in ("TodayWidget", "WeekWidget", "NextWidget", "BOOT_COMPLETED", "REQUEST_IGNORE_BATTERY_OPTIMIZATIONS", "POST_NOTIFICATIONS"):
        assert s in m


def test_widget_providers_picker_friendly():
    import re
    xml = ROOT / "android/app/src/main/res/xml"
    for n in ("today", "week", "next"):
        t = (xml / f"widget_{n}_info.xml").read_text(encoding="utf-8")
        assert 'android:widgetCategory="home_screen"' in t  # 不带 keyguard：ColorOS 等会隐藏
        assert "android:previewImage=" in t and "android:minWidth=" in t and "android:minHeight=" in t
        img = re.search(r'previewImage="@drawable/(\w+)"', t).group(1)
        assert (ROOT / f"android/app/src/main/res/drawable-nodpi/{img}.png").exists()
    m = (ROOT / "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert m.count("android.appwidget.provider") == 3 and "LOCALE_CHANGED" in m
