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
        "--what",
        choices=("all", "schedule", "grades"),
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


def _prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except EOFError:
        print("\n已取消。", file=sys.stderr)
        sys.exit(130)


def _interactive_second_factor(client: jwxt.JwxtClient) -> None:
    """图形验证码 + 微信验证码交互（终端 ASCII / 可选 OCR / 多路径保存）。"""
    from . import captcha_util

    print(
        "需要二次认证：图形验证码会画在终端里；同时保存到 Downloads/Pictures/DCIM。"
        "微信验证码请到「智慧吉大」查看。",
        file=sys.stderr,
    )
    if not captcha_util.has_pillow():
        print(
            "提示：未检测到 Pillow，终端无法绘制验证码。"
            "Termux 请执行：pkg install python-pillow",
            file=sys.stderr,
        )
    auto_ocr = captcha_util.has_ddddocr()
    if auto_ocr:
        print("已启用 ddddocr 自动识别（可直接回车采纳，或改输入）。", file=sys.stderr)

    while True:
        path = client.download_captcha()
        raw = client.last_captcha_bytes or path.read_bytes()
        paths = client.last_captcha_paths or [path]
        print(f"图形验证码已保存（含放大版 *_large.jpg）：", file=sys.stderr)
        for p in paths:
            try:
                print(f"  - {p}  ({p.stat().st_size} bytes)", file=sys.stderr)
            except OSError:
                print(f"  - {p}", file=sys.stderr)
        print(captcha_util.render_ascii(raw), file=sys.stderr)

        suggestion = captcha_util.ocr_digits(raw) if auto_ocr else None
        if suggestion:
            print(f"OCR 识别结果：{suggestion}", file=sys.stderr)
            captcha = _prompt(
                f"请输入图形验证码 [直接回车用 {suggestion}，输入 refresh 刷新]："
            )
            if not captcha:
                captcha = suggestion
        else:
            captcha = _prompt("请输入图形验证码（直接回车 / refresh 刷新图片）：")

        if not captcha or captcha.lower() in ("refresh", "r", "刷新"):
            continue

        result = client.request_wechat_code(captcha)
        if result == jwxt.WechatCodeResult.CAPTCHA_ERROR:
            print("图形验证码错误，已刷新，请重试。", file=sys.stderr)
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


def _ensure_login(x) -> jwxt.JwxtClient:
    debug = bool(getattr(x, "debug", False))
    client = jwxt.JwxtClient(debug=debug)

    if not x.force_login and client.load_session():
        print("发现本地会话，正在检测是否有效…", file=sys.stderr)
        if client.session_alive():
            print("会话有效，跳过登录。", file=sys.stderr)
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
            _interactive_second_factor(client)
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

    sess = client.save_session()
    print(f"已保存会话到 {sess}（权限 600），下次可免登录。", file=sys.stderr)
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
    except jwxt.LoginError as e:
        print(f"{e}；可加 --force-login 重登。", file=sys.stderr)
        sys.exit(1)
    except jwxt.NetworkError as e:
        print(f"网络错误：{e}", file=sys.stderr)
        sys.exit(1)
    except jwxt.JwxtError as e:
        print(f"教务错误：{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
