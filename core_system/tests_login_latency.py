"""Login must return the OTP challenge quickly (queued email, no inline SMTP)
and Turnstile must still be enforced on localhost."""
import time
from unittest.mock import patch

from django.test import TestCase, override_settings

from core_system.auth_utils import hash_password
from core_system.models import OfficerUser


@override_settings(
    TURNSTILE_SITE_KEY="site-key",
    TURNSTILE_SECRET_KEY="secret-key",
    TURNSTILE_REQUIRE_ON_LOCALHOST=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class LoginLatencyTests(TestCase):
    def _officer(self):
        return OfficerUser.objects.create(
            username="latency_user",
            email="latency@test.local",
            password_hash=hash_password("Passw0rd!"),
            full_name="Latency User",
            role="member",
            account_status="Active",
        )

    @patch("core_system.turnstile._post_turnstile_siteverify", return_value={"success": True})
    def test_login_post_returns_quickly(self, _mock_siteverify):
        self._officer()
        start = time.time()
        resp = self.client.post(
            "/login/",
            {
                "username": "latency_user",
                "password": "Passw0rd!",
                "cf-turnstile-response": "fake-token",
            },
            HTTP_HOST="localhost",
        )
        elapsed = time.time() - start
        self.assertIn(resp.status_code, (200, 302), resp.content)
        # Queue insert is a fast DB write; inline SMTP used to take 8-15s.
        self.assertLess(elapsed, 1.5, f"login took {elapsed:.2f}s")
        # MFA challenge was established (session pre-auth token set).
        self.assertTrue(self.client.session.get("mfa_pre_auth_token"))
        # OTP email row was queued, not sent synchronously.
        from core_system.models import OutgoingEmail

        self.assertTrue(
            OutgoingEmail.objects.filter(
                subject="CAUFA MFA Verification Code",
                recipient_list=["latency@test.local"],
            ).exists()
        )

    @patch("core_system.turnstile._post_turnstile_siteverify", return_value={"success": True})
    def test_login_page_renders_with_turnstile_on_localhost(self, _mock_siteverify):
        resp = self.client.get("/login/", HTTP_HOST="localhost")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "cf-turnstile")

    @patch("core_system.turnstile._post_turnstile_siteverify", return_value={"success": False})
    def test_login_rejected_when_turnstile_fails(self, _mock_siteverify):
        self._officer()
        resp = self.client.post(
            "/login/",
            {
                "username": "latency_user",
                "password": "Passw0rd!",
                "cf-turnstile-response": "bad-token",
            },
            HTTP_HOST="localhost",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json().get("error_code"), "turnstile_failed")
        self.assertFalse(self.client.session.get("mfa_pre_auth_token"))
