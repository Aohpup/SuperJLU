"""PyInstaller 入口：jlu-toolkit.exe 等价于命令行 jlu-toolkit。

直接双击（无参数）时启动本地 Web UI 并打开浏览器，方便不熟悉命令行的同学。
"""
import sys

from jlu_toolkit.cli import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv += ["ui", "--open"]
    main()
