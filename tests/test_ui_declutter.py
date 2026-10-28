from pathlib import Path

from jlu_toolkit.ui_page import PAGE

ROOT = Path(__file__).resolve().parents[1]


def test_timetable_shows_end_time():
    assert "function kbTime(c,m)" in PAGE
    assert 'a[0]+"–"+b[1]' in PAGE and 'class="tm"' in PAGE
    assert '<em class="pe">${pt[1]}</em>' in PAGE


def test_android_offcampus_banner_removed():
    for rel in ("android/app/src/main/res/values/strings.xml",
                "android/app/src/main/res/layout/activity_main.xml",
                "android/app/src/main/java/cn/superjlu/app/MainActivity.java"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "offcampus_banner" not in text and "R.id.banner" not in text
    assert "campus_reachable" not in (ROOT / "android/app/src/main/python/jlu_android.py").read_text(encoding="utf-8")


def test_campus_links_are_compact_tiles():
    assert "不常用但用得到的入口" not in PAGE
    assert 'class="lgrid"' in PAGE and 'class="go"' in PAGE
    assert "minmax(88px,1fr)" in PAGE
