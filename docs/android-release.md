# Android 发布约定（给 `android/` Gradle 项目）

CI：`.github/workflows/release-android.yml`。推 `v*` 标签 → 签名 release apk 上传到同名 Release（与 Windows exe 共用）；手动运行 → 未签名 debug apk 作为 Actions 产物。

## Gradle 项目需要满足

1. `android/gradlew`（含 wrapper jar）存在；CI 在 `android/` 下执行 `./gradlew assembleRelease` / `assembleDebug`。没有 `android/gradlew` 时工作流直接跳过并提示。
2. 应用模块名为 `app`，产物路径：
   - release：`android/app/build/outputs/apk/release/*.apk`（**不签名**，即 `app-release-unsigned.apk`；不要在 Gradle 里配置 `signingConfig`，签名由 CI 用 apksigner 完成）
   - debug：`android/app/build/outputs/apk/debug/app-debug.apk`
3. 单一 apk（不做 ABI split）；如要 split，先跟 Asahi 说，CI 需要改成多文件。
4. 版本号从环境变量读取，本地缺省时给默认值：
   ```kotlin
   versionName = System.getenv("JLU_VERSION_NAME") ?: "0.0.0-dev"   // = jlu_toolkit.__version__
   versionCode = (System.getenv("JLU_VERSION_CODE") ?: "1").toInt()  // = GitHub run number，单调递增
   ```
5. JDK 17、CI 用 `android-actions/setup-android` 的最新 build-tools；Chaquopy `buildPython` 用 CI 里的 Python 3.11（`python3` 在 PATH 上）。
6. 签名：CI 从 secrets `ANDROID_KEYSTORE_B64 / ANDROID_KEYSTORE_PASSWORD / ANDROID_KEY_ALIAS / ANDROID_KEY_PASSWORD` 还原 PKCS12 keystore（别名 `jlu-toolkit`，RSA 4096，30 年）。Gradle 不需要读这些变量。

## Chaquopy 与 cryptography

`secure_store` 在 Android 下用 Android Keystore（别名 `jlu-toolkit-storage`，AES/GCM/NoPadding）包裹 32 字节主密钥，
包裹后的密钥存 `<config>/storage-key.wrapped`；数据仍是 AES-256-GCM 的 `.enc`（格式不变），需要 `cryptography`。
`cryptography` 是原生扩展，必须用 Chaquopy 仓库提供的 wheel（https://chaquo.com/pypi-13.1/cryptography/），目前最新为 **42.0.8**（cp38–cp313，arm64-v8a / x86_64 等）：

```kotlin
chaquopy { defaultConfig { pip {
    install("cryptography==42.0.8")
    install("..")            // 或安装 jlu_toolkit 源码 / wheel
} } }
```

不要在 Android 上装 `keyring`（用不到）。Python 侧通过 `from java import jclass` 自动识别 Chaquopy，`secure_store.backend_name()` 返回 `android-keystore`。
