"""内置验证码求解器测试（Pillow + 嵌入模板）。"""
from pathlib import Path
import json

import pytest

from jlu_toolkit import captcha_solver

FIX = Path(__file__).parent / "fixtures" / "captcha_solve"


def test_templates_load():
    t = captcha_solver.load_templates()
    assert len(t) >= 100
    assert all(len(f) == captcha_solver.TW * captcha_solver.TH for _, f in t)


def test_solve_fixture_samples():
    pytest.importorskip("PIL")
    labels = json.loads((FIX / "labels.json").read_text())
    assert labels
    ok = 0
    for name, lab in labels.items():
        pred = captcha_solver.solve_captcha((FIX / name).read_bytes())
        if pred == lab:
            ok += 1
    assert ok / len(labels) >= 0.9


def test_solve_rejects_garbage():
    pytest.importorskip("PIL")
    assert captcha_solver.solve_captcha(b"not-an-image" + b"\x00" * 300) is None
