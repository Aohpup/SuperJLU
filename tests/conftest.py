import pytest


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """所有测试使用临时配置目录，绝不读写真实 ~/.config/jlu-toolkit。"""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
