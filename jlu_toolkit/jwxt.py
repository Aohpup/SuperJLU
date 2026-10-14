"""吉大本科教务（iedu.jlu.edu.cn 金智 jwapp）HTTP 客户端。

登录走统一身份认证 cas.jlu.edu.cn/tpass（Neusoft TPASS）：
  GET 登录页 → 取 lt/execution → rsa=strEnc(user+pwd+lt,'1','2','3') → POST → 跟随 ticket 回跳。

课表/成绩接口来自开源项目抓包核对（JFyuhong/JLU_schedule、ShiGuangSchedule）：
  - 当前学期 POST /jwapp/sys/wdkb/modules/jshkcb/dqxnxq.do
  - 课表     POST /jwapp/sys/wdkb/modules/xskcb/cxxszhxqkb.do  body=XNXQDM=...
  - 成绩     POST /jwapp/sys/cjcx/modules/cjcx/xscjcx.do

仅使用标准库（urllib + http.cookiejar）。密码不会被写入日志。
"""
from __future__ import annotations

import csv
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Iterable, Optional

from . import core
from .des_tpass import strEnc

CAS_LOGIN = "https://cas.jlu.edu.cn/tpass/login"
IEDU_HOST = "iedu.jlu.edu.cn"
IEDU_PORTAL = "https://iedu.jlu.edu.cn/jwapp/sys/emaphome/portal/index.do"
IEDU_BASE = "https://iedu.jlu.edu.cn"

EP_CURRENT_SEM = "/jwapp/sys/wdkb/modules/jshkcb/dqxnxq.do"
EP_COURSES = "/jwapp/sys/wdkb/modules/xskcb/cxxszhxqkb.do"
EP_GRADES = "/jwapp/sys/cjcx/modules/cjcx/xscjcx.do"
REF_SCHEDULE = "https://iedu.jlu.edu.cn/jwapp/sys/wdkb/*default/index.do"
REF_GRADES = "https://iedu.jlu.edu.cn/jwapp/sys/cjcx/*default/index.do"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_LT_RE = re.compile(r'id="lt"[^>]*value="([^"]*)"', re.I)
_EXEC_RE = re.compile(r'name="execution"[^>]*value="([^"]*)"', re.I)
_ERR_RE = re.compile(
    r'id="errormsg"[^>]*>([^<]*)', re.I
)


class JwxtError(Exception):
    """教务/认证相关错误。"""


class LoginError(JwxtError):
    """用户名或密码错误，或登录被拒绝。"""


class NetworkError(JwxtError):
    """网络不可达（常见于校外访问不到 iedu）。"""


def default_cred_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / "jlu-toolkit" / "credentials.json"
    return Path.home() / ".config" / "jlu-toolkit" / "credentials.json"


def save_credentials(username: str, password: str, path: Optional[Path] = None) -> Path:
    """可选：把账号密码存到本地文件（chmod 600）。默认不调用。"""
    path = path or default_cred_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"username": username, "password": password}, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def load_credentials(path: Optional[Path] = None) -> Optional[tuple[str, str]]:
    path = path or default_cred_path()
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    u, p = data.get("username"), data.get("password")
    if not u or not p:
        return None
    return str(u), str(p)


def parse_weeks_skzc(skzc: str) -> list[int]:
    """金智周次二进制串：第 i 位为 '1' 表示第 i+1 周。"""
    return [i + 1 for i, ch in enumerate(skzc or "") if ch == "1"]


def clean_teacher(raw: str) -> str:
    """'姓名/工号,姓名2/工号2' → '姓名,姓名2'。"""
    if not raw:
        return ""
    names = []
    for part in raw.split(","):
        name = part.split("/")[0].strip()
        if name:
            names.append(name)
    return ",".join(names)


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


