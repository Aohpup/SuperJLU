# v1.3.4 校验与构建说明

[返回下载页面](https://github.com/Aohpup/SuperJLU/releases/tag/v1.3.4)

## 安装包

- [Windows：SuperJLU.exe](https://github.com/Aohpup/SuperJLU/releases/download/v1.3.4/SuperJLU.exe)
- [Android：SuperJLU 独立版](https://github.com/Aohpup/SuperJLU/releases/download/v1.3.4/SuperJLU-1.3.4-aohpup.1.apk)

Android 独立版使用 `cn.superjlu.app.aohpup` 包名和独立签名，可与原版共存；需重新登录，不自动迁移原版数据。

## 校验文件

- [Windows SHA-256](SuperJLU.exe.sha256)
- [Android SHA-256](SuperJLU-1.3.4-aohpup.1.apk.sha256)

Windows 可在 PowerShell 执行 `Get-FileHash .\SuperJLU.exe -Algorithm SHA256`，将结果与对应校验文件中的值比较；APK 同理。校验文件对应发布页的同名安装包，文件内容变化时需要重新核对。

## 构建来源与配置

- [构建来源、验证结果与 Android 重建步骤](BUILD-NOTES.md)
- [Android 独立包构建配置](android-independent.init.gradle)

本目录只保存公开构建资料，不包含签名私钥、密码、账号、会话或真实成绩单。应用内检查更新仍指向原仓库，请通过本仓库 Releases 页面手动下载。
