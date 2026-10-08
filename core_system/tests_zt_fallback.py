"""Zero Trust fallback parity: hard-check verify, screen unlock, and challenge
accept the same login-grade methods (email/push TOTP, authenticator app,
burning backup codes) — a Gmail outage must not wedge a live session."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from core_system.auth_utils import create_access_session
from core_system.models import OfficerUser
from core_system.services import zt_service
from core_system.services.mfa_service import (
    backup_codes_remaining,
    generate_authenticator_code,
    generate_authenticator_secret,
    generate_mfa_secret,
    issue_backup_codes,
)

VERIFY_URL = "/api/auth/zero-trust/verify/"
UNLOCK_URL = "/api/auth/zt/unlock/"
CHALLENGE_URL = "/api/auth/zero-trust/challenge/"


class ZeroTrustFallbackTests(TestCase):
    def setUp(self):
        cache.clear()

    def _officer(self, username="zt_fallback", **kw):
        defaults = dict(
            full_name="ZT Fallback",
            username=username,
            password_hash="x",
            role="treasurer",  # money-handling role: unlock escalates to OTP
            account_status="active",
            email=f"{username}@example.com",
            mfa_secret=generate_mfa_secret(),
        )
        defaults.update(kw)
        return OfficerUser.objects.create(**defaults)

    def _login(self, officer):
        session, token = create_access_session(
            officer=officer, ip_address="127.0.0.1", device_info="tests",
        )
        session.trusted_device = True
        session.save()
        s = self.client.session
        s["access_token"] = token
        s["officer_id"] = officer.user_id_PK
        s["role"] = officer.role
        s.save()
        return session

    def test_verify_accepts_authenticator_code(self):
        officer = self._officer(
            authenticator_secret=generate_authenticator_secret(),
            authenticator_enabled=True,
        )
        self._login(officer)
        code = generate_authenticator_code(officer.authenticator_secret)
        resp = self.client.post(VERIFY_URL, {"otp": code}, REMOTE_ADDR="10.220.0.11")
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertTrue(resp.json()["ok"])

    def test_verify_accepts_backup_code_and_burns(self):
        officer = self._officer(username="zt_backup")
        code = issue_backup_codes(officer)[0]
        self._login(officer)
        resp = self.client.post(VERIFY_URL, {"otp": code}, REMOTE_ADDR="10.220.0.12")
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertEqual(backup_codes_remaining(officer), 9)

    def test_verify_still_revokes_after_repeated_failures(self):
        officer = self._officer(username="zt_bruteforce")
        self._login(officer)
        fifth = None
        for _ in range(5):
            fifth = self.client.post(VERIFY_URL, {"otp": "000000"}, REMOTE_ADDR="10.220.0.13")
        self.assertEqual(fifth.status_code, 401)
        self.assertTrue(fifth.json().get("session_revoked"))

    def test_unlock_accepts_authenticator_code(self):
        from datetime import timedelta

        from django.utils import timezone

        officer = self._officer(
            username="zt_unlock",
            authenticator_secret=generate_authenticator_secret(),
            authenticator_enabled=True,
        )
        session = self._login(officer)
        zt_service.lock_session(session, "idle")
        # Seed two prior unlock failures so unlock escalates to a code
        # (fresh lock — aging it would trip the separate lock-expiry).
        policy = session.session_policy or {}
        policy["zt_unlock_failures"] = 2
        session.session_policy = policy
        session.save(update_fields=["session_policy"])
        code = generate_authenticator_code(officer.authenticator_secret)
        resp = self.client.post(
            UNLOCK_URL, {"otp": code},
            REMOTE_ADDR="10.220.0.14",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertTrue(resp.json()["ok"])

    def test_challenge_push_fallback_when_email_fails(self):
        officer = self._officer(username="zt_challenge")
        self._login(officer)
        with patch("core_system.auth_views.send_mfa_email", return_value=False), \
             patch("core_system.auth_views.send_mfa_push", return_value=True) as mock_push:
            resp = self.client.post(CHALLENGE_URL, REMOTE_ADDR="10.220.0.15")
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        body = resp.json()
        self.assertTrue(body["sent"])
        self.assertEqual(body["delivery"], "push")
        mock_push.assert_called_once()
