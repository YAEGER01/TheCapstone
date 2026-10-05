"""Regression: CSP header, fetch-metadata POST guard, push endpoint allowlist."""
from django.test import TestCase


class FetchGuardTests(TestCase):
    def test_csp_header_present(self):
        r = self.client.get("/login/")
        csp = r.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)
        # Regression: dashboards load SweetAlert/Chart/flatpickr from jsdelivr —
        # omitting it silently kills every sidebar button incl. logout.
        self.assertIn("https://cdn.jsdelivr.net", csp)

    def test_cross_site_post_blocked(self):
        r = self.client.post("/api/push/health/", {}, HTTP_SEC_FETCH_SITE="cross-site")
        self.assertEqual(r.status_code, 403)
        self.assertIn("Cross-site", r.json()["error"])

    def test_same_origin_post_passes_guard(self):
        r = self.client.post("/api/push/health/", {}, HTTP_SEC_FETCH_SITE="same-origin")
        # Guard passes (a later middleware/view may still refuse: URL-OBF 404
        # here); the point is it is NOT the guard's Cross-site 403.
        self.assertFalse(r.status_code == 403 and b"Cross-site" in r.content)

    def test_foreign_origin_post_blocked(self):
        r = self.client.post("/api/push/health/", {}, HTTP_ORIGIN="https://evil.example")
        self.assertEqual(r.status_code, 403)

    def test_push_endpoint_validation(self):
        from core_system.push_views import _is_safe_push_endpoint

        self.assertTrue(_is_safe_push_endpoint("https://fcm.googleapis.com/fcm/send/abc"))
        self.assertFalse(_is_safe_push_endpoint("http://fcm.googleapis.com/fcm/send/abc"))
        self.assertFalse(_is_safe_push_endpoint("https://169.254.169.254/latest/meta-data/"))
        self.assertFalse(_is_safe_push_endpoint("https://localhost:8000/x"))
        self.assertFalse(_is_safe_push_endpoint("https://user:pass@fcm.googleapis.com/x"))
        self.assertFalse(_is_safe_push_endpoint("https://192.168.1.5/x"))

