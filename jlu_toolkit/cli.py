import argparse
import getpass
import json
import sys

from . import core
from . import exams as exmod
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
        help="从教务系统拉取课表/成绩并导出 CSV（需校园网或 VPN；支持二次认证）",
    )
    f.add_argument(
        "--user",
        help="统一身份认证账号（邮箱前缀，不是学号）；省略则尝试本地已保存凭据或已保存会话",
    )
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
        "--force-login",
        action="store_true",
        help="忽略已保存会话，强制重新登录（含二次认证）",
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
        "--exams-out",
        default="exams.csv",
        help="考试安排 CSV 输出路径（默认 exams.csv）",
    )
    f.add_argument(
        "--what",
        choices=("all", "schedule", "grades", "exams"),
        default="all",
        help="拉取内容（默认 all）",
    )
    f.add_argument(
        "--probe",
        action="store_true",
        help="只探测 CAS/验证码/教务是否可达，不登录",
    )
    f.add_argument(
        "--debug",
        action="store_true",
        help="打印登录诊断信息（字段名/长度、HTTP 状态、最终 URL、重定向链、服务器错误文案；不打印密码）",
    )
    f.add_argument(
        "--show-captcha",
        action="store_true",
        help="在终端用 ASCII 显示图形验证码（默认关闭；自动识别失败时仍会提示手动输入）",
    )
    f.add_argument(
        "--no-auto-captcha",
        action="store_true",
        help="禁用图形验证码自动识别，始终手动输入",
    )

    e = sub.add_parser("exams", help="查看考试倒计时（读取 exams.csv）")
    e.add_argument("csv", nargs="?", default="exams.csv")
    e.add_argument("--all", action="store_true", help="包含已结束的考试")

    ex_p = sub.add_parser(
        "explore",
        help="只读探测教务各应用接口，生成脱敏报告（需已保存会话；不做任何写操作）",
    )
    ex_p.add_argument("--term", help="学期代码；默认自动取当前学期")
    ex_p.add_argument("-o", "--out", help="报告路径（默认 Termux 下载目录或当前目录 jlu_explore_report.json）")
    ex_p.add_argument("--debug", action="store_true")

    sy = sub.add_parser(
        "sync",
        help="用已保存会话同步全部数据到本地数据目录（课表/成绩/考试/校历/节次/官方绩点/学业完成）；非交互",
    )
    sy.add_argument("--term", help="学期代码；默认当前学期")
    sy.add_argument("--data-dir", help="数据目录（默认 ~/.config/jlu-toolkit/data）")
    sy.add_argument("--debug", action="store_true")

    u = sub.add_parser("ui", help="启动本地网页界面（127.0.0.1，手机浏览器打开）")
    u.add_argument("--port", type=int, default=8765)
    u.add_argument("--demo", action="store_true", help="使用示例数据（不读写真实数据目录）")
    u.add_argument("--data-dir", help="自定义数据目录")
    u.add_argument("--open", action="store_true", help="启动后尝试打开浏览器")

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
    elif x.cmd == "exams":
        _cmd_exams(x)
    elif x.cmd == "explore":
        _cmd_explore(x)
    elif x.cmd == "ui":
        _cmd_ui(x)
    elif x.cmd == "sync":
        _cmd_sync(x)


def _prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except EOFError:
        print("\n已取消。", file=sys.stderr)
        sys.exit(130)


