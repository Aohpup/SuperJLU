## SuperJLU v1.0.4

建议 Windows 用户升级。Android 可以直接覆盖安装，不会丢数据。

### 修复
- **验证码图片不再保存到桌面**：应用内登录识别图形验证码只在内存中进行，不再往工作目录写 `jlu_cas_captcha.jpg`（#56）。
- **发送验证码时 Failed to fetch**：发送验证码最多等待 30 秒左右，超时提示重新发送，不再让一个请求挂几分钟；再遇到连接中断时会提示是需要重试还是后台已退出（#56、#57）。
- 登录相关异常和耗时会写入 `desktop.log`，方便排查（#56）。

### 下载
- **Windows**：`SuperJLU.exe`，单文件，双击即可运行。
- **Android**：`SuperJLU-1.0.4.apk`（已签名，包名 `cn.superjlu.app`）
- 每个文件都附带 `.sha256` 校验文件。

完整功能介绍见 [v1.0.0](https://github.com/Runa-Asahi/SuperJLU/releases/tag/v1.0.0)。
