"""WeChat adaptation of SuperJLU; upstream modules remain untouched in vendor.

Each request binds a user context. CAS cookies and cached academic data use
per-user AES-GCM keys derived from a server key; credentials are never saved.
"""
from __future__ import annotations

import base64
import contextvars
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "vendor"))
from jlu_toolkit import core, exams, jwxt, secure_store, grade_calculator as calc

current_user = contextvars.ContextVar("superjlu_user")
data_root = Path(__file__).parent / ".data"
master_key = b""


def config_dir():
    path = data_root / current_user.get()
    path.mkdir(parents=True, exist_ok=True, mode=0o777 if os.name == "nt" else 0o700)
    return path


def user_key(create=False):
    if len(master_key) != 32:
        raise RuntimeError("Missing encryption key")
    return hmac.new(master_key, current_user.get().encode(), hashlib.sha256).digest()


# The original local keyring cannot distinguish server users. Bind all storage
# to the request context before importing modules that use config_dir.
jwxt.config_dir = config_dir
secure_store._config_dir = config_dir
secure_store._get_key = user_key
secure_store.backend_name = lambda: "server-aesgcm"

from jlu_toolkit import rooms, meta, plan, college, oa

CAMPUSES = [{"code": f"{i + 1:02}", "name": n} for i, n in enumerate(
    ["前卫校区", "南岭校区", "新民校区", "朝阳校区", "南湖校区", "和平校区"])]


def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")


def read(name, default=None):
    return secure_store.SecretFile(config_dir(), name).load() or default


def write(name, value):
    secure_store.SecretFile(config_dir(), name).save(value)


def grade_records(grades, imported=False):
    records, occurrences = [], {}
    for g in grades:
        nature = g.nature or "未标注"
        signature = (g.term, g.name, nature)
        occurrences[signature] = occurrences.get(signature, 0) + 1
        key = json.dumps([*signature, occurrences[signature]], ensure_ascii=False, separators=(",", ":"))
        score = calc.parse_score(g.score)
        point = g.jw_point if g.jw_point is not None else (None if imported else core.score_to_point(g.score))
        c = calc.Course(key, g.term, g.name, nature, g.score, score or 0, g.credit,
                       point or 0, score is not None, point is not None)
        records.append({**asdict(g), "key": key, "nature": nature, "numeric_score": score,
                        "point": point, "point_source": "reported" if g.jw_point is not None else
                        "missing" if imported else "estimated", "builtin": c.as_dict()["builtin"]})
    return records


def snapshot():
    return read("academic", {"courses": [], "grades": [], "exams": [], "calendar": {},
                             "periods": {}, "completion": None, "plan_courses": None,
                             "official_gpa": None, "updated": None})


class SchoolSession:
    def __init__(self):
        self.client = None
        self.started = 0
        self.captcha_code = ""
        self.code_sent = False

    def cancel(self):
        self.client = None
        self.started = 0
        self.captcha_code = ""
        self.code_sent = False

    def finish(self):
        try:
            self.client.bootstrap_emap_apps()
        except jwxt.JwxtError:
            pass
        self.client.save_session()
        self.cancel()
        return {"step": "success"}

    def captcha(self):
        self.need()
        if self.client is None:
            raise ValueError("登录流程已过期，请重新输入账号密码")
        self.code_sent = False
        self.captcha_code = ""
        self.client.download_captcha(save=False)
        raw = self.client.last_captcha_bytes or b""
        self.client.last_captcha_bytes = None
        if not raw:
            raise ValueError("图形验证码加载失败，请重试")
        return {"step": "need_second_factor", "captcha": "data:image/jpeg;base64," + base64.b64encode(raw).decode()}

    def need(self):
        if self.client is None or time.monotonic() - self.started > 600:
            self.cancel()
            raise ValueError("登录流程已过期，请重新输入账号密码")

    def start(self, username, password):
        self.cancel()
        if not isinstance(username, str) or not isinstance(password, str) or not username.strip() or not password:
            raise ValueError("请填写邮箱前缀和密码")
        if len(username) > 100 or len(password) > 256:
            raise ValueError("账号或密码过长")
        self.client = jwxt.JwxtClient(timeout=12)
        self.started = time.monotonic()
        try:
            step = self.client.login_password(username.strip(), password)
            if step == jwxt.LoginStep.SUCCESS:
                return self.finish()
            if step == jwxt.LoginStep.NEED_SECOND_FACTOR:
                return self.captcha()
            self.cancel()
            raise ValueError("账号或密码错误；账号应填写邮箱前缀")
        except Exception:
            self.cancel()
            raise

    def send_code(self, code):
        self.need()
        if self.client is None:
            raise ValueError("请重新开始登录")
        if not isinstance(code, str) or not code.strip() or len(code) > 20:
            raise ValueError("请填写图形验证码")
        result = self.client.request_wechat_code(code.strip())
        if result != jwxt.WechatCodeResult.SUCCESS:
            raise ValueError("发送失败，请刷新图形验证码或稍后再试")
        self.captcha_code, self.code_sent = code.strip(), True
        return {"step": "code_sent"}

    def verify(self, code):
        self.need()
        if not self.client or not self.code_sent:
            raise ValueError("请先发送微信验证码")
        if not isinstance(code, str) or not code.strip() or len(code) > 20:
            raise ValueError("请填写微信验证码")
        result = self.client.login_second_factor(self.captcha_code, code.strip())
        if result == jwxt.LoginStep.SUCCESS:
            return self.finish()
        raise ValueError("验证码错误或已过期")


