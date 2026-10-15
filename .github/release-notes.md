## SuperJLU v1.0.1

v1.0.0 的修复版，建议全部用户升级。Android 可以直接覆盖安装，不会丢数据。

### 修复
- **Android 登录**：输入验证码时报错「Read-only file system（Errno 30）」的问题修好了。之前验证码图片会被写到只读的根目录，现在会自动改存到可写的目录（#39、#41）。
- **Windows 版 SuperJLU.exe**：默认使用文档中写的端口 `127.0.0.1:8765`，只有被占用时才换别的端口；再次双击时更容易找到已经在运行的窗口（#38）。
- **README**：更正了 apk 文件名和下载说明（#37）。

### 下载
- **Windows**：`SuperJLU.exe`，单文件，双击即可运行。
- **Android**：`SuperJLU-1.0.1.apk`（已签名，包名 `cn.superjlu.app`）
- 每个文件都附带 `.sha256` 校验文件。

完整功能介绍见 [v1.0.0](https://github.com/Runa-Asahi/SuperJLU/releases/tag/v1.0.0)。
