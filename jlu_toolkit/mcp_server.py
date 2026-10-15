"""MCP 接口：让 Claude、Cursor 等 AI 助手直接查询你的课表和绩点。数据只从本地文件读取。
环境变量 JLU_SCHEDULE_CSV / JLU_GRADES_CSV 指定文件路径。"""
import os
from . import core

def main():
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("jlu-toolkit")

    @mcp.tool()
    def courses_on_day(week: int, weekday: int) -> list:
        """查询第 week 周星期 weekday（1-7）的课程。"""
        return [c.__dict__ for c in core.courses_on(core.load_courses(os.environ["JLU_SCHEDULE_CSV"]), week, weekday)]

    @mcp.tool()
    def compute_gpa(term: str = "") -> dict:
        """计算绩点，term 为空表示全部学期。"""
        return core.gpa(core.load_grades(os.environ["JLU_GRADES_CSV"]), term or None)

    @mcp.tool()
    def list_grades(term: str = "") -> list:
        """列出成绩。"""
        return [g.__dict__ for g in core.load_grades(os.environ["JLU_GRADES_CSV"]) if not term or g.term == term]

    @mcp.tool()
    def free_rooms(campus: str, date: str = "", periods: str = "1-2", building: str = "", room_type: str = "",
                   seat_min: int = 0, seat_max: int = 0, exam_seat_min: int = 0, exam_seat_max: int = 0,
                   weeks: str = "", weekday: int = 0, extra: dict | None = None) -> dict:
        """查询空教室（需已用 jlu-toolkit fetch 保存会话）。campus 校区代码（list_campuses），
        building 教学楼代码（list_buildings），room_type 教室类型代码（list_room_types）；
        按日期：date=YYYY-MM-DD；按周次：weeks="6-8" + weekday=1-7；periods 如 "3-4"；
        座位数范围 0 表示不限；extra 为其它检索字段 {字段名: 值}。自动翻页取全。"""
        from . import ui
        return ui.rooms_api(ui.Store(ui.data_dir()), {
            "campus": campus, "date": date, "periods": periods, "building": building, "kind": room_type,
            "seat_min": seat_min, "seat_max": seat_max, "exam_min": exam_seat_min, "exam_max": exam_seat_max,
            "mode": "week" if weeks else "date", "weeks": weeks, "weekday": weekday, "extra": extra or {}})

    @mcp.tool()
    def list_buildings(campus: str) -> list:
        """列出某校区的教学楼代码。"""
        from . import ui
        return ui.buildings_api(ui.Store(ui.data_dir()), {"campus": campus})["buildings"]

    @mcp.tool()
    def list_room_types() -> list:
        """列出教室类型代码。"""
        from . import ui
        return ui.room_types_api(ui.Store(ui.data_dir()))["types"]

    @mcp.tool()
    def plan_courses(status: str = "", term: str = "", nature: str = "") -> dict:
        """培养方案课程明细（本地 plan_courses.json，先运行 jlu-toolkit sync 或 plan --refresh）。
        status：已修/在修/未修/未通过；term：建议修读学期（包含匹配）；nature：课程性质/类别（包含匹配）。"""
        import json as _j
        from . import ui
        from .cli import filter_plan
        f = ui.Store(ui.data_dir()).p("plan_courses.json")
        if not f.exists():
            return {"error": "尚无 plan_courses.json，请先运行 jlu-toolkit sync"}
        p = _j.loads(f.read_text(encoding="utf-8"))
        cs = filter_plan(p.get("courses", []), status, term, nature)
        return {"count": len(cs), "courses": cs}

    @mcp.tool()
    def list_campuses() -> list:
        """列出空教室查询可用的校区代码。"""
        from . import ui
        return ui.campuses_api(ui.Store(ui.data_dir()))["campuses"]

    mcp.run()

if __name__ == "__main__": main()
