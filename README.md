# JLU Toolkit

吉大课表和成绩的本地小工具：导入文件后可以计算绩点、导出 iCal 日历（手机和电脑日历都能订阅，课前 15 分钟提醒），还提供 **MCP 接口**，让 Claude、Cursor 等 AI 助手直接回答"我明天有什么课""这学期绩点多少"。

> 🔒 **隐私**：课表/成绩默认只在你自己的电脑上读取和计算。可选的「教务拉取」会用你的统一身份认证账号直接向学校服务器发 HTTPS 请求，**凭据与会话只存在本机**（chmod 600），不经过任何第三方。

## 快速开始
```bash
pip install git+https://github.com/Runa-Asahi/JLU-Toolkit
jlu-toolkit ics examples/schedule.csv --first-monday 2026-09-07 -o 课表.ics
jlu-toolkit gpa examples/grades.csv --term 2025-2026-1
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

# 只拉课表 / 成绩 / 指定学期
jlu-toolkit fetch --user 你的邮箱前缀 --what schedule --term 2025-2026-2
```

图形验证码图片：
- **Termux**：优先保存到 `~/storage/downloads/jlu_cas_captcha.jpg`（请先 `termux-setup-storage`）
- 其他环境：当前目录下的 `jlu_cas_captcha.jpg`

> MCP **不会**代你登录教务；请先用上面的命令导出 CSV，再把路径配给 MCP。

### Termux（Android）示例
```bash
pkg install python git python-pillow
termux-setup-storage   # 授权后才能写到 Download/Pictures/DCIM
pip install -U --force-reinstall "git+https://github.com/Runa-Asahi/JLU-Toolkit.git@feat/jwxt-http-fetch"
# 可选：自动识别四位图形验证码
pip install ddddocr
jlu-toolkit fetch --probe
jlu-toolkit fetch --user 你的邮箱前缀 --force-login --debug
# 图形验证码会直接画在终端；同时保存 jlu_cas_captcha.jpg 与放大的 *_large.jpg
# 到 ~/storage/downloads、Pictures、dcim（并尝试 termux-media-scan）
# 输入图形码 → 去「智慧吉大」取微信验证码 → 粘贴回 Termux
```

> CAS 图形验证码原图只有约 **70×36、1.5–2KB**，系统相册经常「打不开/空白」。
> 请看终端 ASCII，或打开 `jlu_cas_captcha_large.jpg`。

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
- [x] 教务 HTTP 自动导出（CAS 3DES + 二次认证；会话本地复用）
- [ ] 考试倒计时、Windows 托盘挂件
- [ ] 绩点规则可配置（不同学院）

欢迎 PR 和 ⭐！