class JwxtClient:
    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=_ssl_context()),
        )
        self._logged_in = False

    def _request(
        self,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[dict] = None,
        method: Optional[str] = None,
    ) -> tuple[int, str, str]:
        hdrs = {"User-Agent": UA, "Accept": "*/*"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                body = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                text = body.decode(charset, errors="replace")
                return resp.getcode() or 200, text, resp.geturl()
        except urllib.error.HTTPError as e:
            body = e.read() if e.fp else b""
            text = body.decode("utf-8", errors="replace")
            return e.code, text, e.geturl() if hasattr(e, "geturl") else url
        except urllib.error.URLError as e:
            raise NetworkError(f"无法连接 {url}: {e.reason}") from e
        except TimeoutError as e:
            raise NetworkError(f"连接超时 {url}") from e

    def fetch_login_page(self, service: str = IEDU_PORTAL) -> tuple[str, str, str]:
        """返回 (html, lt, execution)。"""
        url = f"{CAS_LOGIN}?service={urllib.parse.quote(service, safe='')}"
        code, html, _ = self._request(url)
        if code != 200:
            raise NetworkError(f"CAS 登录页 HTTP {code}")
        lt_m, ex_m = _LT_RE.search(html), _EXEC_RE.search(html)
        if not lt_m:
            raise JwxtError("登录页未找到 lt，页面结构可能已变更")
        return html, lt_m.group(1), (ex_m.group(1) if ex_m else "e1s1")

    @staticmethod
    def encrypt_password_bundle(username: str, password: str, lt: str) -> str:
        """与 login10.js 一致：strEnc(username+password+lt, '1','2','3')。"""
        return strEnc(username + password + lt, "1", "2", "3")

    def login(self, username: str, password: str, service: str = IEDU_PORTAL) -> None:
        """使用学号/密码登录 CAS，并跟随 ticket 建立 iedu 会话。

        成功条件：最终落到 iedu.jlu.edu.cn，且页面不再是登录表单。
        失败时抛出 LoginError（不会回显密码）。
        """
        _, lt, execution = self.fetch_login_page(service)
        rsa = self.encrypt_password_bundle(username, password, lt)
        form = urllib.parse.urlencode(
            {
                "rsa": rsa,
                "ul": str(len(username)),
                "pl": str(len(password)),
                "sl": "0",
                "lt": lt,
                "execution": execution,
                "_eventId": "submit",
            }
        ).encode("utf-8")
        post_url = f"{CAS_LOGIN}?service={urllib.parse.quote(service, safe='')}"
        code, html, final = self._request(
            post_url,
            data=form,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": post_url,
                "Origin": "https://cas.jlu.edu.cn",
            },
        )
        err = _ERR_RE.search(html)
        err_text = (err.group(1).strip() if err else "") or ""
        still_login = 'id="loginForm"' in html or "id='loginForm'" in html
        host = urllib.parse.urlparse(final).hostname or ""
        if host == IEDU_HOST and code in (200, 302) and not still_login:
            self._logged_in = True
            return
        if still_login or err_text or host == "cas.jlu.edu.cn":
            # 失败时 CAS 会重新渲染登录页并轮换 lt；errormsg 常为默认文案
            if err_text and err_text not in ("请输入正确信息",):
                msg = err_text
            else:
                msg = "用户名或密码错误，或需要额外验证（CAS 仍停留在登录页）"
            raise LoginError(msg)
        # 可能 ticket 回跳到了 iedu 但本机连不上 iedu（校外）
        if "iedu.jlu.edu.cn" in (final + html):
            raise NetworkError(
                "CAS 似乎已放行，但无法完成到教务站点的回跳。"
                "请确认当前网络能访问 iedu.jlu.edu.cn（校园网或学校 VPN）。"
            )
        raise LoginError(f"登录未完成（HTTP {code}，最终地址 {host}）")

    def _post_form(self, path: str, fields: dict, referer: str) -> dict:
        url = IEDU_BASE + path
        data = urllib.parse.urlencode(fields).encode("utf-8") if fields else b""
        code, text, _ = self._request(
            url,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": referer,
                "Origin": IEDU_BASE,
            },
        )
        if code != 200:
            raise JwxtError(f"{path} HTTP {code}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            if "loginForm" in text or "/tpass/login" in text:
                raise LoginError("会话已失效，请重新登录") from e
            raise JwxtError(f"{path} 返回非 JSON") from e

    def current_semester(self) -> Optional[str]:
        """返回当前学期代码，如 '2025-2026-2'。"""
        data = self._post_form(EP_CURRENT_SEM, {}, REF_SCHEDULE)
        rows = (
            data.get("datas", {})
            .get("dqxnxq", {})
            .get("rows")
            or []
        )
        if not rows:
            return None
        return rows[0].get("DM")

    def fetch_schedule(self, xnxqdm: Optional[str] = None) -> list[core.Course]:
        """拉取课表，返回 core.Course 列表。"""
        if not xnxqdm:
            xnxqdm = self.current_semester()
        if not xnxqdm:
            raise JwxtError("无法取得当前学期代码")
        data = self._post_form(EP_COURSES, {"XNXQDM": xnxqdm}, REF_SCHEDULE)
        rows = (
            data.get("datas", {})
            .get("cxxszhxqkb", {})
            .get("rows")
            or []
        )
        return [c for c in (row_to_course(r) for r in rows) if c is not None]

    def fetch_grades(self) -> list[core.Grade]:
        """拉取全部有效成绩。"""
        query = json.dumps(
            [
                {
                    "name": "SFYX",
                    "caption": "是否有效",
                    "linkOpt": "AND",
                    "builderList": "cbl_m_List",
                    "builder": "m_value_equal",
                    "value": "1",
                    "value_display": "是",
                },
                {
                    "name": "SHOWMAXCJ",
                    "caption": "显示最高成绩",
                    "linkOpt": "AND",
                    "builderList": "cbl_m_List",
                    "builder": "m_value_equal",
                    "value": "0",
                    "value_display": "否",
                },
            ],
            ensure_ascii=False,
        )
        data = self._post_form(
            EP_GRADES,
            {
                "querySetting": query,
                "*order": "-XNXQDM,-KCH,-KXH",
                "pageSize": "1000",
                "pageNumber": "1",
            },
            REF_GRADES,
        )
        rows = (
            data.get("datas", {})
            .get("xscjcx", {})
            .get("rows")
            or []
        )
        if not rows:
            data = self._post_form(
                EP_GRADES,
                {
                    "querySetting": "[]",
                    "*order": "-XNXQDM,-KCH,-KXH",
                    "pageSize": "1000",
                    "pageNumber": "1",
                },
                REF_GRADES,
            )
            rows = (
                data.get("datas", {})
                .get("xscjcx", {})
                .get("rows")
                or []
            )
        return [g for g in (row_to_grade(r) for r in rows) if g is not None]


def row_to_course(row: dict) -> Optional[core.Course]:
    name = (row.get("KCM") or "").strip()
    if not name:
        return None
    try:
        weekday = int(row.get("SKXQ"))
        start = int(row.get("KSJC"))
        end = int(row.get("JSJC"))
    except (TypeError, ValueError):
        return None
    weeks = parse_weeks_skzc(str(row.get("SKZC") or ""))
    if not weeks or weekday < 1:
        return None
    return core.Course(
        name=name,
        teacher=clean_teacher(str(row.get("SKJS") or "")),
        location=str(row.get("JASMC") or "待定"),
        weekday=weekday,
        start=start,
        end=end,
        weeks=weeks,
    )


def row_to_grade(row: dict) -> Optional[core.Grade]:
    name = (row.get("KCM") or "").strip()
    if not name:
        return None
    try:
        credit = float(row.get("XF"))
    except (TypeError, ValueError):
        return None
    if credit <= 0:
        return None
    score = (
        (row.get("ZCJ") or "").strip()
        or (row.get("XSZCJMC") or "").strip()
        or (row.get("DJCJMC") or "").strip()
    )
    if not score:
        return None
    return core.Grade(
        name=name,
        credit=credit,
        score=str(score),
        term=str(row.get("XNXQDM") or "").strip(),
    )


def export_courses_csv(courses: Iterable[core.Course], path: str) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["课程", "教师", "地点", "星期", "开始节", "结束节", "周次"]
        )
        w.writeheader()
        for c in courses:
            w.writerow(
                {
                    "课程": c.name,
                    "教师": c.teacher,
                    "地点": c.location,
                    "星期": c.weekday,
                    "开始节": c.start,
                    "结束节": c.end,
                    "周次": _weeks_to_csv(c.weeks),
                }
            )


