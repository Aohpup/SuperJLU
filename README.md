# JLU Toolkit

吉大课表和成绩的本地小工具：导入文件后可以计算绩点、导出 iCal 日历（手机和电脑日历都能订阅，课前 15 分钟提醒），还提供 **MCP 接口**，让 Claude、Cursor 等 AI 助手直接回答"我明天有什么课""这学期绩点多少"。

> 🔒 **隐私**：课表/成绩默认只在你自己的电脑上读取和计算。可选的「教务拉取」会用你的统一身份认证账号直接向学校服务器发 HTTPS 请求，**凭据与会话只存在本机**（chmod 600），不经过任何第三方。

## 快速开始
```bash
pip install git+https://github.com/Runa-Asahi/JLU-Toolkit
jlu-toolkit ics examples/schedule.csv --first-monday 2026-09-07 -o 课表.ics
jlu-toolkit gpa examples/grades.csv --term 2025-2026-1   # 简单学分加权，见下方「绩点说明」
jlu-toolkit today examples/schedule.csv --week 3 --weekday 1
```
CSV 格式参考 `examples/`。周次支持 `1-16`、`1-15单`、`2-16双`、`1,3,5`。

## 从教务系统自动拉取（含二次认证）

本科教务：`https://iedu.jlu.edu.cn`（金智 jwapp）  
统一身份认证：`https://cas.jlu.edu.cn/tpass/login`

**账号是邮箱前缀，不是学号。**

登录流程：
1. 提交邮箱前缀 + 密码（密码经页面同款 3DES：`rsa = strEnc(账号+密码+lt,"1","2","3")`）
2. 若出现「二次认证」：下载图形验证码 → 输入后调用发送接口 → 在「智慧吉大」收取微信验证码 → 提交完成登录
3. 会话 cookie 会保存到 `~/.config/jlu-toolkit/session.json`（权限 600），下次未过期可免登录

### 网络说明

| 地址 | 说明 |
|------|------|
| `cas.jlu.edu.cn` | 公网可访问（登录、验证码、发微信码） |
| `iedu.jlu.edu.cn` | 教务业务站；部分网络需**校园网或学校 VPN** |

```bash
jlu-toolkit fetch --probe
```

### 拉取课表和成绩
```bash
# 交互：密码 →（如需）图形验证码路径提示 → 微信验证码
jlu-toolkit fetch --user 你的邮箱前缀

# 可选：保存账号密码；会话会在登录成功后自动保存
jlu-toolkit fetch --user 你的邮箱前缀 --save-credentials

# 强制重登（忽略已保存会话）
jlu-toolkit fetch --user 你的邮箱前缀 --force-login
# 登录成功后会自动打开课表/成绩应用入口（避免接口 403）
# 若仍 403：加 --debug 查看是否有 CASTGC / _WEU

# 只拉课表 / 成绩 / 考试 / 指定学期
jlu-toolkit fetch --user 你的邮箱前缀 --what schedule --term 2025-2026-2
jlu-toolkit fetch --what exams          # 考试安排 → exams.csv，并打印倒计时
jlu-toolkit exams exams.csv             # 离线查看考试倒计时
```

图形验证码图片：
- **Termux**：优先保存到 `~/storage/downloads/jlu_cas_captcha.jpg`（请先 `termux-setup-storage`）
- 其他环境：当前目录下的 `jlu_cas_captcha.jpg`

> MCP **不会**代你登录教务；请先用上面的命令导出 CSV，再把路径配给 MCP。

### Termux（Android）示例
```bash
pkg install python git python-pillow
termux-setup-storage
pip install -U --force-reinstall "git+https://github.com/Runa-Asahi/JLU-Toolkit.git@feat/jwxt-http-fetch"
jlu-toolkit fetch --probe
jlu-toolkit fetch --user 你的邮箱前缀 --force-login
# 登录成功后会自动打开课表/成绩应用入口（避免接口 403）
# 若仍 403：加 --debug 查看是否有 CASTGC / _WEU
jlu-toolkit explore            # 只读探测，报告在 ~/storage/downloads/
jlu-toolkit ui                 # 手机浏览器打开 http://127.0.0.1:8765/
# 图形验证码默认自动识别（纯 Pillow，无需 ddddocr）
# 识别错了会自动刷新最多 5 次，再不行才让你手输
# 需要看图时加：--show-captcha
```

