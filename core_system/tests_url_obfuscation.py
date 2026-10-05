"""Tests for the URL encryption & obfuscation service.

Run WITHOUT a database (all cases are SimpleTestCase):
    python -c "import django, unittest; django.setup();
      suite = unittest.defaultTestLoader.loadTestsFromName(
        'core_system.tests_url_obfuscation');
      raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())"
"""
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.contrib.sessions.backends.signed_cookies import SessionStore

from core_system import url_obfuscation as obf
from core_system.middleware import UrlObfuscationMiddleware
from core_system import url_obfuscation_views as obf_views


SESSION_SETTINGS = {
    "SESSION_ENGINE": "django.contrib.sessions.backends.signed_cookies",
    "URL_OBFUSCATION_ENABLED": True,
    "URL_OBFUSCATION_REQUIRE_SIGNATURE": False,
    "SECRET_KEY": "test-secret-key-for-obfuscation",
}


def _request(path="/api/treasurer/members/list/", query="", session_data=None):
    factory = RequestFactory()
    req = factory.get(path + ("?" + query if query else ""))
    session = SessionStore()
    for k, v in (session_data or {}).items():
        session[k] = v
    session.save()
    req.session = session
    return req


def _ok_response(request):
    return HttpResponse("OK")


class ServiceTests(SimpleTestCase):
    def test_sign_verify_roundtrip(self):
        sig = obf.compute_sig("/api/x/", [("page", "2"), ("search", "a b")], "k1")
        req = _request("/api/x/", f"page=2&search=a+b&_s={sig}", {"url_obf_key": "k1"})
        self.assertTrue(obf.verify_signed_query("/api/x/", req.GET, "k1"))

    def test_tampered_param_fails(self):
        sig = obf.compute_sig("/api/x/", [("page", "2")], "k1")
        req = _request("/api/x/", f"page=3&_s={sig}", {"url_obf_key": "k1"})
        self.assertFalse(obf.verify_signed_query("/api/x/", req.GET, "k1"))

    def test_wrong_key_fails(self):
        sig = obf.compute_sig("/api/x/", [("page", "2")], "k1")
        req = _request("/api/x/", f"page=2&_s={sig}", {"url_obf_key": "k1"})
        self.assertFalse(obf.verify_signed_query("/api/x/", req.GET, "other"))

    def test_missing_sig_fails(self):
        req = _request("/api/x/", "page=2", {"url_obf_key": "k1"})
        self.assertFalse(obf.verify_signed_query("/api/x/", req.GET, "k1"))

    def test_cache_busters_ignored(self):
        sig = obf.compute_sig("/api/x/", [("page", "2")], "k1")
        req = _request("/api/x/", f"page=2&_s={sig}&_=12345&t=99", {"url_obf_key": "k1"})
        self.assertTrue(obf.verify_signed_query("/api/x/", req.GET, "k1"))

    def test_sign_url_refreshes_sig(self):
        first = obf.sign_url("/api/x/?page=2", "k1")
        # Re-signing must not stack signatures and must stay valid.
        second = obf.sign_url(first + "&_=1", "k1")
        self.assertEqual(second.count("_s="), 1)
        req = _request("/api/x/", second.split("?", 1)[1], {"url_obf_key": "k1"})
        self.assertTrue(obf.verify_signed_query("/api/x/", req.GET, "k1"))

    @override_settings(SECRET_KEY="test-secret-key-for-obfuscation")
    def test_opaque_roundtrip(self):
        token = obf.opaque_encode({"session_expired": "1"})
        # Opaque: no readable key leaks into the token.
        self.assertNotIn("session_expired", token)
        self.assertEqual(obf.opaque_decode(token), {"session_expired": "1"})

    @override_settings(SECRET_KEY="test-secret-key-for-obfuscation")
    def test_opaque_tamper_returns_none(self):
        token = obf.opaque_encode({"session_expired": "1"})
        bad = ("A" if token[0] != "A" else "B") + token[1:]
        self.assertIsNone(obf.opaque_decode(bad))
        self.assertIsNone(obf.opaque_decode("not-a-token!!"))

    @override_settings(SECRET_KEY="test-secret-key-for-obfuscation")
    def test_session_expired_url_shape(self):
        url = obf.session_expired_url()
        self.assertTrue(url.startswith("/?x="))
        self.assertNotIn("session_expired=1", url)

    def test_sign_id_roundtrip_and_bad(self):
        token = obf.sign_id(42)
        self.assertNotEqual(token, "42")
        self.assertEqual(obf.unsign_id(token), "42")
        self.assertIsNone(obf.unsign_id(token + "tampered"))

    def test_session_key_helpers(self):
        req = _request()
        self.assertIsNone(obf.get_session_key(req))
        key = obf.get_or_create_session_key(req)
        self.assertTrue(key)
        self.assertEqual(obf.get_session_key(req), key)
        rotated = obf.rotate_session_key(req)
        self.assertTrue(rotated and rotated != key)


