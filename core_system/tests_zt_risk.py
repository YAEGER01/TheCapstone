from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core_system.auth_utils import create_access_session
from core_system.models import OfficerUser
from core_system.services.mfa_service import generate_mfa_secret, generate_otp
from core_system.services import zt_service

LIST_URL = "/api/audit/trail/"
STATUS_URL = "/api/auth/zero-trust/status/"
CHALLENGE_URL = "/api/auth/zero-trust/challenge/"
VERIFY_URL = "/api/auth/zero-trust/verify/"

CHROME_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
FIREFOX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"


class ZeroTrustRiskTests(TestCase):
    """Three-tier Zero Trust: soft rebind, medium notify, hard OTP challenge."""

    def _officer(self, role="President"):
        return OfficerUser.objects.create(
            full_name=f"{role} User",
            username=f"{role.lower()}_zt",
            password_hash="unused",
            role=role,
            account_status="Active",
            mfa_enabled=False,
            mfa_secret=generate_mfa_secret(),
            email=f"{role.lower()}_zt@isu.edu.ph",
        )

    def _login(self, officer, ua=CHROME_UA):
        """Create a trusted session whose baseline matches the given UA/IP."""
        session, token = create_access_session(
            officer=officer,
            ip_address="127.0.0.1",
            device_info=ua,
        )
        session.trusted_device = True
        session.save()
        # First request bootstraps the snapshot; make it deterministic here.
        policy = session.session_policy or {}
        policy["zt_snapshot"] = {
            "ua_family": "Chrome",
            "ua_platform": "Windows NT 10.0",
            "lang": "en",
            "ip": "127.0.0.1",
            "ip_net": "127.0.0",
            "ts": timezone.now().isoformat(),
        }
        policy["zt_ip_baseline"] = "127.0.0"
        policy["zt_env_baseline"] = {}
        session.session_policy = policy
        session.save(update_fields=["session_policy"])

        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return session

    def _get(self, url=LIST_URL, ua=CHROME_UA, **extra):
        return self.client.get(
            url,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_USER_AGENT=ua,
            HTTP_ACCEPT="application/json",
            **extra,
        )

    # -- baseline -------------------------------------------------------

    def test_matching_environment_passes_and_bootstraps_nothing(self):
        officer = self._officer()
        session = self._login(officer)
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertNotEqual((session.session_policy or {}).get("zt_level"), "hard")

    # -- hard: device binding ------------------------------------------

    def test_browser_change_requires_hard_check(self):
        officer = self._officer()
        self._login(officer)
        resp = self._get(ua=FIREFOX_UA)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.headers.get("X-Zero-Trust-Challenge"), "true")
        data = resp.json()
        self.assertTrue(data["zero_trust_challenge"])
        self.assertEqual(data["level"], "hard")

    def test_hard_check_sticky_until_verified(self):
        officer = self._officer()
        session = self._login(officer)
        # Trip the hard check...
        self._get(ua=FIREFOX_UA)
        # ...then come back with the original browser: still blocked.
        resp = self._get()
        self.assertEqual(resp.status_code, 403)

        # Verify with a valid TOTP code and the block lifts.
        officer.refresh_from_db()
        otp = generate_otp(officer.mfa_secret)
        resp = self.client.post(
            VERIFY_URL,
            {"otp": otp},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_USER_AGENT=FIREFOX_UA,
        )
        self.assertEqual(resp.status_code, 200)
        resp = self._get(ua=FIREFOX_UA)
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertEqual((session.session_policy or {}).get("zt_level"), "none")

    # -- network drift: debounced "Is this you?" lockout -------------------

    def test_network_change_arms_then_locks_on_persist(self):
        # First sighting of a new network only arms a candidate: no block,
        # no medium noise (single blips never punish the officer).
        officer = self._officer()
        session = self._login(officer)
        resp = self.client.get(
            LIST_URL,
            REMOTE_ADDR="10.9.9.9",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_USER_AGENT=CHROME_UA,
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.headers.get("X-Zero-Trust-Level"))
        # Flapping straight back disarms silently.
        resp2 = self.client.get(
            LIST_URL,
            REMOTE_ADDR="127.0.0.1",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_USER_AGENT=CHROME_UA,
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp2.status_code, 200)
        # ...but a network that is STILL new past the stability window locks
        # the screen with the "Is this you?" password prompt.
        from core_system.models import AccessSession

        session.refresh_from_db()
        policy = dict(session.session_policy or {})
        policy["zt_net_candidate"] = {
            "from_net": policy.get("zt_ip_baseline"),
            "to_net": "10.9.9",
            "first_seen": (timezone.now() - timedelta(seconds=120)).isoformat(),
            "confirms": 1,
        }
        AccessSession.objects.filter(pk=session.pk).update(session_policy=policy)
        resp3 = self.client.get(
            LIST_URL,
            REMOTE_ADDR="10.9.9.9",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_USER_AGENT=CHROME_UA,
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp3.status_code, 403)
        self.assertTrue(resp3.json().get("session_locked"))
        session.refresh_from_db()
        from core_system.services import zt_service

        self.assertTrue(zt_service.is_locked(session))
        self.assertIn("Is this you?", zt_service.lock_note(session))

    # -- medium: idle tier ----------------------------------------------

    def test_long_idle_prompts_medium_check(self):
        officer = self._officer()
        session = self._login(officer)
        from core_system.models import AccessSession

        AccessSession.objects.filter(pk=session.pk).update(
            last_activity_at=timezone.now() - timedelta(minutes=18)
        )
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Zero-Trust-Level"), "medium")

    # -- hard: suspicious-activity escalation ---------------------------

    def test_security_events_escalate_to_hard(self):
        officer = self._officer()
        session = self._login(officer)
        policy = session.session_policy or {}
        policy["zt_sec_events"] = [
            [ (timezone.now() - timedelta(minutes=1)).isoformat(), "role_denied" ]
            for _ in range(zt_service.ZT_SEC_HARD)
        ]
        session.session_policy = policy
        session.save(update_fields=["session_policy"])
        resp = self._get()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["level"], "hard")

    # -- status + challenge endpoints ------------------------------------

    def test_status_reports_level_and_fingerprint(self):
        officer = self._officer()
        self._login(officer)
        resp = self._get(url=STATUS_URL)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("fingerprint", data)
        self.assertIn("level", data)

    def test_challenge_rate_limited_then_verify_clears_hard(self):
        officer = self._officer()
        self._login(officer)
        self._get(ua=FIREFOX_UA)  # hard

        resp = self.client.post(
            CHALLENGE_URL, HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_USER_AGENT=FIREFOX_UA
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["sent"])

        # Second send inside the cooldown must not email again.
        resp2 = self.client.post(
            CHALLENGE_URL, HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_USER_AGENT=FIREFOX_UA
        )
        self.assertTrue(resp2.json()["ok"])
        self.assertFalse(resp2.json()["sent"])

        officer.refresh_from_db()
        otp = generate_otp(officer.mfa_secret)
        resp3 = self.client.post(
            VERIFY_URL,
            {"otp": otp},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_USER_AGENT=FIREFOX_UA,
        )
        self.assertEqual(resp3.status_code, 200)
        self.assertTrue(resp3.json()["ok"])

    def test_verify_locks_session_after_repeated_failures(self):
        officer = self._officer()
        session = self._login(officer)
        self._get(ua=FIREFOX_UA)  # hard
        for _ in range(5):
            resp = self.client.post(
                VERIFY_URL,
                {"otp": "000000"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                HTTP_USER_AGENT=FIREFOX_UA,
            )
        self.assertTrue(resp.json().get("session_revoked"))
        session.refresh_from_db()
        self.assertEqual(session.session_status, "Revoked")
