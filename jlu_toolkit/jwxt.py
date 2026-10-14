"""吉大本科教务（iedu.jlu.edu.cn 金智 jwapp）HTTP 客户端。

登录走统一身份认证 cas.jlu.edu.cn/tpass（Neusoft TPASS）：
  1) GET 登录页 → lt/execution → rsa=strEnc(邮箱前缀+密码+lt,'1','2','3') → POST
  2) 若返回「二次认证」页：下载图形验证码 /tpass/code → 调 /tpass/recheckcode 发微信验证码
     → 再 POST lt/execution/code/WxCode 完成登录 → 跟随 ticket 回跳教务

课表/成绩接口（开源项目抓包核对）：
  - 当前学期 POST /jwapp/sys/wdkb/modules/jshkcb/dqxnxq.do
  - 课表     POST /jwapp/sys/wdkb/modules/xskcb/cxxszhxqkb.do
  - 成绩     POST /jwapp/sys/cjcx/modules/cjcx/xscjcx.do

仅标准库。密码与验证码不会写入日志。
"""
from __future__ import annotations

import csv
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import Enum
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from typing import Iterable, Optional

from . import core
from .des_tpass import strEnc

CAS_BASE = "https://cas.jlu.edu.cn/tpass"
CAS_LOGIN = f"{CAS_BASE}/login"
CAS_CODE = f"{CAS_BASE}/code"
CAS_RECHECKCODE = f"{CAS_BASE}/recheckcode"
IEDU_HOST = "iedu.jlu.edu.cn"
IEDU_PORTAL = "https://iedu.jlu.edu.cn/jwapp/sys/emaphome/portal/index.do"
IEDU_BASE = "https://iedu.jlu.edu.cn"

EP_CURRENT_SEM = "/jwapp/sys/wdkb/modules/jshkcb/dqxnxq.do"
EP_COURSES = "/jwapp/sys/wdkb/modules/xskcb/cxxszhxqkb.do"
EP_GRADES = "/jwapp/sys/cjcx/modules/cjcx/xscjcx.do"
REF_SCHEDULE = "https://iedu.jlu.edu.cn/jwapp/sys/wdkb/*default/index.do"
REF_GRADES = "https://iedu.jlu.edu.cn/jwapp/sys/cjcx/*default/index.do"

UA = (
    "Mozilla/5.0 (Linux; Android 14; Termux) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)

_LT_RE = re.compile(r'(?:id|name)="lt"[^>]*value="([^"]*)"', re.I)
_LT_RE2 = re.compile(r'value="([^"]*)"[^>]*(?:id|name)="lt"', re.I)
_EXEC_RE = re.compile(r'name="execution"[^>]*value="([^"]*)"', re.I)
_EVENT_RE = re.compile(r'name="_eventId"[^>]*value="([^"]*)"', re.I)
_ERR_RE = re.compile(r'id="errormsg"[^>]*>([^<]*)', re.I)
_WXCODE_RE = re.compile(r'name=["\']WxCode["\']', re.I)


class JwxtError(Exception):
    """教务/认证相关错误。"""


class LoginError(JwxtError):
    """用户名或密码错误，或登录被拒绝。"""


class NetworkError(JwxtError):
    """网络不可达（常见于校外访问不到 iedu）。"""


class SecondFactorError(JwxtError):
    """二次认证（图形/微信验证码）失败。"""


class LoginStep(Enum):
    SUCCESS = "success"
    NEED_SECOND_FACTOR = "need_second_factor"
    WRONG_PASSWORD = "wrong_password"
    FAILED = "failed"


class WechatCodeResult(Enum):
    SUCCESS = "success"
    CAPTCHA_ERROR = "img_code_error"
    TOO_FREQUENT = "get_times_more"
    SESSION_EXPIRED = "get_session_error"
    FAILED = "failed"


@dataclass
class PendingSecondFactor:
    lt: str
    execution: str
    event_id: str = "submit"
    service: str = IEDU_PORTAL


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "jlu-toolkit"


def default_cred_path() -> Path:
    return config_dir() / "credentials.json"


def default_session_path() -> Path:
    return config_dir() / "session.json"


def captcha_save_path(filename: str = "jlu_cas_captcha.jpg") -> Path:
    """Termux 优先写到 ~/storage/downloads，否则当前目录。"""
    termux = Path.home() / "storage" / "downloads"
    if termux.is_dir():
        return termux / filename
    return Path.cwd() / filename


def _chmod600(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def save_credentials(username: str, password: str, path: Optional[Path] = None) -> Path:
    path = path or default_cred_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"username": username, "password": password}, ensure_ascii=False),
        encoding="utf-8",
    )
    _chmod600(path)
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
    return [i + 1 for i, ch in enumerate(skzc or "") if ch == "1"]


