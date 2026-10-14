import argparse, json
from . import core

def main():
    p = argparse.ArgumentParser(prog="jlu-toolkit", description="吉大课表/成绩本地工具")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ics", help="课表 CSV 导出 iCal"); a.add_argument("csv"); a.add_argument("--first-monday", required=True); a.add_argument("-o", default="schedule.ics")
    b = sub.add_parser("gpa", help="计算绩点"); b.add_argument("csv"); b.add_argument("--term")
    c = sub.add_parser("today", help="查看某周某天的课"); c.add_argument("csv"); c.add_argument("--week", type=int, required=True); c.add_argument("--weekday", type=int, required=True)
    x = p.parse_args()
    if x.cmd == "ics":
        open(x.o, "w", encoding="utf-8").write(core.to_ics(core.load_courses(x.csv), x.first_monday)); print(f"已导出 {x.o}")
    elif x.cmd == "gpa":
        print(json.dumps(core.gpa(core.load_grades(x.csv), x.term), ensure_ascii=False))
    else:
        for k in core.courses_on(core.load_courses(x.csv), x.week, x.weekday):
            print(f"第{k.start}-{k.end}节 {k.name} @ {k.location}")

if __name__ == "__main__": main()
