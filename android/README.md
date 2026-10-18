# JLU Toolkit Android 原型

用 [Chaquopy](https://chaquo.com/chaquopy/) 把仓库里的 `jlu_toolkit` 包和 Web UI 打进 APK。点开就能用，不需要 Termux。

## 工作方式

1. 启动时显示启动页，后台线程调用 `app/src/main/python/jlu_android.py` 的 `start()`。
2. `start()` 把 `XDG_CONFIG_HOME` 设为应用私有目录 `files/config`（数据在 `files/config/jlu-toolkit/data`），
   设置 `JLU_TOOLKIT_NO_KEYRING=1`，再用 `jlu_toolkit.ui.make_handler` 在 **127.0.0.1 的随机端口**起 `ThreadingHTTPServer`，不对局域网开放。
3. 全屏 WebView 加载该地址（开启 JavaScript 和 DOM Storage）。非本机链接交给系统浏览器打开。
4. 同时检查 `iedu.jlu.edu.cn` 的实际 HTTPS 入口；直连不可达时显示可关闭提示。校园网内可选直连，校外在「更多 → 登录」选择应用内 WebVPN；OA 的访问限制单独说明，连接检测不等于账号验证。

桌面端代码没有改动：`jlu_toolkit` 直接从仓库根目录打包（`app/build.gradle` 里的 `srcDir "../.."`），始终只有一份。

## 构建

需要：JDK 17+、Android SDK（platform 35）、构建机上的 **Python 3.13**（Chaquopy 要求构建 Python 和 APK 内的 Python 版本一致）。

```bash
cd android
echo "sdk.dir=$HOME/android/sdk" > local.properties   # 或设置 ANDROID_HOME
./gradlew assembleDebug        # → app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease      # → app/build/outputs/apk/release/app-release-unsigned.apk（不签名，由发版流程签）
```

- 版本号读环境变量 `JLU_VERSION_NAME` / `JLU_VERSION_CODE`，默认是 `0.0.0-dev` / `1`。
- 构建 Python 不在 PATH 上时，可以用 `-PbuildPython=/path/to/python3.13` 指定。
- 只打一个通用 APK（含 arm64-v8a 和 x86_64），不按 ABI 拆分。
- 依赖固定为 `cryptography==42.0.8`（Chaquopy 预编译包）。不安装 `keyring`。

## 已知限制（原型）

- **凭据加密**：Android 上没有系统钥匙串，`secure_store` 目前走文件回退，也就是明文保存在应用私有目录里。之后由 Android Keystore 接管（Asahi 负责，别名 `jlu-toolkit-storage`）。
- 不含成绩、OA 提醒和后台任务。
- 不支持 32 位设备（armeabi-v7a / x86）。
- 测试：`tests/test_android_bootstrap.py` 在桌面 Python 上验证 `jlu_android.start()`。