def clean_teacher(raw: str) -> str:
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


def _extract_lt(html: str) -> Optional[str]:
    m = _LT_RE.search(html) or _LT_RE2.search(html)
    return m.group(1) if m else None


def classify_login_html(html: str) -> LoginStep:
    """根据密码提交后的 HTML 判断下一步（对照 wzyyyyyyy/iLearn 的分类器）。"""
    wrong_markers = (
        "用户名或密码错误",
        "账号或密码错误",
        "用户名或密码有误",
        "账号或密码有误",
        "密码错误",
        "密码有误",
    )
    if any(m in html for m in wrong_markers):
        return LoginStep.WRONG_PASSWORD
    if (
        _WXCODE_RE.search(html)
        or "recheckcode" in html.lower()
        or "二次认证" in html
        or 'name="WxCode"' in html
        or "获取微信验证码" in html
    ):
        return LoginStep.NEED_SECOND_FACTOR
    if 'id="loginForm"' in html or "id='loginForm'" in html:
        return LoginStep.WRONG_PASSWORD
    return LoginStep.SUCCESS


def jar_to_list(jar: CookieJar) -> list[dict]:
    out = []
    for c in jar:
        out.append(
            {
                "name": c.name,
                "value": c.value,
                "domain": c.domain,
                "path": c.path or "/",
                "secure": bool(c.secure),
                "expires": c.expires,
                "rest": dict(c._rest) if getattr(c, "_rest", None) else {},
            }
        )
    return out


def jar_from_list(items: list[dict]) -> CookieJar:
    jar = CookieJar()
    for d in items:
        c = Cookie(
            version=0,
            name=d["name"],
            value=d["value"],
            port=None,
            port_specified=False,
            domain=d.get("domain") or "",
            domain_specified=bool(d.get("domain")),
            domain_initial_dot=str(d.get("domain") or "").startswith("."),
            path=d.get("path") or "/",
            path_specified=True,
            secure=bool(d.get("secure")),
            expires=d.get("expires"),
            discard=d.get("expires") is None,
            comment=None,
            comment_url=None,
            rest=d.get("rest") or {},
            rfc2109=False,
        )
        jar.set_cookie(c)
    return jar


