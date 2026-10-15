"""`jlu-toolkit ui`：本地网页界面（标准库 http.server，仅监听 127.0.0.1）。

数据目录：~/.config/jlu-toolkit/data/
  schedule.csv / grades.csv / exams.csv —— 由「从教务刷新」或 CLI fetch 生成
  schemes.json  —— 命名绩点方案（保研/综测…）：{"方案名": ["学期|课程", ...]}
  settings.json —— {"first_monday": "YYYY-MM-DD"}
所有数据只在本机；网页不引用任何外部资源。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from . import core, exams as ex, jwxt
from .ui_page import PAGE

ALLOWED_HOSTS = ("127.0.0.1", "localhost")


def data_dir() -> Path:
    d = jwxt.config_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.Lock()

    def p(self, name: str) -> Path:
        return self.root / name

    def _json(self, name: str, default):
        try:
            return json.loads(self.p(name).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def _write_json(self, name: str, obj) -> None:
        self.p(name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")

    def courses(self) -> list[core.Course]:
        f = self.p("schedule.csv")
        return core.load_courses(str(f)) if f.exists() else []

    def grades(self) -> list[core.Grade]:
        f = self.p("grades.csv")
        return core.load_grades(str(f)) if f.exists() else []

    def exams(self) -> list[ex.Exam]:
        f = self.p("exams.csv")
        return ex.load_exams(str(f)) if f.exists() else []

    def schemes(self) -> dict:
        return self._json("schemes.json", {})

    def settings(self) -> dict:
        return self._json("settings.json", {})

    def calendar(self) -> dict:
        return self._json("calendar.json", {})

    def periods(self) -> dict:
        return self._json("periods.json", {})

    def first_monday(self) -> Optional[str]:
        """手动覆盖优先，否则用教务校历。"""
        return self.settings().get("first_monday") or self.calendar().get("first_monday") or None

    def save_scheme(self, name: str, keys: list[str]) -> None:
        name = (name or "").strip()[:40]
        if not name:
            raise ValueError("方案名不能为空")
        with self.lock:
            s = self.schemes()
            s[name] = sorted({str(k) for k in keys})
            self._write_json("schemes.json", s)

    def delete_scheme(self, name: str) -> None:
        with self.lock:
            s = self.schemes()
            s.pop(name, None)
            self._write_json("schemes.json", s)

    def save_settings(self, upd: dict) -> None:
        fm = upd.get("first_monday")
        if fm == "":
            with self.lock:
                s = self.settings()
                s.pop("first_monday", None)
                self._write_json("settings.json", s)
            return
        if fm:
            d = dt.date.fromisoformat(fm)
            if d.weekday() != 0:
                raise ValueError("第一周起始日必须是星期一")
        with self.lock:
            s = self.settings()
            s.update({k: v for k, v in upd.items() if k in ("first_monday",)})
            self._write_json("settings.json", s)

    def snapshot(self) -> dict:
        gs = self.grades()
        mtimes = [self.p(n).stat().st_mtime for n in ("schedule.csv", "grades.csv", "exams.csv")
                  if self.p(n).exists()]
        return {
            "courses": [c.__dict__ for c in self.courses()],
            "grades": [dict(g.__dict__, key=f"{g.term}|{g.name}",
                            point=core.score_to_point(g.score)) for g in gs],
            "exams": [e.to_dict() for e in ex.upcoming(self.exams(), dt.datetime(1970, 1, 1))],
            "schemes": self.schemes(),
            "settings": self.settings(),
            "calendar": self.calendar(),
            "periods": self.periods(),
            "first_monday": self.first_monday(),
            "first_monday_source": ("manual" if self.settings().get("first_monday")
                                    else "calendar" if self.calendar().get("first_monday") else None),
            "official_gpa": self._json("official_gpa.json", None),
            "completion": self._json("completion.json", None),
            "plan_courses": self._json("plan_courses.json", None),
            "gpa_all": core.gpa(gs),
            "updated": (dt.datetime.fromtimestamp(max(mtimes)).isoformat(timespec="minutes")
                        if mtimes else None),
        }


def refresh_from_jwxt(store: Store) -> dict:
    """用已保存会话拉取全部数据；不做交互登录。"""
    from .sync import sync_all

    client = jwxt.JwxtClient()
    if not client.load_session():
        raise jwxt.LoginError("没有已保存的会话，请先在终端运行 jlu-toolkit fetch 登录一次")
    return sync_all(client, store.root)


def _client() -> "jwxt.JwxtClient":
    c = jwxt.JwxtClient()
    if not c.load_session():
        raise jwxt.LoginError("没有已保存的会话，请先在终端运行 jlu-toolkit fetch 登录一次")
    return c


def campuses_api(store: Store) -> dict:
    from . import rooms
    cache = store.p("campuses.json")
    if cache.exists():
        return {"campuses": json.loads(cache.read_text(encoding="utf-8"))}
    c = _client()
    lst = rooms.list_campuses(c)
    cache.write_text(json.dumps(lst, ensure_ascii=False), encoding="utf-8")
    c.save_session()
    return {"campuses": lst}


def build_room_query(store: Store, body: dict, term: str = ""):
    """UI / CLI / MCP 共用：body 字段 campus,date,periods,building,kind,seat_min,seat_max,
    exam_min,exam_max,mode(date|week),weeks,weekday,extra{}。"""
    from . import rooms
    mode = str(body.get("mode") or "date")
    start, end = rooms.parse_periods_arg(str(body.get("periods") or "1-2"))
    campus = str(body.get("campus") or "")
    if not campus:
        raise ValueError("请选择校区")
    i = lambda k: int(body.get(k) or 0)  # noqa: E731
    if mode == "week":
        weeks = rooms.expand_weeks(str(body.get("weeks") or ""))
        if not weeks:
            raise ValueError("按周次查询需要周次，如 6 或 6-8")
        weekday = i("weekday")
        if not 1 <= weekday <= 7:
            raise ValueError("按周次查询需要星期 1-7")
        date, week = "", int(weeks.split(",")[0])
    else:
        date = str(body.get("date") or dt.date.today().isoformat())
        dt.date.fromisoformat(date)
        week, weekday = rooms.week_and_weekday(date, store.first_monday())
        weeks = ""
    extra = body.get("extra") or {}
    if not isinstance(extra, dict):
        raise ValueError("extra 应为 {字段: 值}")
    return rooms.RoomQuery(campus, date, start, end, str(body.get("building") or ""),
                           term or store.calendar().get("term", ""), week, weekday,
                           kind=str(body.get("kind") or ""), seat_min=i("seat_min"), seat_max=i("seat_max"),
                           exam_min=i("exam_min"), exam_max=i("exam_max"), mode=mode, weeks=weeks,
                           extra={str(k): str(v) for k, v in extra.items()})


def rooms_api(store: Store, body: dict) -> dict:
    from . import rooms
    q = build_room_query(store, body)
    c = _client()
    found, prof = rooms.query_rooms_any(c, q, store.p("rooms_profile.json"), store.first_monday())
    c.save_session()
    return {"mode": q.mode, "date": q.date, "week": q.week, "weeks": q.weeks, "weekday": q.weekday,
            "periods": [q.start, q.end], "total": prof.get("total"), "rooms": [r.to_dict() for r in found]}


def _cached(store: Store, name: str, fn):
    f = store.p(name)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    c = _client()
    v = fn(c)
    if v:
        f.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
    c.save_session()
    return v


def buildings_api(store: Store, body: dict) -> dict:
    from . import rooms
    campus = str(body.get("campus") or "")
    safe = re.sub(r"\W", "_", campus)
    return {"buildings": _cached(store, f"buildings2_{safe}.json", lambda c: rooms.list_buildings(c, campus))}


def room_types_api(store: Store) -> dict:
    from . import rooms
    return {"types": _cached(store, "room_types.json", lambda c: rooms.list_room_types(c))}


def room_fields_api(store: Store) -> dict:
    """「更多条件」：元数据里额外的检索字段（名称+标题）。"""
    from . import rooms
    return {"fields": _cached(store, "room_fields2.json",
                              lambda c: [{k: s[k] for k in ("name", "caption", "xtype")}
                                         for s in rooms.extra_search_fields(rooms.full_meta(c))])}


def make_handler(store: Store):
    class H(BaseHTTPRequestHandler):
        server_version = "JLUToolkitUI"

        def log_message(self, fmt, *args):  # 安静
            pass

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ALLOWED_HOSTS

        def _send(self, code: int, body: bytes, ctype: str, extra: Optional[dict] = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                raise ValueError("请求过大")
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, b"forbidden", "text/plain")
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                return self._send(200, PAGE.encode(), "text/html; charset=utf-8",
                                  {"Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"})
            if path == "/api/data":
                return self._json(store.snapshot())
            if path == "/api/ics":
                fm = store.first_monday()
                if not fm:
                    return self._json({"error": "缺少开学日期：请先刷新（自动读取校历）或在设置里手动填写"}, 400)
                body = core.to_ics(store.courses(), fm, store.periods() or None).encode()
                return self._send(200, body, "text/calendar; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="jlu-schedule.ics"'})
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if not self._host_ok() or "application/json" not in (self.headers.get("Content-Type") or ""):
                return self._send(403, b"forbidden", "text/plain")
            try:
                body = self._body()
                if self.path == "/api/schemes":
                    store.save_scheme(body.get("name", ""), body.get("include") or [])
                elif self.path == "/api/schemes/delete":
                    store.delete_scheme(body.get("name", ""))
                elif self.path == "/api/settings":
                    store.save_settings(body)
                elif self.path == "/api/rooms":
                    return self._json({"ok": True, **rooms_api(store, body)})
                elif self.path == "/api/rooms/buildings":
                    return self._json({"ok": True, **buildings_api(store, body)})
                elif self.path == "/api/rooms/types":
                    return self._json({"ok": True, **room_types_api(store)})
                elif self.path == "/api/rooms/fields":
                    return self._json({"ok": True, **room_fields_api(store)})
                elif self.path == "/api/rooms/campuses":
                    return self._json({"ok": True, **campuses_api(store)})
                elif self.path == "/api/refresh":
                    return self._json({"ok": True, "result": refresh_from_jwxt(store), **store.snapshot()})
                else:
                    return self._send(404, b"not found", "text/plain")
                return self._json({"ok": True, **store.snapshot()})
            except (ValueError, jwxt.JwxtError) as e:
                return self._json({"ok": False, "error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)

    return H


def seed_demo(root: Path) -> None:
    ex_dir = Path(__file__).resolve().parent / "data" / "demo"
    for n in ("schedule.csv", "grades.csv", "exams.csv"):
        src = ex_dir / n
        if src.exists():
            shutil.copy(src, root / n)
    for n in ("calendar.json", "periods.json", "official_gpa.json", "completion.json", "plan_courses.json"):
        src = ex_dir / n
        if src.exists():
            shutil.copy(src, root / n)
    store = Store(root)
    keys = [f"{g.term}|{g.name}" for g in store.grades()
            if not g.name.startswith(("体育", "军事", "创新"))]
    store.save_scheme("保研", keys)


def serve(port: int = 8765, root: Optional[Path] = None, open_browser: bool = False) -> None:
    store = Store(root or data_dir())
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(store))
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"JLU Toolkit 界面已启动：{url}\n数据目录：{store.root}\n按 Ctrl+C 退出。", flush=True)
    if open_browser:
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
