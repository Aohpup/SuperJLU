from jlu_toolkit.ui import Store


def test_grade_help_seen_persists(tmp_path):
    st = Store(tmp_path)
    st.save_settings({"grade_help_seen": True})
    assert Store(tmp_path).settings()["grade_help_seen"] is True
