# JLU Toolkit

吉大课表和成绩的本地小工具：导入文件后可以计算绩点、导出 iCal 日历（手机和电脑日历都能订阅，课前 15 分钟提醒），还提供 **MCP 接口**，让 Claude、Cursor 等 AI 助手直接回答"我明天有什么课""这学期绩点多少"。

> 🔒 **隐私**：所有数据只在你自己的电脑上读取和计算，不上传任何服务器，也不需要教务账号密码。

## 快速开始
```bash
pip install git+https://github.com/Runa-Asahi/JLU-Toolkit
jlu-toolkit ics examples/schedule.csv --first-monday 2026-09-07 -o 课表.ics
jlu-toolkit gpa examples/grades.csv --term 2025-2026-1
jlu-toolkit today examples/schedule.csv --week 3 --weekday 1
```
CSV 格式参考 `examples/`。周次支持 `1-16`、`1-15单`、`2-16双`、`1,3,5`。

## 接入 AI 助手（MCP）
```bash
pip install "jlu-toolkit[mcp] @ git+https://github.com/Runa-Asahi/JLU-Toolkit"
```
在 AI 客户端的 MCP 配置里加入：
```json
{"mcpServers": {"jlu": {"command": "jlu-toolkit-mcp",
  "env": {"JLU_SCHEDULE_CSV": "/path/课表.csv", "JLU_GRADES_CSV": "/path/成绩.csv"}}}}
```

## 路线图
- [x] 课表/成绩文件导入、绩点计算、iCal 导出、MCP 接口
- [ ] 教务系统自动导出（凭据只存本地）
- [ ] 考试倒计时、Windows 托盘挂件
- [ ] 绩点规则可配置（不同学院）

欢迎 PR 和 ⭐！
