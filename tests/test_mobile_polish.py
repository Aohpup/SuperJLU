import pytest
from jlu_toolkit import jwxt, ui
Store = ui.Store


def test_outer_operation_is_not_replayed_after_connection_abort(monkeypatch):
    c = jwxt.JwxtClient()
    calls = []

    class Op:
        def open(self, req, timeout=None):
            calls.append(1)
            raise ConnectionAbortedError(103, "Software caused connection abort")
    c.opener = Op()
    with pytest.raises(jwxt.NetworkError):
        c._request("https://example.invalid/x")
    # Recovery belongs to one HTTPS hop, not a whole operation whose redirect
    # chain may already have submitted a password or consumed a ticket.
    assert len(calls) == 1


def test_bootstrap_marker(tmp_path):
    s = Store(tmp_path)
    assert ui.needs_bootstrap(s)
    s.p("bootstrap_done").write_text("x")
    assert not ui.needs_bootstrap(s)
