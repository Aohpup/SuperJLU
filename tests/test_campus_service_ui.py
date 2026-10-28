import shutil
import subprocess
from pathlib import Path

import pytest


def test_campus_services_ui_behaviour():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    result = subprocess.run([node, "tests/js_campus_services_test.js"],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
