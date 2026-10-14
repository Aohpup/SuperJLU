import argparse
import getpass
import json
import sys

from . import core
from . import jwxt


def main():
    p = argparse.ArgumentParser(prog="jlu-toolkit", description="吉大课表/成绩本地工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ics", help="课表 CSV 导出 iCal")
    a.add_argument("csv")
    a.add_argument("--first-monday", required=True)
    a.add_argument("-o", default="schedule.ics")

    b = sub.add_parser("gpa", help="计算绩点")
    b.add_argument("csv")
    b.add_argument("--term")

    c = sub.add_parser("today", help="查看某周某天的课")
    c.add_argument("csv")
    c.add_argument("--week", type=int, required=True)
    c.add_argument("--weekday", type=int, required=True)

    f = sub.add_parser(
        "fetch",
        help="从教务系统拉取课表/成绩并导出 CSV（需校园网或 VPN）",
    )
    f.add_argument("--user", help="学号；省略则尝试读取本地已保存凭据")
    f.add_argument(
        "--password",
        help="密码；强烈不建议在命令行传入（会出现在 shell 历史）。省略则交互输入",
    )
    f.add_argument(
        "--save-credentials",
        action="store_true",
        help="可选：把账号密码保存到 ~/.config/jlu-toolkit/credentials.json（chmod 600）",
    )
    f.add_argument(
        "--schedule-out",
        default="schedule.csv",
        help="课表 CSV 输出路径（默认 schedule.csv）",
    )
    f.add_argument(
        "--grades-out",
        default="grades.csv",
        help="成绩 CSV 输出路径（默认 grades.csv）",
    )
    f.add_argument("--term", help="学期代码，如 2025-2026-2；默认当前学期")
    f.add_argument(
        "--what",
        choices=("all", "schedule", "grades"),
        default="all",
        help="拉取内容（默认 all）",
    )
    f.add_argument(
        "--probe",
        action="store_true",
        help="只探测 CAS/教务是否可达，不登录",
    )

    x = p.parse_args()
    if x.cmd == "ics":
        open(x.o, "w", encoding="utf-8").write(
            core.to_ics(core.load_courses(x.csv), x.first_monday)
        )
        print(f"已导出 {x.o}")
    elif x.cmd == "gpa":
        print(json.dumps(core.gpa(core.load_grades(x.csv), x.term), ensure_ascii=False))
    elif x.cmd == "today":
        for k in core.courses_on(core.load_courses(x.csv), x.week, x.weekday):
            print(f"第{k.start}-{k.end}节 {k.name} @ {k.location}")
    elif x.cmd == "fetch":
        _cmd_fetch(x)


def _cmd_fetch(x):
    if x.probe:
        print(json.dumps(jwxt.probe_reachability(), ensure_ascii=False, indent=2))
        return

    username = x.user
    password = x.password
    if not username or not password:
        saved = jwxt.load_credentials()
        if saved:
            if not username:
                username = saved[0]
            if not password:
                password = saved[1]
                print(f"使用本地已保存账号：{username}", file=sys.stderr)
    if not username:
        print("请用 --user 指定学号，或先 --save-credentials 保存一次。", file=sys.stderr)
        sys.exit(2)
    if not password:
        password = getpass.getpass(f"请输入 {username} 的统一身份认证密码：")

    client = jwxt.JwxtClient()
    try:
        print("正在登录统一身份认证…", file=sys.stderr)
        client.login(username, password)
    except jwxt.LoginError as e:
        print(f"登录失败：{e}", file=sys.stderr)
        sys.exit(1)
    except jwxt.NetworkError as e:
        print(f"网络错误：{e}", file=sys.stderr)
        print(
            "提示：CAS（cas.jlu.edu.cn）公网可访问；教务（iedu.jlu.edu.cn）"
            "通常需要校园网或学校 VPN。",
            file=sys.stderr,
        )
        sys.exit(1)

    if x.save_credentials:
        path = jwxt.save_credentials(username, password)
        print(f"已保存凭据到 {path}（权限 600）", file=sys.stderr)

    # 登录成功后立刻丢掉内存中的密码引用（尽最大努力）
    password = None  # noqa: F841

    if x.what in ("all", "schedule"):
        courses = client.fetch_schedule(x.term)
        jwxt.export_courses_csv(courses, x.schedule_out)
        print(f"课表 {len(courses)} 门 → {x.schedule_out}")
    if x.what in ("all", "grades"):
        grades = client.fetch_grades()
        jwxt.export_grades_csv(grades, x.grades_out)
        print(f"成绩 {len(grades)} 条 → {x.grades_out}")
        print(json.dumps(core.gpa(grades), ensure_ascii=False))


if __name__ == "__main__":
    main()