def export_grades_csv(grades: Iterable[core.Grade], path: str) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["课程", "学分", "成绩", "学期"])
        w.writeheader()
        for g in grades:
            w.writerow(
                {"课程": g.name, "学分": g.credit, "成绩": g.score, "学期": g.term}
            )


def _weeks_to_csv(weeks: list[int]) -> str:
    if not weeks:
        return ""
    weeks = sorted(weeks)
    parts = []
    start = prev = weeks[0]
    for w in weeks[1:]:
        if w == prev + 1:
            prev = w
            continue
        parts.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = w
    parts.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(parts)


def probe_reachability(timeout: float = 12.0) -> dict:
    """不带凭据探测 CAS / iedu 是否可达。供诊断用。"""
    out = {}
    client = JwxtClient(timeout=timeout)
    try:
        html, lt, execution = client.fetch_login_page()
        out["cas"] = {
            "ok": True,
            "lt_prefix": lt[:16] + "...",
            "execution": execution,
            "has_login_form": 'id="loginForm"' in html,
            "captcha_script_loaded": "jquery.captcha.js" in html,
            "password_login_uses_captcha": False,  # login10.js 密码登录不校验 captcha
        }
    except Exception as e:  # noqa: BLE001 — 诊断汇总
        out["cas"] = {"ok": False, "error": type(e).__name__ + ": " + str(e)}
    try:
        code, text, final = client._request(IEDU_PORTAL)
        out["iedu"] = {
            "ok": code == 200,
            "http": code,
            "final_host": urllib.parse.urlparse(final).hostname,
            "bytes": len(text),
        }
    except Exception as e:  # noqa: BLE001
        out["iedu"] = {"ok": False, "error": type(e).__name__ + ": " + str(e)}
    return out
