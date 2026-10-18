"""Manual campus/VPN policy regression using synthetic sessions only."""
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from jlu_toolkit import jwxt, network, sessions, ui, webvpn

VPN = [{"name": "VPN", "value": "synthetic", "domain": "vpn.jlu.edu.cn", "path": "/"}]


@pytest.mark.parametrize("saved,expected", [(None, "direct"), ({"mode":"direct"}, "direct"),
                                         ({"mode":"webvpn"}, "webvpn"), ({"version":2,"mode":"invalid"}, "direct")])
def test_manual_policy_preserves_previous_explicit_selection(saved, expected):
    if saved is not None:
        path = jwxt.config_dir() / "network-route.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved))
    assert webvpn.mode() == expected and jwxt.JwxtClient().route == expected


@pytest.mark.parametrize("cookies,expected", [([], "direct"), (VPN, "webvpn")])
def test_retired_auto_policy_keeps_owned_vpn_without_probing_network(monkeypatch, cookies, expected):
    path = jwxt.config_dir() / "network-route.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version":2,"mode":"auto"}))
    monkeypatch.setattr(sessions, "load_cookies", lambda sid: cookies if sid == "vpn" else [])
    monkeypatch.setattr(jwxt.JwxtClient, "_request", lambda *a, **kw: pytest.fail("policy migration must not probe/login"))
    assert webvpn.mode() == expected


def test_direct_failure_never_probes_or_switches_to_saved_vpn(monkeypatch):
    monkeypatch.setattr(sessions, "load_cookies", lambda *_: VPN)
    webvpn.set_mode("direct")
    c = jwxt.JwxtClient()
    calls = []
    def fail(req, **kwargs):
        calls.append(req)
        assert urllib.parse.urlsplit(req.full_url).hostname == jwxt.IEDU_HOST
        raise OSError("synthetic network failure")
    monkeypatch.setattr(c.opener, "open", fail)
    with pytest.raises(jwxt.NetworkError): c._request(jwxt.REF_SCHEDULE, data=b"synthetic-query")
    assert len(calls) == 1 and c.route == "direct" and webvpn.mode() == "direct"


def test_auto_mode_is_not_available():
    with pytest.raises(ValueError): webvpn.set_mode("auto")
    with pytest.raises(ValueError): jwxt.JwxtClient(route="auto")


def test_expired_vpn_does_not_invalidate_jwxt(monkeypatch):
    c = jwxt.JwxtClient(route="webvpn")
    monkeypatch.setattr(sessions, "load_cookies", lambda sid: VPN if sid == "vpn" else [])
    url = jwxt.CAS_LOGIN + "?service=" + urllib.parse.quote(webvpn.SERVICE, safe="")
    monkeypatch.setattr(c.opener, "open", lambda *a, **kw: network._response(
        urllib.request.Request(url), 200, "Content-Type: text/html\r\n", b"<form id='loginForm'>"))
    monkeypatch.setattr(jwxt, "mark_session_expired", lambda *a: pytest.fail("VPN is not JWXT"))
    with pytest.raises(jwxt.NetworkError) as error: c._request(jwxt.REF_SCHEDULE)
    assert error.value.kind == "webvpn"


def test_jwxt_requires_campus_direct_even_with_old_public_override(tmp_path):
    override = tmp_path / "links.json"
    override.write_text(json.dumps({"links":[{"id":"jwxt","campus_only":False}]}))
    link = next(item for item in ui.campus_links_api(override)["links"] if item["id"] == "jwxt")
    assert link["campus_only"] and urllib.parse.urlsplit(link["vpn_url"]).hostname == "vpn.jlu.edu.cn"


def test_removed_auto_endpoint_cannot_change_manual_route(tmp_path):
    webvpn.set_mode("webvpn")
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(ui.Store(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/api/network/auto",
                                     data=b"{}", headers={"Content-Type":"application/json"})
        with pytest.raises(urllib.error.HTTPError) as error: urllib.request.urlopen(req)
        assert error.value.code == 404 and webvpn.mode() == "webvpn"
    finally:
        server.shutdown(); server.server_close()
