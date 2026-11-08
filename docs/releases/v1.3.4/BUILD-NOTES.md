# SuperJLU v1.3.4 备用分发构建说明

本次分发基于原作者 Runa-Asahi 的官方 v1.3.4，保留原作者署名、贡献记录和 MIT 许可证，不含 v1.3.5 的功能提交。

## 源码与 Windows

- 官方版本提交：`3ac6e7d82a0e8348b752979fc4b78c91b5963304`。
- 当前公开 Windows 安装包构建提交：`3ac6e7d82a0e8348b752979fc4b78c91b5963304`，由 v1.3.4 标签自动构建发布。
- Windows 构建：[GitHub Actions](https://github.com/Aohpup/SuperJLU/actions/runs/42499771915)，测试和打包均通过。
- Windows 使用原版程序标识与配置路径，不承诺与原版进程隔离。

## Android 独立版

- 应用名称：SuperJLU（独立版）。
- 包名：`cn.superjlu.app.aohpup`；版本名称：`1.3.4-aohpup.1`；版本号：`2000134`。
- Android 7.0 / API 24 起，包含 arm64-v8a 与 x86_64。
- 使用独立签名，可与原版共存，不覆盖原版、不自动迁移原版数据，需要重新登录。
- 本次构建仅调整 Android 的包名、应用名称和构建版本；Python 与 Java 功能代码保持官方 v1.3.4。
- 签名证书 SHA-256：`6ddbf4776139633b947260c2ce9f0d75f2a13ac6d55ea8577963d36b363e7076`。
- 已验证 APK v1/v2/v3 签名、对齐、非调试配置、独立分享 provider authority 和打包 Python 页面与源码一致。
- 没有进行本次 APK 的真机登录、同步与安装复测；构建检查不能替代真机测试。

### 重建 Android 包

1. 检出官方 v1.3.4 源码，准备 JDK 17、Android SDK 35 和 Python 3.13。
2. 仅将 `android/app/src/main/res/values/strings.xml` 的 `app_name` 从 `SuperJLU` 改为 `SuperJLU（独立版）`。
3. 设置 `JLU_VERSION_NAME=1.3.4-aohpup.1`、`JLU_VERSION_CODE=2000134`。
4. 在 `android` 目录执行 `./gradlew --no-daemon -I /绝对路径/android-independent.init.gradle -PbuildPython=/Python3.13路径 assembleRelease`。
5. 用 `zipalign -f -p 4` 对齐 APK，再使用自己的发布密钥和 `apksigner` 签名；启用 v1、v2、v3，并以 `--min-sdk-version 21` 验证签名覆盖。

分发签名私钥不公开；如要覆盖安装本仓库后续独立版，必须沿用本次签名。第三方重新签名的同包名 APK 无法直接覆盖本包。

## 下载与数据

应用内检查更新仍指向原仓库；请通过 Aohpup/SuperJLU 的 Releases 页面手动下载。安装包来自干净的已跟踪源码，不包含本地账号配置、会话、真实成绩单或测试数据。两个安装包的 SHA-256 校验文件保存在本目录，通过发布说明中的折叠入口查看。

## 发布记录

首次手动发布后，v1.3.4 标签触发了仓库自带的 Windows 发布流程，重新生成并替换了 EXE。本目录的 Windows 校验记录对应当前标签自动构建的安装包，不再使用首次手动构建的旧校验值。Android 独立版安装包未被替换；原签名发布流程因仓库没有原作者签名密钥而失败。