def _interactive_second_factor(client: jwxt.JwxtClient, show_captcha: bool = False, auto_captcha: bool = True) -> None:
    """图形验证码（默认自动识别）+ 微信验证码交互。"""
    from . import captcha_util
    from . import captcha_solver

    print(
        "需要二次认证：图形验证码默认自动识别；微信验证码请到「智慧吉大」查看。",
        file=sys.stderr,
    )
    if auto_captcha:
        try:
            captcha_solver.load_templates()
        except Exception as e:
            print(f"自动识别不可用（{e}），改为手动输入。", file=sys.stderr)
            auto_captcha = False

    max_auto_tries = 5
    auto_try = 0
    while True:
        path = client.download_captcha()
        raw = client.last_captcha_bytes or path.read_bytes()
        if show_captcha:
            print(captcha_util.render_ascii(raw), file=sys.stderr)
            for p in client.last_captcha_paths or [path]:
                try:
                    print(f"  已保存 {p} ({p.stat().st_size} bytes)", file=sys.stderr)
                except OSError:
                    pass

        captcha = None
        if auto_captcha and auto_try < max_auto_tries:
            auto_try += 1
            try:
                captcha = captcha_solver.solve_captcha(raw)
            except RuntimeError as e:
                print(f"自动识别需要 Pillow：{e}", file=sys.stderr)
                auto_captcha = False
                captcha = None
            if captcha:
                print(f"图形验证码自动识别：{captcha}（第 {auto_try}/{max_auto_tries} 次）", file=sys.stderr)
            else:
                print(f"自动识别失败（第 {auto_try}/{max_auto_tries} 次），刷新重试…", file=sys.stderr)
                continue

        if not captcha:
            captcha = _prompt("请输入图形验证码（直接回车刷新图片）：")
            if not captcha:
                continue

        result = client.request_wechat_code(captcha)
        if result == jwxt.WechatCodeResult.CAPTCHA_ERROR:
            print("图形验证码错误。", file=sys.stderr)
            if auto_captcha and auto_try < max_auto_tries:
                print("自动刷新并重试…", file=sys.stderr)
                continue
            print("请手动输入。", file=sys.stderr)
            auto_captcha = False
            continue
        if result == jwxt.WechatCodeResult.TOO_FREQUENT:
            print("发送太频繁，请稍后再试。", file=sys.stderr)
            sys.exit(1)
        if result == jwxt.WechatCodeResult.SESSION_EXPIRED:
            print("二次认证会话已失效，请重新运行并完成密码登录。", file=sys.stderr)
            sys.exit(1)
        if result != jwxt.WechatCodeResult.SUCCESS:
            print(f"发送微信验证码失败（{result.value}）。", file=sys.stderr)
            sys.exit(1)
        print(
            "微信验证码已发送，请到「智慧吉大」查看「统一身份认证」消息。",
            file=sys.stderr,
        )
        wx = _prompt("请输入微信验证码：")
        if not wx:
            print("未输入微信验证码。", file=sys.stderr)
            sys.exit(2)
        step = client.login_second_factor(captcha, wx)
        if step == jwxt.LoginStep.SUCCESS:
            print("二次认证成功。", file=sys.stderr)
            return
        print("验证码不正确或已过期，请重试。", file=sys.stderr)
        again = _prompt("再试一次？[Y/n] ").lower()
        if again in ("n", "no", "q"):
            sys.exit(1)
        auto_try = 0  # allow auto again on full retry


