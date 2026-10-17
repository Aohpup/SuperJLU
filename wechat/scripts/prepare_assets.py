"""Generate bundled demo records and small drawn tab icons; no network needed."""
import json
import sys
from pathlib import Path
from dataclasses import asdict
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import adapter
from jlu_toolkit import core, exams
demo = ROOT / "server/vendor/jlu_toolkit/data/demo"
data = {
    "courses": [asdict(c) for c in core.load_courses(demo / "schedule.csv")],
    "grades": adapter.grade_records(core.load_grades(demo / "grades.csv")),
    "exams": [asdict(e) for e in exams.load_exams(demo / "exams.csv")],
    "updated": "2026-10-16T09:00:00+08:00", "first_monday": "2026-09-07", "failures": []
}
for name in ["calendar", "periods", "completion", "official_gpa"]:
    data[name] = json.loads((demo / (name + ".json")).read_text(encoding="utf-8"))
data["plan_courses"] = {"courses": [
    {"name":"数据结构","credit":4,"nature":"必修","status":"在修","group":"专业必修课"},
    {"name":"操作系统","credit":4,"nature":"必修","status":"在修","group":"专业必修课"},
    {"name":"高等数学A（上）","credit":5,"nature":"必修","status":"已修","group":"学科基础课"},
    {"name":"编译原理","credit":3,"nature":"必修","status":"未修","group":"专业必修课"}]}
path = ROOT / "miniprogram/data"
path.mkdir(exist_ok=True)
(path / "demo.js").write_text("// Bundled synthetic examples from upstream, plus sample plan rows.\nmodule.exports = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
links = json.loads((demo.parent / "campus_links.json").read_text(encoding="utf-8"))["links"]
(path / "links.js").write_text("module.exports = " + json.dumps(links, ensure_ascii=False, indent=2) + ";\n", encoding="utf-8")
from PIL import Image, ImageDraw
assets = ROOT / "miniprogram/assets"
assets.mkdir(exist_ok=True)
for kind in ["home", "schedule", "grades", "campus", "profile"]:
    for active in [False, True]:
        img = Image.new("RGBA", (80, 80))
        d = ImageDraw.Draw(img)
        c = "#157a67" if active else "#87978e"
        if kind == "home":
            d.line([(13,36),(40,14),(67,36)],fill=c,width=5)
            d.line([(21,31),(21,65),(59,65),(59,31)],fill=c,width=5)
            d.rectangle([35,46,45,65],outline=c,width=4)
        elif kind == "schedule":
            d.rounded_rectangle([15,21,65,66],radius=6,outline=c,width=5)
            d.line([(15,35),(65,35)],fill=c,width=4)
            for x in [29,51]:
                d.line([(x,13),(x,27)],fill=c,width=5)
            for x in [29,48]:
                for y in [44,54]:
                    d.rectangle([x,y,x+5,y+5],fill=c)
        elif kind == "grades":
            d.line([(18,16),(18,65),(67,65)],fill=c,width=4)
            for x,y in [(29,44),(43,33),(57,20)]:
                d.rounded_rectangle([x,y,x+8,58],radius=2,fill=c)
        elif kind == "campus":
            d.polygon([(13,30),(40,15),(67,30)],outline=c,width=4)
            for x in [23,38,53]:
                d.line([(x,36),(x,60)],fill=c,width=5)
            d.line([(15,65),(65,65)],fill=c,width=5)
        else:
            d.ellipse([28,13,52,37],outline=c,width=5)
            d.arc([15,41,65,85],180,360,fill=c,width=5)
        img.save(assets / (kind + ("-active" if active else "") + ".png"))
print("Demo records and 10 tab icons generated.")
