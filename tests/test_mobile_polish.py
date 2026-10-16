import pytest
from jlu_toolkit import jwxt, ui
Store = ui.Store


def test_conn_abort_retried_then_network_error(monkeypatch):
    c = jwxt.JwxtClient()
    calls = []

    class Op:
        def open(self, req, timeout=None):
            calls.append(1)
            raise ConnectionAbortedError(103, "Software caused connection abort")
    c.opener = Op()
    with pytest.raises(jwxt.NetworkError):
        c._request("https://example.invalid/x")
    assert len(calls) == 2


def test_bootstrap_marker(tmp_path):
    s = Store(tmp_path)
    assert ui.needs_bootstrap(s)
    s.p("bootstrap_done").write_text("x")
    assert not ui.needs_bootstrap(s)