def _ensure_login(x) -> jwxt.JwxtClient:
    debug = bool(getattr(x, "debug", False))
    client = jwxt.JwxtClient(debug=debug)

    if not x.force_login and client.load_session():
        print("发现本地会话，正在检测是否有效…", file=sys.stderr)
        if client.session_alive():
            print("会话有效，跳过登录。", file=sys.stderr)
            try:
                client.bootstrap_emap_apps()
                client.save_session()
            except (jwxt.LoginError, jwxt.JwxtError, jwxt.NetworkError) as e:
                print(f"会话探测通过但进入应用失败：{e}；将尝试继续。", file=sys.stderr)
            if getattr(x, "debug", False):
                print(f"[debug] {client.session_cookie_summary()}", file=sys.stderr)
            return client
        print("会话已失效，需要重新登录。", file=sys.stderr)
        client.clear_session_file()
        client = jwxt.JwxtClient(debug=debug)

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
        print(
            "请用 --user 指定邮箱前缀（统一身份认证账号，不是学号），"
            "或先 --save-credentials 保存一次。",
            file=sys.stderr,
        )
        sys.exit(2)
    if not password:
        try:
            password = getpass.getpass(f"请输入 {username} 的统一身份认证密码：")
        except Exception:
            # 部分 Termux 环境 getpass 异常时回退到可见输入
            password = _prompt(f"请输入 {username} 的统一身份认证密码（可见输入）：")

    try:
        print("正在提交账号密码…", file=sys.stderr)
        step = client.login_password(username, password)
    except jwxt.NetworkError as e:
        print(f"网络错误：{e}", file=sys.stderr)
        print(
            "提示：CAS（cas.jlu.edu.cn）公网可访问；教务（iedu.jlu.edu.cn）"
            "通常需要校园网或学校 VPN。",
            file=sys.stderr,
        )
        sys.exit(1)

    if step == jwxt.LoginStep.WRONG_PASSWORD:
        err = client.last_error_text
        if err:
            print(f"统一登录失败：服务器返回「{err}」。", file=sys.stderr)
        else:
            print("统一登录失败：用户名或密码错误。", file=sys.stderr)
        print(
            "账号请使用邮箱前缀（不要用学号；完整邮箱也可，会自动剥掉后缀）。"
            "可加 --debug 查看字段长度与响应详情。",
            file=sys.stderr,
        )
        sys.exit(1)
    if step == jwxt.LoginStep.NEED_SECOND_FACTOR:
        try:
            _interactive_second_factor(
                client,
                show_captcha=bool(getattr(x, "show_captcha", False)),
                auto_captcha=not bool(getattr(x, "no_auto_captcha", False)),
            )
        except jwxt.NetworkError as e:
            print(f"网络错误：{e}", file=sys.stderr)
            sys.exit(1)
        except jwxt.SecondFactorError as e:
            print(f"二次认证失败：{e}", file=sys.stderr)
            sys.exit(1)
    elif step != jwxt.LoginStep.SUCCESS:
        print(f"登录未完成（{step.value}）。", file=sys.stderr)
        sys.exit(1)
    else:
        print("密码登录成功（无需二次认证）。", file=sys.stderr)

    if x.save_credentials:
        path = jwxt.save_credentials(username, password)
        print(f"已保存凭据到 {path}（权限 600）", file=sys.stderr)
    password = None  # noqa: F841

    # 预进入课表/成绩应用，写入 _WEU 等，再落盘会话
    try:
        print("正在进入教务应用（课表/成绩）…", file=sys.stderr)
        client.bootstrap_emap_apps()
    except jwxt.LoginError as e:
        print(f"进入教务应用失败：{e}", file=sys.stderr)
        sys.exit(1)
    except jwxt.NetworkError as e:
        print(f"网络错误：{e}", file=sys.stderr)
        sys.exit(1)

    sess = client.save_session()
    summary = client.session_cookie_summary()
    print(f"已保存会话到 {sess}（权限 600）。", file=sys.stderr)
    if summary.get("has_CASTGC"):
        print(
            "会话含 CASTGC：下次若教务 Cookie 过期，仍可能靠它静默换票（通常无需再过微信验证）。",
            file=sys.stderr,
        )
    else:
        print(
            "注意：会话里没有 CASTGC（CAS 长期票据）。"
            "下次主要依赖教务站 Cookie；失效后需要 --force-login 再走一遍认证。",
            file=sys.stderr,
        )
    if getattr(x, "debug", False):
        print(f"[debug] cookies={summary.get('cookie_names')}", file=sys.stderr)
    return client


def _cmd_fetch(x):
    if x.probe:
        print(json.dumps(jwxt.probe_reachability(), ensure_ascii=False, indent=2))
        return

    try:
        client = _ensure_login(x)
    except jwxt.LoginError as e:
        print(f"登录失败：{e}", file=sys.stderr)
        sys.exit(1)

    try:
        if x.what in ("all", "schedule"):
            courses = client.fetch_schedule(x.term)
            jwxt.export_courses_csv(courses, x.schedule_out)
            print(f"课表 {len(courses)} 门 → {x.schedule_out}")
        if x.what in ("all", "grades"):
            grades = client.fetch_grades()
            jwxt.export_grades_csv(grades, x.grades_out)
            print(f"成绩 {len(grades)} 条 → {x.grades_out}")
            print(json.dumps(core.gpa(grades), ensure_ascii=False))
            print("（注：此为全部课程的简单学分加权；保研/综测口径请在 jlu-toolkit ui 里勾选课程）", file=sys.stderr)
        if x.what in ("all", "exams"):
            try:
                exs = client.fetch_exams(x.term)
                exmod.export_exams_csv(exs, x.exams_out)
                print(f"考试 {len(exs)} 场 → {x.exams_out}")
                _print_countdown(exs)
            except jwxt.JwxtError as e:
                if x.what == "exams":
                    raise
                print(f"（考试安排暂未获取：{e}）", file=sys.stderr)
    except jwxt.LoginError as e:
        print(f"{e}；可加 --force-login 重登。", file=sys.stderr)
        sys.exit(1)
    except jwxt.NetworkError as e:
        print(f"网络错误：{e}", file=sys.stderr)
        sys.exit(1)
    except jwxt.JwxtError as e:
        print(f"教务错误：{e}", file=sys.stderr)
        sys.exit(1)


