"""一键同步：用已保存会话把课表/成绩/考试/校历/节次/官方绩点/学业完成写入数据目录。

返回的摘要只含条数、成功/失败与非个人信息（学期代码、开学日期、节次数），
可安全打印或贴给他人；个人数值（绩点、学分、成绩）只写入本地文件。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import exams as ex, jwxt, meta


def _wjson(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def sync_all(client: "jwxt.JwxtClient", root: Path, term: str | None = None) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    s: dict = {}

    def step(name, fn):
        try:
            s[name] = fn()
        except jwxt.LoginError:
            raise
        except (jwxt.JwxtError, ValueError, KeyError) as e:
            s[name] = {"ok": False, "error": str(e)[:200]}

    term = term or client.current_semester()
    s["term"] = term

    def _courses():
        cs = client.fetch_schedule(term)
        jwxt.export_courses_csv(cs, str(root / "schedule.csv"))
        return {"ok": True, "count": len(cs)}

    def _grades():
        gs = client.fetch_grades()
        jwxt.export_grades_csv(gs, str(root / "grades.csv"))
        return {"ok": True, "count": len(gs)}

    def _exams():
        es = client.fetch_exams(term)
        ex.export_exams_csv(es, str(root / "exams.csv"))
        return {"ok": True, "count": len(es)}

    def _cal():
        c = meta.fetch_calendar(client, term)
        _wjson(root / "calendar.json", c)
        return {"ok": True, **c}

    def _periods():
        p = meta.fetch_periods(client)
        _wjson(root / "periods.json", p)
        return {"ok": True, "count": len(p), "first": p.get("1"), "last_section": max(map(int, p))}

    def _gpa():
        g = meta.fetch_official_gpa(client)
        _wjson(root / "official_gpa.json", g)
        return {"ok": True, "fields": [i["key"] for i in g["items"]]}

    def _prog():
        c = meta.fetch_completion(client)
        _wjson(root / "completion.json", c)
        return {"ok": True, "groups": len(c["groups"]),
                "has_required": c["required"] is not None, "has_earned": c["earned"] is not None}

    for name, fn in (("schedule", _courses), ("grades", _grades), ("exams", _exams),
                     ("calendar", _cal), ("periods", _periods),
                     ("official_gpa", _gpa), ("completion", _prog)):
        step(name, fn)
    client.save_session()
    return s
