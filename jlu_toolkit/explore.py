"""`jlu-toolkit explore`：只读探测吉大金智 EMAP 各应用接口，输出**脱敏**报告。

报告只含：HTTP 状态、最终路径、JSON 顶层键、datas 子块名、行数、字段名。
不含任何字段值（姓名、学号、成绩等一律不写）。

只发起查询类请求（GET 应用入口 / POST *cx*.do 查询）；
**绝不**调用选课、退课、重算、报名、评教提交等写接口。

候选端点来源：JFyuhong/JLU_schedule（wdkb）、Youwenqwq/ysu-sdk（金智 EMAP 通用 API 表）、
XJTU/BIT 公开脚本（studentWdksapApp）。吉大实际部署可能不同，这正是探测的目的。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import jwxt

APP = "https://iedu.jlu.edu.cn/jwapp/sys/{}/*default/index.do"

# 写接口关键字黑名单：探测前硬性检查，防止误加
FORBIDDEN = (
    "xk/", "xsxkapp/sys/xsxkapp/elective", "tk.do", "bysc.do", "xgksrwxs",
    "commit", "calculate", "save", "delete", "submit", "add", "update",
)


@dataclass
class Probe:
    label: str
    app: str  # 应用名（拼 *default/index.do）
    path: Optional[str] = None  # 为空则只 GET 入口
    form: Callable[[str], dict] = field(default=lambda term: {})


def _term_parts(term: str) -> tuple[str, str]:
    # "2025-2026-1" → XN="2025-2026", XQ="1"
    if term and term.count("-") == 2:
        a, b, c = term.split("-")
        return f"{a}-{b}", c
    return "", ""


PROBES: list[Probe] = [
    # 学期 / 校历
    Probe("当前学期(wdkb)", "wdkb", "/jwapp/sys/wdkb/modules/jshkcb/dqxnxq.do"),
    Probe("当前学期(考试应用)", "studentWdksapApp", "/jwapp/sys/studentWdksapApp/modules/wdksap/dqxnxq.do"),
    Probe("学期校历", "wdkb", "/jwapp/sys/wdkb/modules/xskcb/cxxljc.do",
          lambda t: dict(zip(("XN", "XQ"), _term_parts(t)))),
    Probe("当前周次", "wdkb", "/jwapp/sys/wdkb/modules/jshkcb/dqzc.do",
          lambda t: {"XNXQDM": t, "RQ": dt.date.today().isoformat()}),
    Probe("节次时间", "wdkb", "/jwapp/sys/wdkb/modules/jshkcb/jc.do", lambda t: {"XNXQDM": t}),
    Probe("学期列表(jwpubapp)", "wdkb", "/jwapp/sys/jwpubapp/modules/bb/cxjwggbbdqxnxq.do"),
    # 考试
    Probe("考试安排 cxxsksap", "studentWdksapApp",
          "/jwapp/sys/studentWdksapApp/WdksapController/cxxsksap.do",
          lambda t: {"requestParamStr": json.dumps({"XNXQDM": t, "*order": "-KSRQ,-KSSJMS"})}),
    Probe("考试安排 wdksap", "studentWdksapApp",
          "/jwapp/sys/studentWdksapApp/modules/wdksap/wdksap.do",
          lambda t: {"XNXQDM": t, "*order": "-KSRQ,-KSSJMS"}),
    # 成绩扩展
    Probe("学分绩点统计", "cjcx", "/jwapp/sys/cjcx/modules/cjcx/cxzxfaxfjd.do"),
    # 空教室 / 教室
    Probe("教室列表(kcbcx)", "kcbcx", "/jwapp/sys/kcbcx/modules/jskcb/jscx.do",
          lambda t: {"XNXQDM": t, "pageSize": "5", "pageNumber": "1"}),
    Probe("教室列表(kcbcxby)", "kcbcxby", "/jwapp/sys/kcbcxby/modules/jskcb/jscx.do",
          lambda t: {"XNXQDM": t, "pageSize": "5", "pageNumber": "1"}),
    Probe("空教室入口(kxjas)", "kxjas"),
    Probe("空教室入口(kxjscx)", "kxjscx"),
    # 培养方案 / 学业
    Probe("个人培养方案", "xsfacx", "/jwapp/sys/xsfacx/modules/pyfacxepg/grpyfacx.do"),
    Probe("学业完成情况", "xywccx", "/jwapp/sys/xywccx/modules/xywccx/cxxsscfa.do",
          lambda t: {"SCLBDM": "04", "*order": "-CZSJ"}),
    Probe("学业预警", "xyyj", "/jwapp/sys/xyyj/modules/xsxyyjjg/cxxsyjpcjg.do"),
    # 个人信息
    Probe("学生基本信息", "xsjbxxgl", "/jwapp/sys/xsjbxxgl/modules/xsjbxx/cxxsjbxxlb.do"),
    # 选课结果（只看入口，不碰选课接口）
    Probe("选课应用入口(xsxkapp)", "xsxkapp"),
    Probe("选课结果入口(xkjgcx)", "xkjgcx"),
    # 课表变动（只读）
    Probe("调课记录", "wdkb", "/jwapp/sys/wdkb/modules/jshkcb/cxztdkjl.do", lambda t: {"XNXQDM": t}),
    Probe("未排课程", "wdkb", "/jwapp/sys/wdkb/modules/xskcb/xswpkc.do", lambda t: {"XNXQDM": t}),
]


def _assert_read_only(path: str) -> None:
    low = path.lower()
    for bad in FORBIDDEN:
        if bad in low:
            raise ValueError(f"拒绝探测疑似写接口：{path}")


def summarize_json(obj) -> dict:
    """只保留结构信息，不保留任何值。"""
    out: dict = {"type": type(obj).__name__}
    if not isinstance(obj, dict):
        if isinstance(obj, list):
            out["len"] = len(obj)
        return out
    out["keys"] = sorted(obj.keys())
    if "code" in obj and isinstance(obj["code"], (str, int)) and len(str(obj["code"])) <= 6:
        out["code"] = str(obj["code"])
    datas = obj.get("datas")
    if isinstance(datas, dict):
        blocks = {}
        for name, blk in datas.items():
            b: dict = {"type": type(blk).__name__}
            if isinstance(blk, dict):
                rows = blk.get("rows")
                if isinstance(rows, list):
                    b["rows"] = len(rows)
                    fields = set()
                    for r in rows[:20]:
                        if isinstance(r, dict):
                            fields.update(r.keys())
                    b["fields"] = sorted(fields)
                if isinstance(blk.get("totalSize"), int):
                    b["totalSize"] = blk["totalSize"]
                ext = blk.get("extParams")
                if isinstance(ext, dict) and "code" in ext:
                    b["extCode"] = str(ext["code"])[:6]
                b["keys"] = sorted(k for k in blk.keys() if k != "rows")
            elif isinstance(blk, list):
                b["len"] = len(blk)
            blocks[name] = b
        out["datas"] = blocks
    return out


def _path_only(url: str) -> str:
    u = urllib.parse.urlparse(url or "")
    return f"{u.hostname or ''}{u.path}"


def run_explore(client: "jwxt.JwxtClient", term: Optional[str] = None,
                log: Callable[[str], None] = print) -> dict:
    report: dict = {
        "tool": "jlu-toolkit explore",
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "note": "脱敏：仅状态码/路径/键名/行数/字段名，不含任何值",
        "term_detected": None,
        "apps": {},
        "probes": [],
    }
    if not term:
        try:
            term = client.current_semester()
        except Exception as e:  # noqa: BLE001
            log(f"无法取得当前学期：{type(e).__name__}")
    # 学期代码不是个人信息，可报告格式
    report["term_detected"] = term
    term = term or ""

    entered: set[str] = set()
    for pr in PROBES:
        entry = APP.format(pr.app)
        if pr.app not in entered:
            entered.add(pr.app)
            try:
                code, html, final, _ = client._request(
                    entry, headers={"Referer": jwxt.IEDU_PORTAL})
                report["apps"][pr.app] = {
                    "status": code,
                    "final": _path_only(final),
                    "bytes": len(html or ""),
                    "bounced_to_cas": "cas.jlu.edu.cn" in (final or ""),
                }
            except Exception as e:  # noqa: BLE001
                report["apps"][pr.app] = {"error": type(e).__name__}
            log(f"[入口] {pr.app}: {report['apps'][pr.app]}")
        if not pr.path:
            continue
        _assert_read_only(pr.path)
        item: dict = {"label": pr.label, "path": pr.path}
        try:
            code, text, final = client.post_raw(pr.path, pr.form(term), entry)
            item["status"] = code
            item["final"] = _path_only(final)
            try:
                item["json"] = summarize_json(json.loads(text))
            except (json.JSONDecodeError, ValueError):
                item["non_json_bytes"] = len(text or "")
                item["looks_like_login"] = "loginForm" in (text or "")
        except Exception as e:  # noqa: BLE001
            item["error"] = type(e).__name__
        report["probes"].append(item)
        rows = ""
        for name, b in (item.get("json", {}).get("datas") or {}).items():
            if "rows" in b:
                rows += f" {name}={b['rows']}行"
        log(f"[查询] {pr.label}: HTTP {item.get('status', item.get('error'))}{rows}")
    return report


def default_report_path() -> Path:
    dl = Path.home() / "storage" / "downloads"
    if dl.is_dir() and os.access(dl, os.W_OK):
        return dl / "jlu_explore_report.json"
    return Path.cwd() / "jlu_explore_report.json"


def write_report(report: dict, path: Optional[Path] = None) -> Path:
    path = path or default_report_path()
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
