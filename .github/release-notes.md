## SuperJLU v1.0.2

建议全部用户升级。Android 可以直接覆盖安装，不会丢数据。

### 新功能
- **成绩加权分析**（感谢 [@Aohpup](https://github.com/Aohpup)）：教务成绩为主数据源，支持保研 / 奖学金 / 全部课程模板、自定义模板、搜索筛选排序、可选 Excel/CSV 成绩单导入（#44 → #45）。

### 修复
- **Android 启动偶发失败**：`Python already started` 导致启动页报错，现在启动已串行化（#47）。
- **不及格分数口径**：成绩页模板与 CLI 统一按 55 分计算（#46）。
- **成绩导入**：上限 5 MB；导入文件损坏时退回教务成绩；自动同步加了 10 分钟间隔（#45）。

### 下载
- **Windows**：`SuperJLU.exe`，单文件，双击即可运行。
- **Android**：`SuperJLU-1.0.2.apk`（已签名，包名 `cn.superjlu.app`）
- 每个文件都附带 `.sha256` 校验文件。

完整功能介绍见 [v1.0.0](https://github.com/Runa-Asahi/SuperJLU/releases/tag/v1.0.0)。
