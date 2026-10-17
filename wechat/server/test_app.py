import concurrent.futures
import contextlib
import json
import os
import gzip
import io
import sys
import tempfile
import threading
import time
import uuid
import shutil
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import app
import adapter
import cas_transport
import network_probe
from email.message import Message


class BackendTests(unittest.TestCase):
    def test_network_diagnostic_omits_login_html_and_redacts_denial_text(self):
        from types import SimpleNamespace
        headers = Message()
        headers['Content-Type'] = 'text/html; charset=utf-8'
        raw = b'<title>Login</title><input name="lt" value="private-login-value">'
        result = network_probe.inspect_response(SimpleNamespace(status=200, headers=headers, read=io.BytesIO(raw).read), 'https://vpn.jlu.edu.cn/login')
        self.assertNotIn('private-login-value', json.dumps(result))
        self.assertNotIn('error_page_text', result)
        text = '<style>private-css</style><script>private-js</script>Access denied 1.2.3.4 token=private-token https://example.test/?ticket=private-ticket'
        safe = network_probe.safe_error_text(text)
        for secret in ('private-css', 'private-js', '1.2.3.4', 'private-token', 'private-ticket'):
            self.assertNotIn(secret, safe)
        self.assertIn('Access denied', safe)

    def test_cas_transport_rejects_non_cas_destinations_and_foreign_service(self):
        for url in ["http://cas.jlu.edu.cn/tpass/login", "https://iedu.jlu.edu.cn/",
                    "https://cas.jlu.edu.cn.evil.test/tpass/login", "https://cas.jlu.edu.cn/tpass/logout",
                    "https://cas.jlu.edu.cn/tpass/login?service=https%3A%2F%2Fevil.test%2F",
                    "https://cas.jlu.edu.cn/tpass/login?service=https%3A%2F%2Fiedu.jlu.edu.cn%2F%3Fticket%3Dx"]:
            with self.assertRaises(cas_transport.CasTransportError):
                cas_transport.target_url(url)

    def test_cas_transport_returns_ticket_without_requesting_campus_or_exposing_cookies(self):
        response = io.BytesIO(b"")
        response.status = 302
        response.headers = Message()
        response.headers["Location"] = "https://iedu.jlu.edu.cn/?ticket=ST-synthetic"
        response.headers["Set-Cookie"] = "CASTGC=private-cas-session; Path=/tpass"
        response.headers["Set-Cookie"] = "mobile_error_info=success; Path=/tpass"
        flow = cas_transport.CasFlow()
        with patch.object(flow.opener, "open", return_value=response) as opened:
            result = flow.request({"url":"https://cas.jlu.edu.cn/tpass/login", "method":"POST", "data":"rsa=synthetic"})
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(opened.call_args.args[0].host, "cas.jlu.edu.cn")
        self.assertEqual(result["header"]["Location"], "https://iedu.jlu.edu.cn/?ticket=ST-synthetic")
        self.assertEqual(result["cookies"], ["mobile_error_info=success; Path=/tpass"])
        self.assertNotIn("private-cas-session", json.dumps(result))

    def test_cas_transport_isolates_flow_ids_and_cleans_up_without_academic_files(self):
        a, b = self.token("a"), self.token("b")
        with patch.object(cas_transport.CasFlow, "request", return_value={"statusCode":200,"data":"fixture"}):
            result = self.api.dispatch("POST", "/api/cas/request", {"url":"https://cas.jlu.edu.cn/tpass/login"}, a)
            with self.assertRaises(cas_transport.CasTransportError):
                self.api.dispatch("POST", "/api/cas/request", {"url":"https://cas.jlu.edu.cn/tpass/login","flow":result["flow"]}, b)
            self.api.dispatch("POST", "/api/cas/clear", {}, a)
            with self.assertRaises(cas_transport.CasTransportError):
                self.api.dispatch("POST", "/api/cas/request", {"url":"https://cas.jlu.edu.cn/tpass/login","flow":result["flow"]}, a)
            self.api.dispatch("POST", "/api/logout", {}, a)

    def test_cas_sms_cooldown_survives_flow_closure_and_invalid_methods_do_not_send(self):
        flows = cas_transport.CasFlows()
        with patch.object(cas_transport.CasFlow, "request", return_value={"statusCode":200}) as network:
            result = flows.request({"url":"https://cas.jlu.edu.cn/tpass/mobilecode?method=isPhone"})
            flows.clear()
            with self.assertRaises(cas_transport.CasTransportError):
                flows.request({"url":"https://cas.jlu.edu.cn/tpass/mobilecode?method=isPhone"})
            with self.assertRaises(cas_transport.CasTransportError):
                flows.request({"url":"https://cas.jlu.edu.cn/tpass/mobilecode?method=resetPassword"})
            self.assertEqual(network.call_count, 1)

    def test_cas_transport_hides_urls_on_network_failure(self):
        flow = cas_transport.CasFlow()
        with patch.object(flow.opener, "open", side_effect=urllib.error.URLError("private-code-in-url")):
            with self.assertRaises(cas_transport.CasTransportError) as error:
                flow.request({"url":"https://cas.jlu.edu.cn/tpass/code?secret"})
        self.assertNotIn("private-code", str(error.exception))

    def setUp(self):
        temporary_root = Path(__file__).parent / ".data" / "tests"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.test_root = temporary_root.resolve()
        self.test_dir = self.test_root / ("run-" + uuid.uuid4().hex)
        self.test_dir.mkdir()
        self.api = app.Application(b"K" * 32, self.test_dir, appid="wx-test",
                                   exchange=lambda code: {"a": "openid-a", "b": "openid-b"}.get(code, code))

    def tearDown(self):
        self.assertEqual(self.test_dir.resolve().parent, self.test_root)
        shutil.rmtree(self.test_dir)

    def token(self, code="a"):
        return self.api.dispatch("POST", "/api/wechat/login", {"code": code}, "")["token"]

    @contextlib.contextmanager
    def user(self, token):
        ctx = adapter.current_user.set(self.api.sessions[token].user)
        try:
            yield
        finally:
            adapter.current_user.reset(ctx)

    def test_real_exchange_login_does_not_expose_openid_or_key(self):
        result = self.api.dispatch("POST", "/api/wechat/login", {"code": "a"}, "")
        self.assertEqual(set(result), {"token", "expires_in"})
        self.assertNotIn("openid", result["token"])
        self.assertEqual(result["expires_in"], 7200)

    def test_wechat_transport_accepts_compressed_json(self):
        self.api.secret = "private-api-secret"
        response = io.BytesIO(gzip.compress(json.dumps({"openid": "verified-user"}).encode()))
        response.headers = {"Content-Encoding": "gzip"}
        with patch.object(app.urllib.request, "urlopen", return_value=response):
            self.assertEqual(self.api.exchange_wechat("wx-code"), "verified-user")

    def test_wechat_transport_diagnostics_do_not_log_credentials(self):
        self.api.secret = "private-api-secret"
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(app.urllib.request, "urlopen", side_effect=urllib.error.URLError("https://api.weixin.qq.com/?secret=private-api-secret")):
            with self.assertRaises(app.ApiError) as error:
                self.api.exchange_wechat("wx-code")
        self.assertEqual(error.exception.code, "WECHAT_UNAVAILABLE")
        self.assertNotIn("private-api-secret", output.getvalue())
        self.assertIn("URLError", output.getvalue())

    def test_development_login_disabled_by_default(self):
        with self.assertRaises(app.ApiError) as error:
            self.token("dev:test")
        self.assertEqual(error.exception.status, 403)

    def test_cloud_identity_requires_platform_environment_and_complete_headers(self):
        headers = {"X-WX-ENV": "test-cloud", "X-WX-APPID": "wx-test", "X-WX-SOURCE": "wx_client", "X-WX-OPENID": "openid-a"}
        with patch.dict(os.environ, {"CBR_ENV_ID": ""}):
            with self.assertRaises(app.ApiError):
                self.api.dispatch("POST", "/api/wechat/cloud-login", {}, "", headers=headers)
        with patch.dict(os.environ, {"CBR_ENV_ID": "test-cloud"}):
            for field in headers:
                bad = dict(headers)
                bad.pop(field)
                with self.assertRaises(app.ApiError):
                    self.api.dispatch("POST", "/api/wechat/cloud-login", {}, "", headers=bad)
            result = self.api.dispatch("POST", "/api/wechat/cloud-login", {}, "", headers=headers)
            self.assertEqual(set(result), {"token", "expires_in"})
            other_token = self.token("a")
            self.assertEqual(self.api.sessions[result["token"]].user, self.api.sessions[other_token].user)

    def test_cloud_identity_rejects_other_application_or_environment(self):
        headers = {"x-wx-env": "test-cloud", "x-wx-appid": "wx-other", "x-wx-source": "wx_client", "x-wx-openid": "a"}
        with patch.dict(os.environ, {"CBR_ENV_ID": "test-cloud"}):
            with self.assertRaises(app.ApiError):
                self.api.cloud_login(headers, "127.0.0.1")
            headers["x-wx-appid"] = "wx-test"
            headers["x-wx-env"] = "different-cloud"
            with self.assertRaises(app.ApiError):
                self.api.cloud_login(headers, "127.0.0.1")

    def test_unauthenticated_and_expired_tokens_rejected(self):
        with self.assertRaises(app.ApiError):
            self.api.dispatch("GET", "/api/data", {}, "")
        token = self.token()
        self.api.sessions[token].expires = time.time() - 1
        with self.assertRaises(app.ApiError) as error:
            self.api.dispatch("GET", "/api/data", {}, token)
        self.assertEqual(error.exception.code, "TOKEN_EXPIRED")

    def test_users_cannot_read_each_others_encrypted_cache(self):
        a, b = self.token("a"), self.token("b")
        with self.user(a):
            adapter.write("academic", {"grades": ["private-a"]})
            encrypted = (adapter.config_dir() / "academic.enc").read_bytes()
            self.assertNotIn(b"private-a", encrypted)
            self.assertFalse((adapter.config_dir() / "academic.json").exists())
        with self.user(b):
            self.assertIsNone(adapter.read("academic"))
            self.assertNotEqual(adapter.user_key(), b"K" * 32)
        self.assertEqual(self.api.dispatch("GET", "/api/data", {}, a)["grades"], ["private-a"])
        self.assertEqual(self.api.dispatch("GET", "/api/data", {}, b)["grades"], [])

    def test_request_context_isolates_parallel_users(self):
        tokens = [self.token("a"), self.token("b")]
        def task(token):
            with self.user(token):
                adapter.write("parallel", {"owner": token})
                time.sleep(.01)
                return adapter.read("parallel")["owner"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(task, tokens)), tokens)

    def test_same_wechat_identity_reuses_only_its_own_cache(self):
        first, second = self.token("a"), self.token("a")
        with self.user(first):
            adapter.write("academic", {"grades": ["mine"]})
        self.assertEqual(self.api.dispatch("GET", "/api/data", {}, second)["grades"], ["mine"])

    def test_logout_revokes_all_same_user_tokens_and_deletes_only_that_user(self):
        a, a2, b = self.token("a"), self.token("a"), self.token("b")
        for token in [a, b]:
            with self.user(token):
                adapter.write("academic", {"grades": [token]})
        self.api.dispatch("POST", "/api/logout", {}, a)
        for token in [a, a2]:
            with self.assertRaises(app.ApiError):
                self.api.dispatch("GET", "/api/data", {}, token)
        self.assertEqual(self.api.dispatch("GET", "/api/data", {}, b)["grades"], [b])

    def test_tampered_ciphertext_fails_closed(self):
        token = self.token()
        with self.user(token):
            adapter.write("academic", {"grades": ["secret"]})
            p = adapter.config_dir() / "academic.enc"
            blob = bytearray(p.read_bytes())
            blob[-1] ^= 1
            p.write_bytes(blob)
            with self.assertRaises(adapter.secure_store.SecureStoreError):
                adapter.snapshot()

    def test_import_preserves_missing_point_and_never_replaces_official_cache(self):
        import base64
        token = self.token()
        with self.user(token):
            adapter.write("academic", {"grades": ["original"]})
        result = self.api.dispatch("POST", "/api/grades/import", {
            "filename": "grades.csv", "data": base64.b64encode("课程,学分,成绩\n数学,3,90".encode()).decode()
        }, token)
        self.assertIsNone(result["grades"][0]["point"])
        self.assertEqual(self.api.dispatch("GET", "/api/data", {}, token)["grades"], ["original"])

    def test_college_notice_items_are_preserved(self):
        token = self.token()
        with patch.object(adapter.college, "fetch", return_value={"items": [
            {"id": "1", "title": "校园通知", "url": "https://csw.jlu.edu.cn/info/1/2.htm"}
        ], "hint": ""}):
            result = self.api.dispatch("POST", "/api/notices", {"category": "csw-xytz"}, token)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["title"], "校园通知")

    def test_room_input_validation_precedes_network(self):
        token = self.token()
        with self.assertRaises(ValueError):
            self.api.dispatch("POST", "/api/rooms", {"campus": "../../"}, token)

    def test_login_rate_limit(self):
        for i in range(20):
            self.token(str(i))
        with self.assertRaises(app.ApiError) as error:
            self.token("21")
        self.assertEqual(error.exception.status, 429)

    def test_school_flow_expiration_and_no_saved_password(self):
        flow = adapter.SchoolSession()
        self.assertFalse(hasattr(flow, "password"))
        flow.client = object()
        flow.started = time.monotonic() - 601
        with self.assertRaises(ValueError):
            flow.need()
        self.assertIsNone(flow.client)

    def test_manual_second_factor_state_machine(self):
        class Client:
            def __init__(self, **kwargs):
                self.last_captcha_bytes = None
            def login_password(self, u, p):
                return adapter.jwxt.LoginStep.NEED_SECOND_FACTOR
            def download_captcha(self, save=False):
                self.last_captcha_bytes = b"jpeg"
            def request_wechat_code(self, code):
                return adapter.jwxt.WechatCodeResult.SUCCESS
            def login_second_factor(self, image, wechat):
                return adapter.jwxt.LoginStep.SUCCESS
            def save_session(self):
                pass
            def bootstrap_emap_apps(self):
                pass
        with patch.object(adapter.jwxt, "JwxtClient", Client):
            flow = adapter.SchoolSession()
            self.assertEqual(flow.start("user", "secret")["step"], "need_second_factor")
            self.assertEqual(flow.send_code("1234")["step"], "code_sent")
            self.assertEqual(flow.verify("5678")["step"], "success")
            self.assertIsNone(flow.client)

    def test_partial_sync_keeps_previous_failed_module(self):
        token = self.token()
        with self.user(token):
            adapter.write("academic", {"courses": [], "grades": [{"name": "cached"}], "exams": [], "calendar": {}, "periods": {}})
        class Client:
            def current_semester(self): return "2026-2027-1"
            def fetch_schedule(self, term): return []
            def fetch_grades(self): raise adapter.jwxt.NetworkError("offline")
            def fetch_exams(self, term): return []
            def save_session(self): pass
        with patch.object(adapter, "client", return_value=Client()), patch.object(adapter.meta, "fetch_calendar", return_value={}), patch.object(adapter.meta, "fetch_periods", return_value={}), patch.object(adapter.meta, "fetch_official_gpa", return_value={}), patch.object(adapter.meta, "fetch_completion", return_value={}), patch.object(adapter.plan, "fetch_plan", return_value={}):
            job = self.api.dispatch("POST", "/api/refresh", {}, token)
            self.assertEqual(job["status"], "running")
            for _ in range(100):
                status = self.api.dispatch("GET", "/api/refresh/status", {}, token)
                if status["status"] != "running":
                    break
                time.sleep(.01)
            self.assertEqual(status["status"], "done")
            result = status["data"]
        self.assertEqual(result["grades"], [{"name": "cached"}])
        self.assertIn("grades", result["failures"])

    def test_http_end_to_end_auth_json_headers_logout(self):
        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(self.api))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = "http://127.0.0.1:" + str(server.server_address[1])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(path, body=None, token=""):
            req = urllib.request.Request(url + path,
                data=None if body is None else json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
            with opener.open(req, timeout=5) as response:
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                return json.load(response)
        try:
            self.assertEqual(request("/health")["status"], "ok")
            with self.assertRaises(urllib.error.HTTPError) as error:
                request("/api/data")
            self.assertEqual(error.exception.code, 401)
            token = request("/api/wechat/login", {"code": "a"})["token"]
            self.assertEqual(request("/api/data", token=token)["courses"], [])
            self.assertTrue(request("/api/logout", {}, token)["ok"])
            with self.assertRaises(urllib.error.HTTPError):
                request("/api/data", token=token)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
