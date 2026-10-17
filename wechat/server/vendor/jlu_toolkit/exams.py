"""考试安排：解析金智 wdksap 行、CSV 读写、倒计时。纯标准库。"""
from __future__ import annotations

import csv
import datetime as dt
import re
from dataclasses import dataclass, asdict
from typing import Iterable, Optional

FIELDS = ["课程", "开始", "结束", "地点", "座位号", "考试名称", "学期"]


@dataclass
class Exam:
    name: str
    start: str  # ISO "YYYY-MM-DDTHH:MM"，未知时间则为 ""
    end: str
    location: str
    seat: str = ""
    kind: str = ""
    term: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_KSSJ = re.compile(
    r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?\s*(\d{1,2}):(\d{2})\s*[-~至到]\s*(\d{1,2}):(\d{2})"
)


def parse_kssjms(text: str) -> tuple[str, str]:
    """'2023-04-27 10:10-12:10(星期四)' → ('2023-04-27T10:10','2023-04-27T12:10')。"""
    m = _KSSJ.search(text or "")
    if not m:
        return "", ""
    y, mo, d, h1, m1, h2, m2 = (int(x) for x in m.groups())
    day = f"{y:04d}-{mo:02d}-{d:02d}"
    return f"{day}T{h1:02d}:{m1:02d}", f"{day}T{h2:02d}:{m2:02d}"


def row_to_exam(row: dict, to_str) -> Optional[Exam]:
    name = to_str(row.get("KCM"))
    if not name:
        return None
    start, end = parse_kssjms(to_str(row.get("KSSJMS")))
    if not start:
        ksrq = to_str(row.get("KSRQ"))[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ksrq):
            start = f"{ksrq}T00:00"
    return Exam(
        name=name,
        start=start,
        end=end,
        location=to_str(row.get("JASMC")) or "待定",
        seat=to_str(row.get("ZWH")),
        kind=to_str(row.get("KSMC")),
        term=to_str(row.get("XNXQDM")),
    )


def export_exams_csv(exams: Iterable[Exam], path: str) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for e in exams:
            w.writerow([e.name, e.start, e.end, e.location, e.seat, e.kind, e.term])


def load_exams(path: str) -> list[Exam]:
    with open(path, encoding="utf-8-sig") as f:
        return [
            Exam(r["课程"], r.get("开始", ""), r.get("结束", ""), r.get("地点", ""),
                 r.get("座位号", ""), r.get("考试名称", ""), r.get("学期", ""))
            for r in csv.DictReader(f)
        ]


def countdown(exam: Exam, now: Optional[dt.datetime] = None) -> Optional[dt.timedelta]:
    if not exam.start:
        return None
    now = now or dt.datetime.now()
    return dt.datetime.fromisoformat(exam.start) - now


def format_countdown(delta: Optional[dt.timedelta]) -> str:
    if delta is None:
        return "时间待定"
    secs = int(delta.total_seconds())
    if secs < 0:
        return "已结束"
    d, rem = divmod(secs, 86400)
    h = rem // 3600
    if d:
        return f"还有 {d} 天 {h} 小时"
    return f"还有 {h} 小时 {rem % 3600 // 60} 分"


def upcoming(exams: Iterable[Exam], now: Optional[dt.datetime] = None) -> list[Exam]:
    now = now or dt.datetime.now()
    future = [e for e in exams if e.start and dt.datetime.fromisoformat(e.end or e.start) >= now]
    undated = [e for e in exams if not e.start]
    return sorted(future, key=lambda e: e.start) + undated

