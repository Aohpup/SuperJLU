"""一键同步：用已保存会话把课表/成绩/考试/校历/节次/官方绩点/学业完成写入数据目录。

返回的摘要只含条数、成功/失败与非个人信息（学期代码、开学日期、节次数），
可安全打印或贴给他人；个人数值（绩点、学分、成绩）只写入本地文件。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import exams as ex, jwxt, meta


def _wjson(path: Path, obj) -> None:
    from .endpoints import scrub
    path.write_text(json.dumps(scrub(obj), ensure_ascii=False, indent=1), encoding="utf-8")


def sync_all(client: "jwxt.JwxtClient", root: Path, term: str | None = None) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    s: dict = {}

    def step(name, fn):
        try:
            s[name] = fn()
        except jwxt.LoginError:
            raise
        except meta.Unavailable as e:
            s[name] = {"ok": True, "available": False, "note": str(e)[:300]}
        except (jwxt.JwxtError, ValueError, KeyError) as e:
            s[name] = {"ok": False, "error": str(e)[:200]}

    term = term or client.current_semester()
    s["term"] = term

    courses_cache: list = []

    def _courses():
        cs = client.fetch_schedule(term)
        courses_cache.extend(cs)
        jwxt.export_courses_csv(cs, str(root / "schedule.csv"))
        return {"ok": True, "count": len(cs)}

    grades_cache: list = []

    def _grades():
        gs = client.fetch_grades()
        grades_cache.extend(gs)
        jwxt.export_grades_csv(gs, str(root / "grades.csv"))
        return {"ok": True, "count": len(gs),
                "with_jw_point": sum(1 for g in gs if getattr(g, "jw_point", None) is not None)}

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
        try:
            g = meta.fetch_official_gpa(client, grades=grades_cache)
        except meta.Unavailable as e:
            _wjson(root / "official_gpa.json", {"available": False, "note": str(e)[:300], "items": []})
            raise
        _wjson(root / "official_gpa.json", g)
        return {"ok": True, "source": g.get("source"), "fields": [i["key"] for i in g["items"]]}

    def _prog():
        c = meta.fetch_completion(client, grades=grades_cache)
        _wjson(root / "completion.json", c)
        return {"ok": True, "groups": len(c["groups"]),
                "has_required": c["required"] is not None, "has_earned": c["earned"] is not None,
                "groups_with_earned": sum(1 for g in c["groups"] if g.get("earned") is not None),
                "groups_derived": c.get("groups_derived", 0)}

    def _plan():
        from . import plan as pl
        p = pl.fetch_plan(client, grades=grades_cache, courses_now=courses_cache)
        _wjson(root / "plan_courses.json", p)
        cf = root / "completion.json"
        if cf.exists():
            comp = json.loads(cf.read_text(encoding="utf-8"))
            _wjson(cf, pl.attach_to_completion(comp, p))
        st: dict = {}
        for c in p["courses"]:
            st[c["status"]] = st.get(c["status"], 0) + 1
        return {"ok": True, "count": p["count"], "source": p["source"], "status_counts": st,
                "with_group": sum(1 for c in p["courses"] if c.get("group") or c.get("group_code"))}

    for name, fn in (("schedule", _courses), ("grades", _grades), ("exams", _exams),
                     ("calendar", _cal), ("periods", _periods),
                     ("official_gpa", _gpa), ("completion", _prog), ("plan_courses", _plan)):
        step(name, fn)
    client.save_session()
    return s