class JwxtClient:
    def __init__(self, timeout: float = 25.0):
        self.timeout = timeout
        self.jar = CookieJar()
        self._rebuild_opener()
        self._logged_in = False
        self.pending: Optional[PendingSecondFactor] = None

    def _rebuild_opener(self) -> None:
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=_ssl_context()),
        )

    def _request(
        self,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[dict] = None,
        method: Optional[str] = None,
        allow_redirects: bool = True,
    ) -> tuple[int, str, str, bytes]:
        hdrs = {"User-Agent": UA, "Accept": "*/*"}
        if headers:
            hdrs.update(headers)
        if allow_redirects:
            opener = self.opener
        else:
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(self.jar),
                urllib.request.HTTPSHandler(context=_ssl_context()),
                _NoRedirect(),
            )
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="replace")
                return resp.getcode() or 200, text, resp.geturl(), raw
        except urllib.error.HTTPError as e:
            raw = e.read() if e.fp else b""
            text = raw.decode("utf-8", errors="replace")
            # 302 with no-redirect handler lands here
            loc = e.headers.get("Location", "")
            final = urllib.parse.urljoin(url, loc) if loc else url
            return e.code, text, final, raw
        except urllib.error.URLError as e:
            raise NetworkError(f"无法连接 {url}: {e.reason}") from e
        except TimeoutError as e:
            raise NetworkError(f"连接超时 {url}") from e

    def save_session(self, path: Optional[Path] = None) -> Path:
        path = path or default_session_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"cookies": jar_to_list(self.jar)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _chmod600(path)
        return path

    def load_session(self, path: Optional[Path] = None) -> bool:
        path = path or default_session_path()
        if not path.is_file():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        self.jar = jar_from_list(data.get("cookies") or [])
        self._rebuild_opener()
        return True

    def clear_session_file(self, path: Optional[Path] = None) -> None:
        path = path or default_session_path()
        if path.is_file():
            path.unlink()

    def session_alive(self) -> bool:
        """探测已保存会话是否还能访问教务（不落在 CAS 登录页）。"""
        try:
            code, text, final, _ = self._request(REF_SCHEDULE)
        except NetworkError:
            return False
        host = urllib.parse.urlparse(final).hostname or ""
        if host != IEDU_HOST or code not in (200, 302):
            return False
        low = text[:8192].lower()
        if 'id="loginform"' in low or ("/tpass/login" in low and "password" in low):
            return False
        if "二次认证" in text:
            return False
        self._logged_in = True
        return True

    def fetch_login_page(self, service: str = IEDU_PORTAL) -> tuple[str, str, str]:
        url = f"{CAS_LOGIN}?service={urllib.parse.quote(service, safe='')}"
        code, html, _, _ = self._request(url)
        if code != 200:
            raise NetworkError(f"CAS 登录页 HTTP {code}")
        lt = _extract_lt(html)
        if not lt:
            raise JwxtError("登录页未找到 lt，页面结构可能已变更")
        ex_m = _EXEC_RE.search(html)
        return html, lt, (ex_m.group(1) if ex_m else "e1s1")

    @staticmethod
    def encrypt_password_bundle(username: str, password: str, lt: str) -> str:
        return strEnc(username + password + lt, "1", "2", "3")

    def login_password(
        self, username: str, password: str, service: str = IEDU_PORTAL
    ) -> LoginStep:
        """第一步：提交邮箱前缀+密码。可能直接成功，或需要二次认证。"""
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
        code, html, final, _ = self._request(
            post_url,
            data=form,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": post_url,
                "Origin": "https://cas.jlu.edu.cn",
            },
        )
        step = classify_login_html(html)
        host = urllib.parse.urlparse(final).hostname or ""

        if step == LoginStep.NEED_SECOND_FACTOR:
            new_lt = _extract_lt(html) or lt
            ex_m = _EXEC_RE.search(html)
            ev_m = _EVENT_RE.search(html)
            self.pending = PendingSecondFactor(
                lt=new_lt,
                execution=ex_m.group(1) if ex_m else "e1s2",
                event_id=ev_m.group(1) if ev_m else "submit",
                service=service,
            )
            return LoginStep.NEED_SECOND_FACTOR

        if step == LoginStep.WRONG_PASSWORD:
            return LoginStep.WRONG_PASSWORD

        if host == IEDU_HOST and code in (200, 302):
            self._logged_in = True
            self.pending = None
            return LoginStep.SUCCESS

        if host == IEDU_HOST or ("ticket=" in final and "iedu.jlu.edu.cn" in final):
            # ticket 已发但业务站连不上
            raise NetworkError(
                "CAS 已放行，但无法完成到教务站点的回跳。"
                "请确认当前网络能访问 iedu.jlu.edu.cn（校园网或学校 VPN）。"
            )
        if host == "cas.jlu.edu.cn":
            return LoginStep.WRONG_PASSWORD
        return LoginStep.FAILED

    def download_captcha(self, path: Optional[Path] = None) -> Path:
        """GET /tpass/code → JPEG。需与当前会话 cookie 一致。"""
        path = path or captcha_save_path()
        url = f"{CAS_CODE}?{int(time.time() * 1000)}"
        code, _, _, raw = self._request(
            url,
            headers={"Referer": CAS_LOGIN, "Accept": "image/*,*/*"},
        )
        if code != 200 or len(raw) < 50:
            raise SecondFactorError(f"获取图形验证码失败 HTTP {code}")
        if raw[:2] != b"\xff\xd8":
            raise SecondFactorError("图形验证码不是 JPEG，页面可能已变更")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def request_wechat_code(self, image_captcha: str) -> WechatCodeResult:
        """GET /tpass/recheckcode?code=&t= ，结果在 cookie recheck_mobile_error_info。"""
        if not image_captcha.strip():
            raise SecondFactorError("图形验证码不能为空")
        now = int(time.time() * 1000)
        # 与浏览器一致：写入倒计时 cookie
        self.jar.set_cookie(
            Cookie(
                version=0,
                name="recheck_djsendtime",
                value=str(now + 120000),
                port=None,
                port_specified=False,
                domain="cas.jlu.edu.cn",
                domain_specified=True,
                domain_initial_dot=False,
                path="/",
                path_specified=True,
                secure=False,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
        )
        url = (
            f"{CAS_RECHECKCODE}?code={urllib.parse.quote(image_captcha.strip())}"
            f"&t={now}"
        )
        referer = f"{CAS_LOGIN}?service={urllib.parse.quote(IEDU_PORTAL, safe='')}"
        code, _, _, _ = self._request(
            url,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": referer,
                "Accept": "*/*",
            },
        )
        if code != 200:
            return WechatCodeResult.FAILED
        info = None
        for c in self.jar:
            if c.name == "recheck_mobile_error_info":
                info = c.value
                break
        mapping = {
            "success": WechatCodeResult.SUCCESS,
            "img_code_error": WechatCodeResult.CAPTCHA_ERROR,
            "get_times_more": WechatCodeResult.TOO_FREQUENT,
            "get_session_error": WechatCodeResult.SESSION_EXPIRED,
        }
        return mapping.get(info or "", WechatCodeResult.FAILED)

    def login_second_factor(self, image_captcha: str, wechat_code: str) -> LoginStep:
        """第二步：提交图形验证码 + 微信验证码。"""
        if not self.pending:
            raise SecondFactorError("没有待完成的二次认证（请先完成密码登录）")
        p = self.pending
        form = urllib.parse.urlencode(
            {
                "rsa": "",
                "ul": "",
                "pl": "",
                "sl": "",
                "lt": p.lt,
                "execution": p.execution,
                "_eventId": p.event_id,
                "code": image_captcha.strip(),
                "WxCode": wechat_code.strip(),
                "not_exit_number": "",
                "service_id": "",
            }
        ).encode("utf-8")
        post_url = f"{CAS_LOGIN}?service={urllib.parse.quote(p.service, safe='')}"
        code, html, final, _ = self._request(
            post_url,
            data=form,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": post_url,
                "Origin": "https://cas.jlu.edu.cn",
            },
        )
        host = urllib.parse.urlparse(final).hostname or ""
        if "验证码错误" in html:
            return LoginStep.FAILED
        if classify_login_html(html) == LoginStep.NEED_SECOND_FACTOR:
            new_lt = _extract_lt(html)
            if new_lt:
                self.pending.lt = new_lt
            ex_m = _EXEC_RE.search(html)
            if ex_m:
                self.pending.execution = ex_m.group(1)
            return LoginStep.FAILED
        landed_iedu = host == IEDU_HOST or "iedu.jlu.edu.cn" in final
        has_ticket = "ticket=" in final
        if landed_iedu:
            self._logged_in = True
            self.pending = None
            return LoginStep.SUCCESS
        if has_ticket:
            raise NetworkError(
                "二次认证似乎已通过，但无法完成到教务的回跳，请使用校园网或 VPN。"
            )
        if code in (200, 302) and host not in ("", "cas.jlu.edu.cn"):
            # 其他业务站 service 回跳也算 CAS 成功
            self._logged_in = True
            self.pending = None
            return LoginStep.SUCCESS
        return LoginStep.FAILED

    def login(self, username: str, password: str, service: str = IEDU_PORTAL) -> None:
        """兼容旧接口：仅密码、无二次认证时可用；需要 2FA 时抛 LoginError。"""
        step = self.login_password(username, password, service)
        if step == LoginStep.SUCCESS:
            return
        if step == LoginStep.NEED_SECOND_FACTOR:
            raise LoginError(
                "需要二次认证（图形验证码 + 微信验证码）。请使用 CLI 交互流程。"
            )
        if step == LoginStep.WRONG_PASSWORD:
            raise LoginError("用户名或密码错误，或需要额外验证（CAS 仍停留在登录页）")
        raise LoginError("登录未完成")

    def _post_form(self, path: str, fields: dict, referer: str) -> dict:
        url = IEDU_BASE + path
        data = urllib.parse.urlencode(fields).encode("utf-8") if fields else b""
        code, text, _, _ = self._request(
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
            if "loginForm" in text or "/tpass/login" in text or "二次认证" in text:
                raise LoginError("会话已失效，请重新登录") from e
            raise JwxtError(f"{path} 返回非 JSON") from e

    def current_semester(self) -> Optional[str]:
        data = self._post_form(EP_CURRENT_SEM, {}, REF_SCHEDULE)
        rows = (data.get("datas", {}).get("dqxnxq", {}) or {}).get("rows") or []
        if not rows:
            return None
        return rows[0].get("DM")

    def fetch_schedule(self, xnxqdm: Optional[str] = None) -> list[core.Course]:
        if not xnxqdm:
            xnxqdm = self.current_semester()
        if not xnxqdm:
            raise JwxtError("无法取得当前学期代码")
        data = self._post_form(EP_COURSES, {"XNXQDM": xnxqdm}, REF_SCHEDULE)
        rows = (data.get("datas", {}).get("cxxszhxqkb", {}) or {}).get("rows") or []
        return [c for c in (row_to_course(r) for r in rows) if c is not None]

    def fetch_grades(self) -> list[core.Grade]:
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
        rows = (data.get("datas", {}).get("xscjcx", {}) or {}).get("rows") or []
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
            rows = (data.get("datas", {}).get("xscjcx", {}) or {}).get("rows") or []
        return [g for g in (row_to_grade(r) for r in rows) if g is not None]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


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
    out = {}
    client = JwxtClient(timeout=timeout)
    try:
        html, lt, execution = client.fetch_login_page()
        out["cas"] = {
            "ok": True,
            "lt_prefix": lt[:16] + "...",
            "execution": execution,
            "has_login_form": 'id="loginForm"' in html,
        }
    except Exception as e:  # noqa: BLE001
        out["cas"] = {"ok": False, "error": type(e).__name__ + ": " + str(e)}
    try:
        path = captcha_save_path("jlu_cas_captcha_probe.jpg")
        saved = client.download_captcha(path)
        out["captcha"] = {
            "ok": True,
            "path": str(saved),
            "bytes": saved.stat().st_size,
            "url": CAS_CODE,
        }
    except Exception as e:  # noqa: BLE001
        out["captcha"] = {"ok": False, "error": type(e).__name__ + ": " + str(e)}
    try:
        # 无密码会话时应返回 get_session_error
        result = client.request_wechat_code("0000")
        out["recheckcode"] = {
            "ok": True,
            "url": CAS_RECHECKCODE,
            "without_session": result.value,
            "note": "无密码会话时预期 get_session_error",
        }
    except Exception as e:  # noqa: BLE001
        out["recheckcode"] = {"ok": False, "error": type(e).__name__ + ": " + str(e)}
    try:
        code, text, final, _ = client._request(IEDU_PORTAL)
        out["iedu"] = {
            "ok": code == 200,
            "http": code,
            "final_host": urllib.parse.urlparse(final).hostname,
            "bytes": len(text),
        }
    except Exception as e:  # noqa: BLE001
        out["iedu"] = {"ok": False, "error": type(e).__name__ + ": " + str(e)}
    return out
