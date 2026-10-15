"""Grade rules, transcript isolation and reusable selections."""
import base64
import io
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from openpyxl import Workbook

from jlu_toolkit import core, grade_calculator as calc, jwxt, ui


def transcript(rows):
    return ("课程名称,课程性质,总成绩,学分,绩点,学年学期\n" + rows).encode("utf-8-sig")


def import_into(store, rows):
    store.import_grades("demo.csv", base64.b64encode(transcript(rows)).decode())


def test_template_rules_and_weighted_results():
    courses = calc.courses_from_bytes("demo.csv", transcript(
        "高数,必修,90,4,3.8,T1\n军事理论,必修,80,2,3,T1\n军事训练,必修,优秀,2,4,T1\n"
        "大学英语,必修,88,2,3.4,T1\n通用学术英语,必修,90,2,4,T1\n"
        "体育,必修,95,1,4,T1\n专业选修,限选,85,2,3.5,T1\n"))
    picked = lambda base: [c.name for c in courses if calc.builtin_selected(base, c)]
    assert picked("postgraduate") == ["高数", "大学英语"]
    assert picked("scholarship") == ["高数", "军事理论"]
    result = calc.calculate_selection(courses, [c.name in picked("scholarship") for c in courses])
    assert result["weighted_score"] == pytest.approx(520 / 6)
    assert result["weighted_gpa"] == pytest.approx(21.2 / 6)


def test_import_keeps_jwxt_grades_and_missing_points(tmp_path):
    jwxt.export_grades_csv([core.Grade("教务课程", 3, "91", "T1", 3.9, "必修")], str(tmp_path / "grades.csv"))
    store = ui.Store(tmp_path)
    before = store.p("grades.csv").read_bytes()
    import_into(store, "导入课程,必修,85,2,,T1\n")
    record = store.grade_records("import")[0]
    assert record["point"] is None and record["point_source"] == "missing"
    assert store.snapshot("import")["grade_source"] == "import"
    assert store.p("grades.csv").read_bytes() == before
    store.p("imported_grades.json").unlink()
    record = store.grade_records("import")[0]
    assert record["name"] == "教务课程" and record["point"] == 3.9


def test_duplicate_identity_and_reusable_overrides(tmp_path):
    store = ui.Store(tmp_path)
    rows = "课程A,必修,90,2,4,T1\n课程A,必修,80,2,3,T1\n选修课,选修,90,2,4,T1\n"
    import_into(store, rows)
    records = store.grade_records("import")
    assert len({g["key"] for g in records}) == 3
    selected = [records[0]["key"], records[2]["key"]]
    store.save_scheme("我的模板", selected, "postgraduate", "import")
    rule = store.snapshot("import")["scheme_rules"]["我的模板"]
    assert rule["overrides"] == {records[1]["key"]: False, records[2]["key"]: True}
    import_into(store, rows + "新增必修,必修,95,1,4,T2\n")
    rule = store.snapshot("import")["scheme_rules"]["我的模板"]
    actual = [g["key"] for g in store.grade_records("import") if rule["overrides"].get(g["key"], g["builtin"][rule["base"]])]
    assert actual == selected + [store.grade_records("import")[-1]["key"]]
    # Saving while a previously overridden course is absent must retain its rule.
    import_into(store, "课程A,必修,90,2,4,T1\n")
    store.save_scheme("我的模板", [store.grade_records("import")[0]["key"]], "postgraduate", "import")
    assert store.snapshot("import")["scheme_rules"]["我的模板"]["overrides"] == rule["overrides"]


def test_csv_aliases_encoding_and_title_rows():
    text = "示例成绩单\nCourse Name;分数;Credits;Nature;Year;Term\nA;90;2;required;2025;1\n"
    courses = calc.courses_from_bytes("demo.csv", text.encode("gb18030"))
    assert courses[0].term == "2025 / 1" and courses[0].score == 90
    assert not courses[0].gpa_valid
    assert any("绩点" in note for note in courses.import_notes)


def test_excel_uses_first_recognizable_sheet():
    content = io.BytesIO()
    workbook = Workbook()
    workbook.active.title = "封面"
    workbook.active.append(["无关工作表"])
    sheet = workbook.create_sheet("成绩")
    sheet.append(["课程名", "成绩", "学分", "绩点"])
    sheet.append(["测试课", 85, 2, 3.4])
    workbook.save(content)
    workbook.close()
    courses = calc.courses_from_bytes("demo.xlsx", content.getvalue())
    assert courses[0].gpa == 3.4
    assert "成绩" in courses.import_notes[0]


def test_inference_rejects_ambiguous_scores():
    with pytest.raises(ValueError, match="多个可能的成绩列"):
        calc.courses_from_bytes("demo.csv", "课程,学分,未知甲,未知乙\nA,2,80,90\nB,2,85,95\nC,2,90,99\n".encode())


@pytest.mark.parametrize("filename", ["broken.xlsx", "broken.xls"])
def test_corrupt_workbook_is_a_validation_error(filename):
    with pytest.raises(ValueError, match="文件"):
        calc.courses_from_bytes(filename, b"not a workbook")


