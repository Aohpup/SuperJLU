from jlu_toolkit import jwxt, sessions


def test_ilearn_follows_jwxt(monkeypatch):
    for st in (jwxt.SESSION_OK, sessions.EXPIRED, sessions.MISSING):
        monkeypatch.setattr(jwxt, "session_status", lambda st=st: {"state": st, "checked_at": 1})
        il, jw = sessions.status("ilearn"), sessions.status("jwxt")
        assert il["state"] == jw["state"] and il["needs_login"] == jw["needs_login"]
        assert il["name"] == "学在吉大" and il["follows"] == "jwxt"
