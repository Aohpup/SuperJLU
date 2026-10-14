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

    mcp.run()

if __name__ == "__main__": main()