def client():
    c = jwxt.JwxtClient(timeout=12)
    if not c.load_session():
        raise jwxt.SessionExpiredError("请先绑定教务账号")
    return c


def refresh():
    c = client()
    data, failures = snapshot(), []
    # A failed module keeps its previous cache. No CSV containing personal data
    # is written on the server; all academic caches use a single encrypted file.
    term = c.current_semester()
    gs = []

    def step(key, fn):
        try:
            data[key] = fn()
            data.setdefault("module_updated", {})[key] = now()
        except jwxt.LoginError:
            raise
        except Exception:
            failures.append(key)

    step("courses", lambda: [asdict(x) for x in c.fetch_schedule(term)])

    def grades():
        gs.extend(c.fetch_grades())
        return grade_records(gs)

    step("grades", grades)
    step("exams", lambda: [asdict(x) for x in c.fetch_exams(term)])
    step("calendar", lambda: meta.fetch_calendar(c, term))
    step("periods", lambda: meta.fetch_periods(c))
    step("official_gpa", lambda: meta.fetch_official_gpa(c, grades=gs))
    step("completion", lambda: meta.fetch_completion(c, grades=gs))
    step("plan_courses", lambda: plan.fetch_plan(c, grades=gs, courses_now=[core.Course(**x) for x in data["courses"]]))
    data["updated"], data["failures"] = now(), failures
    data["first_monday"] = (data.get("calendar") or {}).get("first_monday")
    c.save_session()
    write("academic", data)
    return data


def room_query(body):
    campus = str(body.get("campus", ""))
    if campus not in {x["code"] for x in CAMPUSES}:
        raise ValueError("请选择校区")
    date = str(body.get("date", ""))
    dt.date.fromisoformat(date)
    start, end = rooms.parse_periods_arg(str(body.get("periods", "1-2")))
    minimum = int(body.get("seat_min") or 0)
    if not 0 <= minimum <= 2000:
        raise ValueError("座位数应在 0–2000 之间")
    data = snapshot()
    week, weekday = rooms.week_and_weekday(date, data.get("first_monday"))
    q = rooms.RoomQuery(campus, date, start, end, str(body.get("building") or ""),
                        (data.get("calendar") or {}).get("term", ""), week, weekday, seat_min=minimum)
    c = client()
    result, _ = rooms.query_rooms_any(c, q, config_dir() / "rooms_profile.json", data.get("first_monday"))
    c.save_session()
    return {"rooms": [r.to_dict() for r in result]}


def notices(body):
    channel = str(body.get("category") or "csw-xytz")
    keyword = str(body.get("keyword") or "").strip()[:100]
    if college.is_channel(channel):
        result = college.fetch(channel)
        items = result.get("items", [])
        hint = result.get("hint", "")
    elif channel in oa.KNOWN_CHANNELS:
        c = client()
        result = oa.fetch_notices(c, channel, limit=30, max_pages=1)
        c.save_session()
        items, hint = result.get("items", []), ""
    else:
        raise ValueError("未知通知来源")
    items = [i for i in items if not keyword or keyword in i.get("title", "") or keyword in i.get("dept", "")]
    return {"items": [{k: i.get(k, "") for k in ("id", "title", "time", "dept", "url")} for i in items], "hint": hint}


def import_grades(body):
    raw = base64.b64decode(body.get("data", ""), validate=True)
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("文件不能超过 5 MB")
    cs = calc.courses_from_bytes(str(body.get("filename", "")), raw)
    grades = [core.Grade(c.name, c.credit, c.grade, c.term, c.gpa if c.gpa_valid else None, c.nature) for c in cs]
    return {"grades": grade_records(grades, imported=True), "notes": cs.import_notes}