## 网页界面（`jlu-toolkit ui`）

```bash
jlu-toolkit ui            # 浏览器打开 http://127.0.0.1:8765/
jlu-toolkit ui --demo     # 用示例数据先看看效果
```

- **课表**：周视图，左右滑动或按钮切换周次，今日高亮；首页顶部显示下一场考试倒计时
- **成绩**：顶部显示教务官方「学分绩点统计」（只读）；下方每门课一个勾选框，实时计算所选课程的绩点；可把勾选结果另存为命名方案（如「保研」「综测」）
- **考试**：倒计时列表（3 天内标红）
- **学业**：培养方案总学分进度、各类课程（课组）要求/已获/还差学分，未完成的排在前面
- **设置**：开学日期自动取自教务校历（可手动覆盖）、导出 iCal（使用教务节次时间）
- 右上角「刷新」（等同 `jlu-toolkit sync`）使用终端登录时保存的会话从教务重新拉取，不会弹出登录；会话失效时在终端执行 `jlu-toolkit fetch --force-login`

仅监听 `127.0.0.1`，页面无任何 CDN/外部资源，数据保存在 `~/.config/jlu-toolkit/data/`。

### 一键同步（非交互）

```bash
jlu-toolkit sync    # 课表/成绩/考试/校历/节次时间/官方绩点/学业完成 → ~/.config/jlu-toolkit/data/
```
终端只打印条数、成功/失败等摘要，**不打印绩点、学分等个人数值**；任何一项失败时退出码为 2。

## 绩点说明

`jlu-toolkit gpa`、`fetch` 输出的绩点目前是**全部课程的简单学分加权平均**：百分制 60 分记 1.0、每多 1 分 +0.1、90 分及以上 4.0；等级制按 优秀95/良好85/中等75/及格65 换算；「通过」类不计入。

网页「成绩」页顶部另有教务**官方**「学分绩点统计」（初修/最高绩点、必修课绩点、加权平均分等），以教务为准。

自算绩点**不等于**教务或学院的官方口径（保研、综测等会剔除体育、公选、重修等不同课程）。请在网页界面里勾选需要计入的课程，并保存为自己的方案。

## 探测更多教务功能（`jlu-toolkit explore`）

```bash
jlu-toolkit explore
```

v2 会额外用内存中的学号/方案代码探测官方绩点与课组明细（不写入报告），并从空教室应用前端代码中提取接口路径（`discover`）。

用已保存会话**只读**探测考试安排、空教室、培养方案/学业完成、学期校历、个人信息等候选接口，生成 `jlu_explore_report.json`（Termux 下在「下载」目录）。
报告**只含状态码、JSON 键名、行数、字段名，不含任何值**（不含姓名、学号、成绩），可以直接贴给开发者用于适配。
绝不调用选课、退课、报名、评教提交等写接口。

## 接入 AI 助手（MCP）
```bash
pip install "jlu-toolkit[mcp] @ git+https://github.com/Runa-Asahi/JLU-Toolkit"
```
```json
{"mcpServers": {"jlu": {"command": "jlu-toolkit-mcp",
  "env": {"JLU_SCHEDULE_CSV": "/path/课表.csv", "JLU_GRADES_CSV": "/path/成绩.csv"}}}}
```

## 路线图
- [x] 课表/成绩文件导入、绩点计算、iCal 导出、MCP 接口
- [x] 教务 HTTP 自动导出（CAS 3DES + 二次认证 + 验证码自动识别；会话本地复用）
- [x] 本地网页界面：课表周视图、成绩勾选、命名绩点方案、考试倒计时、iCal 导出
- [x] 考试安排拉取与倒计时（接口按金智通用 `studentWdksapApp` 实现，待吉大实测确认）
- [x] `explore` 只读探测 + 脱敏报告
- [x] 教务校历自动识别开学日期/当前周、真实节次时间、官方学分绩点、学业完成（课组）进度
- [ ] 空教室（`explore` v2 正在定位 kxjscx 接口）
- [ ] 官方绩点口径（保研/综测）预设方案、不同学院规则可配置
- [ ] MCP 接入考试与绩点方案；桌面托盘挂件

欢迎 PR 和 ⭐！
