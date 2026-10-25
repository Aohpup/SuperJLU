from jlu_toolkit import jwxt, sessions


def test_ilearn_does_not_inherit_jwxt_login(monkeypatch):
    for st in (jwxt.SESSION_OK, sessions.EXPIRED, sessions.MISSING):
        monkeypatch.setattr(jwxt, "session_status", lambda st=st: {"state": st, "checked_at": 1})
        il, jw = sessions.status("ilearn"), sessions.status("jwxt")
        assert il["state"] == sessions.MISSING
        assert il["checked_at"] is None and "follows" not in il
        assert il["name"] == "学在吉大"
