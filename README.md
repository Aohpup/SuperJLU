# JLU Toolkit

吉大课表和成绩的本地小工具：导入文件后可以计算绩点、导出 iCal 日历（手机和电脑日历都能订阅，课前 15 分钟提醒），还提供 **MCP 接口**，让 Claude、Cursor 等 AI 助手直接回答"我明天有什么课""这学期绩点多少"。

> 🔒 **隐私**：课表/成绩默认只在你自己的电脑上读取和计算。可选的「教务拉取」会用你的统一身份认证账号直接向学校服务器发 HTTPS 请求，**凭据只存在本机**（且默认不保存），不经过任何第三方。

## 快速开始
```bash
pip install git+https://github.com/Runa-Asahi/JLU-Toolkit
jlu-toolkit ics examples/schedule.csv --first-monday 2026-09-07 -o 课表.ics
jlu-toolkit gpa examples/grades.csv --term 2025-2026-1
jlu-toolkit today examples/schedule.csv --week 3 --weekday 1
```
CSV 格式参考 `examples/`。周次支持 `1-16`、`1-15单`、`2-16双`、`1,3,5`。

## 从教务系统自动拉取（实验性）

本科教务地址是 `https://iedu.jlu.edu.cn`（金智 jwapp）。登录走统一身份认证：

```
https://cas.jlu.edu.cn/tpass/login
```

密码在浏览器里由 `des.js` 做 3DES 后再提交（`rsa = strEnc(学号+密码+lt, "1", "2", "3")`），本工具用纯 Python 复刻了同一算法，**不依赖 Node / requests**。密码登录路径**不需要图形验证码**（页面虽然加载了 captcha 脚本，但 `login10.js` 的密码提交不带 captcha）。

### 网络说明（实测）

| 地址 | 公网可达？ | 说明 |
|------|-----------|------|
| `cas.jlu.edu.cn` | ✅ 是 | 统一身份认证，校外可打开登录页并完成认证 |
| `iedu.jlu.edu.cn` | ⚠️ 视网络而定 | 教务业务站；部分网络（含部分云主机）TLS 握手超时，需**校园网或学校 VPN** |

先探测：
```bash
jlu-toolkit fetch --probe
```

### 拉取课表和成绩
```bash
# 交互输入密码（不会出现在 shell 历史）
jlu-toolkit fetch --user 你的学号

# 可选：本次登录成功后把账号密码存到
# ~/.config/jlu-toolkit/credentials.json（chmod 600），下次可省略 --user
jlu-toolkit fetch --user 你的学号 --save-credentials

# 只拉课表 / 只拉成绩 / 指定学期
jlu-toolkit fetch --user 你的学号 --what schedule --term 2025-2026-2
jlu-toolkit fetch --user 你的学号 --what grades
```

成功后会在当前目录生成 `schedule.csv`、`grades.csv`，可直接交给 `ics` / `gpa` / MCP 使用。

> MCP 接口**不会**代你登录教务（避免 AI 会话触碰密码）；请先用上面的命令导出 CSV，再把路径配给 MCP。

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
- [x] 教务系统 HTTP 自动导出（CAS 3DES 登录；凭据可选本地保存）
- [ ] 考试倒计时、Windows 托盘挂件
- [ ] 绩点规则可配置（不同学院）

欢迎 PR 和 ⭐！