def _print_countdown(exs, show_all: bool = False) -> None:
    items = exs if show_all else exmod.upcoming(exs)
    if not items:
        print("暂无未结束的考试。")
        return
    for e in items:
        when = e.start.replace("T", " ") if e.start else "时间待定"
        cd = exmod.format_countdown(exmod.countdown(e))
        print(f"⏱ {cd:<14} {e.name}  {when}  {e.location}" + (f"  座位{e.seat}" if e.seat else ""))


def _cmd_exams(x):
    try:
        exs = exmod.load_exams(x.csv)
    except FileNotFoundError:
        print(f"找不到 {x.csv}；先运行 jlu-toolkit fetch --what exams", file=sys.stderr)
        sys.exit(1)
    _print_countdown(exs, show_all=x.all)


def _cmd_explore(x):
    from . import explore

    client = jwxt.JwxtClient(debug=bool(x.debug))
    if not client.load_session():
        print("没有已保存的会话。请先运行 jlu-toolkit fetch --user 你的邮箱前缀 登录一次。", file=sys.stderr)
        sys.exit(1)
    print("开始只读探测（不会进行任何选课/退课/提交操作）…", file=sys.stderr)
    try:
        report = explore.run_explore(client, x.term, log=lambda m: print(m, file=sys.stderr))
    except jwxt.NetworkError as e:
        print(f"网络错误：{e}", file=sys.stderr)
        sys.exit(1)
    client.save_session()
    from pathlib import Path

    path = explore.write_report(report, Path(x.out) if x.out else None)
    print(f"脱敏报告已写入：{path}\n（只含状态码/键名/行数/字段名，可以直接粘贴给开发者）")


def _cmd_sync(x):
    from pathlib import Path

    from . import sync, ui

    client = jwxt.JwxtClient(debug=bool(x.debug))
    if not client.load_session():
        print("没有已保存的会话。请先运行 jlu-toolkit fetch --user 你的邮箱前缀 登录一次。", file=sys.stderr)
        sys.exit(1)
    root = Path(x.data_dir).expanduser() if x.data_dir else ui.data_dir()
    try:
        summary = sync.sync_all(client, root, x.term)
    except jwxt.LoginError as e:
        print(f"会话失效：{e}；请运行 jlu-toolkit fetch --force-login", file=sys.stderr)
        sys.exit(1)
    except jwxt.NetworkError as e:
        print(f"网络错误：{e}", file=sys.stderr)
        sys.exit(1)
    # 摘要不含个人数值（绩点/学分/成绩只写本地文件）
    print(json.dumps({"data_dir": str(root), **summary}, ensure_ascii=False, indent=1))
    bad = [k for k, v in summary.items() if isinstance(v, dict) and not v.get("ok")]
    sys.exit(2 if bad else 0)


def _cmd_ui(x):
    from pathlib import Path
    import tempfile

    from . import ui

    root = None
    if x.demo:
        root = Path(tempfile.mkdtemp(prefix="jlu-ui-demo-"))
        ui.seed_demo(root)
    elif x.data_dir:
        root = Path(x.data_dir).expanduser()
        root.mkdir(parents=True, exist_ok=True)
    ui.serve(port=x.port, root=root, open_browser=x.open)


if __name__ == "__main__":
    main()