@override_settings(**SESSION_SETTINGS)
class MiddlewareTests(SimpleTestCase):
    def _run(self, req):
        return UrlObfuscationMiddleware(_ok_response)(req)

    def test_valid_signature_passes(self):
        sig = obf.compute_sig("/api/treasurer/members/list/", [("page", "2")], "sess-key")
        req = _request("/api/treasurer/members/list/", f"page=2&_s={sig}", {"url_obf_key": "sess-key"})
        resp = self._run(req)
        self.assertEqual(resp.status_code, 200)

    def test_tampered_signature_404s(self):
        sig = obf.compute_sig("/api/treasurer/members/list/", [("page", "2")], "sess-key")
        req = _request("/api/treasurer/members/list/", f"page=999&_s={sig}", {"url_obf_key": "sess-key"})
        resp = self._run(req)
        self.assertEqual(resp.status_code, 404)

    def test_missing_signature_passes_in_compat_mode(self):
        req = _request("/api/treasurer/members/list/", "page=2", {"url_obf_key": "sess-key"})
        resp = self._run(req)
        self.assertEqual(resp.status_code, 200)

    @override_settings(URL_OBFUSCATION_REQUIRE_SIGNATURE=True)
    def test_missing_signature_404s_in_hard_mode(self):
        req = _request(
            "/api/treasurer/members/list/", "page=2",
            {"url_obf_key": "sess-key", "access_token": "tok"},
        )
        resp = self._run(req)
        self.assertEqual(resp.status_code, 404)

    @override_settings(URL_OBFUSCATION_REQUIRE_SIGNATURE=True)
    def test_bare_path_passes_in_hard_mode(self):
        req = _request("/treasurer/", "", {"url_obf_key": "sess-key", "access_token": "tok"})
        resp = self._run(req)
        self.assertEqual(resp.status_code, 200)

    def test_valid_envelope_passes_and_decodes(self):
        url = obf.opaque_url("/", {"session_expired": "1"})
        req = _request("/", url.split("?", 1)[1])
        resp = self._run(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(getattr(req, "obf_envelope", {}), {"session_expired": "1"})

    def test_tampered_envelope_404s(self):
        url = obf.opaque_url("/", {"session_expired": "1"})
        query = url.split("?", 1)[1]
        bad = query[:-2] + ("AA" if not query.endswith("AA") else "BB")
        req = _request("/", bad)
        resp = self._run(req)
        self.assertEqual(resp.status_code, 404)

    def test_exempt_paths_pass(self):
        for path in ("/admin/", "/sw.js", "/api/public/bylaws/", "/register/", "/api/url/session-expired/"):
            req = _request(path, "anything=edited-by-user", {"url_obf_key": "sess-key"})
            self.assertEqual(self._run(req).status_code, 200, path)

    @override_settings(URL_OBFUSCATION_ENABLED=False)
    def test_kill_switch_disables(self):
        req = _request("/api/x/", "page=999&_s=bogus", {"url_obf_key": "sess-key"})
        self.assertEqual(self._run(req).status_code, 200)


@override_settings(**SESSION_SETTINGS)
class ObfViewTests(SimpleTestCase):
    def test_session_expired_envelope_view(self):
        req = _request("/api/url/session-expired/", "")
        resp = obf_views.session_expired_envelope(req)
        self.assertEqual(resp.status_code, 200)
        import json

        data = json.loads(resp.content)
        self.assertTrue(data["ok"] and data["url"].startswith("/?x="))
        from urllib.parse import parse_qs, urlsplit

        token = parse_qs(urlsplit(data["url"]).query)["x"][0]
        self.assertEqual(obf.opaque_decode(token), {"session_expired": "1"})

    def test_sign_urls_needs_key(self):
        import json

        factory = RequestFactory()
        req = factory.post("/api/url/sign/", json.dumps({"urls": ["/api/x/?a=1"]}), content_type="application/json")
        req.session = SessionStore()
        resp = obf_views.sign_urls(req)
        self.assertEqual(resp.status_code, 401)

    def test_sign_urls_batch(self):
        import json

        factory = RequestFactory()
        req = factory.post(
            "/api/url/sign/",
            json.dumps({"urls": ["/api/x/?a=1", "/api/y/?b=2&b=3"]}),
            content_type="application/json",
        )
        session = SessionStore()
        session["url_obf_key"] = "sess-key"
        session.save()
        req.session = session
        resp = obf_views.sign_urls(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data["ok"] and len(data["urls"]) == 2)
        for signed in data["urls"]:
            path, query = signed.split("?", 1)
            check = _request(path, query, {"url_obf_key": "sess-key"})
            self.assertTrue(obf.verify_signed_query(path, check.GET, "sess-key"), signed)

    def test_not_found_view_renders_404(self):
        req = _request("/nope/", "")
        resp = obf_views.obfuscated_not_found_view(req)
        self.assertEqual(resp.status_code, 404)