def test_nature_export_backwards_compatibility(tmp_path):
    grade = jwxt.row_to_grade({"KCM": "高数", "XF": "4", "ZCJ": "90", "XNXQDM": "T1", "KCXZDM_DISPLAY": "必修"})
    assert grade.nature == "必修"
    path = tmp_path / "grades.csv"
    jwxt.export_grades_csv([grade], str(path))
    assert core.load_grades(str(path))[0].nature == "必修"
    path.write_text("课程,学分,成绩,学期\n旧数据,2,85,T1\n", encoding="utf-8")
    assert core.load_grades(str(path))[0].nature == ""


def test_unknown_and_nonfinite_values_are_explicit():
    courses = calc.courses_from_bytes("demo.csv", transcript("A,必修,待定,2,NaN,T1\nB,必修,90,inf,inf,T1\n"))
    assert not courses[0].score_valid and not courses[0].gpa_valid
    assert courses[1].credit == 0 and not courses[1].gpa_valid
    result = calc.calculate_selection(courses, [True, False])
    assert result["invalid_scores"] == 1 and result["weighted_gpa"] is None


def test_default_source_is_jwxt_even_with_saved_import(tmp_path):
    store = ui.Store(tmp_path)
    jwxt.export_grades_csv([core.Grade("当前账号课程", 3, "91", "T1", 3.9, "必修")],
                          str(store.p("grades.csv")))
    import_into(store, "文件课程,必修,85,2,3.5,T1\n")
    default = store.snapshot()
    assert default["grade_source"] == "jwxt"
    assert default["has_imported_grades"] is True
    assert default["grade_filename"] is None and default["grade_notes"] == []
    assert [g["name"] for g in default["grades"]] == ["当前账号课程"]
    assert store.snapshot("import")["grades"][0]["name"] == "文件课程"
    assert ui.Store(tmp_path).snapshot()["grade_source"] == "jwxt"  # Also after restart.


def test_grade_sync_uses_saved_login_and_preserves_optional_import(tmp_path, monkeypatch):
    store = ui.Store(tmp_path)
    import_into(store, "文件课程,必修,85,2,3.5,T1\n")
    imported = store.p("imported_grades.json").read_bytes()
    class Client:
        saved = False
        def fetch_grades(self):
            return [core.Grade("同步课程", 3, "90", "T2", 4, "必修")]
        def save_session(self):
            self.saved = True
    client = Client()
    monkeypatch.setattr(ui, "_client", lambda: client)
    assert ui.refresh_grades_from_jwxt(store) == {"ok": True, "count": 1}
    assert client.saved
    assert store.snapshot()["grades"][0]["name"] == "同步课程"
    assert store.p("imported_grades.json").read_bytes() == imported
    previous = store.p("grades.csv").read_bytes()
    def fail():
        raise jwxt.NetworkError("offline")
    monkeypatch.setattr(client, "fetch_grades", fail)
    with pytest.raises(jwxt.NetworkError):
        ui.refresh_grades_from_jwxt(store)
    assert store.p("grades.csv").read_bytes() == previous


def test_import_api_failure_preserves_previous_data(tmp_path):
    store = ui.Store(tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(store))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    def post(path, body):
        req = urllib.request.Request(url + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)
    try:
        code, result = post("/api/grades/import", {"filename": "demo.csv", "data": base64.b64encode(transcript("A,必修,90,2,4,T1\n")).decode()})
        assert code == 200 and result["grades"][0]["name"] == "A"
        before = store.p("imported_grades.json").read_bytes()
        code, result = post("/api/grades/import", {"filename": "demo.csv", "data": "invalid"})
        assert code == 400 and not result["ok"]
        assert store.p("imported_grades.json").read_bytes() == before
        code, result = post("/api/grades/source", {})
        assert code == 200 and result["grade_source"] == "jwxt"
        assert store.p("imported_grades.json").read_bytes() == before
        with urllib.request.urlopen(url + "/api/data") as response:
            assert json.load(response)["grade_source"] == "jwxt"
        with urllib.request.urlopen(url + "/api/data?grade_source=import") as response:
            assert json.load(response)["grades"][0]["name"] == "A"
    finally:
        server.shutdown()
        server.server_close()


def test_corrupt_import_falls_back_to_jwxt(tmp_path):
    store = ui.Store(tmp_path)
    jwxt.export_grades_csv([core.Grade("当前账号课程", 3, "91", "T1", 3.9, "必修")],
                          str(store.p("grades.csv")))
    store.p("imported_grades.json").write_text('{"grades": [{"bogus": 1}]}', encoding="utf-8")
    snap = store.snapshot("import")
    assert [g["name"] for g in snap["grades"]] == ["当前账号课程"]
    store.p("imported_grades.json").write_text('[]', encoding="utf-8")
    assert store.snapshot("import")["grade_source"] == "jwxt"


def test_automatic_grade_sync_is_throttled(tmp_path, monkeypatch):
    store = ui.Store(tmp_path)
    jwxt.export_grades_csv([core.Grade("课", 2, "90", "T1", 3.8, "必修")], str(store.p("grades.csv")))
    def boom():
        raise AssertionError("fresh cache must not hit CAS")
    monkeypatch.setattr(ui, "_client", boom)
    r = ui.refresh_grades_from_jwxt(store, automatic=True)
    assert r["skipped"] and r["count"] == 1
    with pytest.raises(AssertionError):
        ui.refresh_grades_from_jwxt(store, automatic=False)


def test_import_size_limit_is_5mb():
    assert calc.MAX_UPLOAD_BYTES == 5 * 1024 * 1024
