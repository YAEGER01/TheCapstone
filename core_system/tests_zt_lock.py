from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from core_system import zt_settings
from core_system.auth_utils import create_access_session, hash_password
from core_system.models import OfficerUser, SystemSetting
from core_system.services import zt_service
from core_system.services.mfa_service import generate_mfa_secret, generate_otp

LIST_URL = "/api/audit/trail/"
STATUS_URL = "/api/auth/zero-trust/status/"
LOCK_URL = "/api/auth/zt/lock/"
HEARTBEAT_URL = "/api/auth/zt/heartbeat/"
UNLOCK_URL = "/api/auth/zt/unlock/"
CHALLENGE_URL = "/api/auth/zero-trust/challenge/"

PASSWORD = "Str0ng!Passw0rd"


class ZeroTrustScreenLockTests(TestCase):
    """Screen lock: server-side flag freezes everything; password unlocks in
    the common case; OTP escalates on risk; failures revoke."""

    def _officer(self, role="President", with_password=True):
        return OfficerUser.objects.create(
            full_name=f"{role} User",
            username=f"{role.lower()}_lock",
            password_hash=hash_password(PASSWORD) if with_password else "unused",
            role=role,
            account_status="Active",
            mfa_enabled=False,
            mfa_secret=generate_mfa_secret(),
            email=f"{role.lower()}_lock@isu.edu.ph",
        )

    def _login(self, officer):
        session, token = create_access_session(
            officer=officer,
            ip_address="127.0.0.1",
            device_info="tests",
        )
        session.trusted_device = True
        session.save()

        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return session

    def _ajax(self, method, url, **extra):
        do = self.client.post if method == "post" else self.client.get
        return do(
            url,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) tests",
            **extra,
        )

    def _lock(self, session):
        zt_service.lock_session(session, "idle")

    # -- the lock freezes everything ------------------------------------

    def test_locked_session_blocks_pages_and_api(self):
        officer = self._officer()
        session = self._login(officer)
        self._lock(session)

        resp = self._ajax("get", LIST_URL)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.headers.get("X-ZT-Session-Locked"), "true")
        self.assertTrue(resp.json()["session_locked"])

        # Even other /api/auth/* endpoints (MFA settings!) stay frozen.
        resp2 = self.client.post(
            "/api/auth/mfa/enable/",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp2.status_code, 403)
        self.assertTrue(resp2.json()["session_locked"])
        officer.refresh_from_db()
        self.assertFalse(officer.mfa_enabled)  # nothing actually happened

    def test_locked_navigation_redirects_to_unlock_page(self):
        officer = self._officer()
        session = self._login(officer)
        self._lock(session)
        resp = self.client.get("/some/page/")
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith("/zt-unlock/"))

    # -- password unlock (the common path) -------------------------------

    def test_unlock_with_correct_password(self):
        officer = self._officer()
        session = self._login(officer)
        self._lock(session)

        resp = self.client.post(
            UNLOCK_URL, {"password": PASSWORD},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["method"], "password")

        session.refresh_from_db()
        self.assertFalse(zt_service.is_locked(session))
        # Life goes on.
        resp2 = self._ajax("get", LIST_URL)
        self.assertEqual(resp2.status_code, 200)

    def test_wrong_password_escalates_to_otp_after_two_failures(self):
        officer = self._officer()
        session = self._login(officer)
        self._lock(session)

        resp1 = self.client.post(
            UNLOCK_URL, {"password": "wrong"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertFalse(resp1.json().get("otp_required", False))

        resp2 = self.client.post(
            UNLOCK_URL, {"password": "wrong"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertTrue(resp2.json()["otp_required"])  # guessing -> OTP now

        # Even the CORRECT password no longer unlocks - OTP is required.
        resp3 = self.client.post(
            UNLOCK_URL, {"password": PASSWORD},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertTrue(resp3.json()["otp_required"])

    def test_five_failures_revoke_session(self):
        officer = self._officer()
        session = self._login(officer)
        self._lock(session)
        # Two wrong passwords escalate to OTP...
        for _ in range(2):
            self.client.post(
                UNLOCK_URL, {"password": "wrong"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
            )
        # ...then three wrong OTPs reach the 5-attempt total -> revoked.
        for _ in range(3):
            resp = self.client.post(
                UNLOCK_URL, {"otp": "000000"},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
            )
        self.assertTrue(resp.json().get("session_revoked"))
        session.refresh_from_db()
        self.assertEqual(session.session_status, "Revoked")

    # -- OTP escalation ---------------------------------------------------

    def test_long_lock_requires_otp_even_with_password(self):
        officer = self._officer()
        session = self._login(officer)
        zt_service.lock_session(session, "idle")
        # Rewind the lock timestamp past the OTP threshold. The auto
        # sign-out (default 5 min) would kill an 11-minute lock first, so
        # raise it for this test to isolate the OTP escalation behavior.
        SystemSetting.objects.update_or_create(
            setting_key="zt_lock_auto_signout_minutes",
            defaults={"setting_value": "120"},
        )
        cache.delete(zt_settings.CACHE_KEY)
        try:
            policy = session.session_policy
            policy["zt_locked_at"] = (timezone.now() - zt_service.ZT_LOCK_OTP_AFTER - timedelta(minutes=1)).isoformat()
            session.save(update_fields=["session_policy"])

            resp = self.client.post(
                UNLOCK_URL, {"password": PASSWORD},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
            )
            self.assertTrue(resp.json()["otp_required"])

            # OTP unlock clears BOTH the lock and a sticky hard check.
            policy = session.session_policy
            policy["zt_level"] = "hard"
            session.save(update_fields=["session_policy"])

            officer.refresh_from_db()
            otp = generate_otp(officer.mfa_secret)
            resp2 = self.client.post(
                UNLOCK_URL, {"otp": otp},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
            )
            self.assertEqual(resp2.status_code, 200)
            session.refresh_from_db()
            self.assertFalse(zt_service.is_locked(session))
            self.assertEqual((session.session_policy or {}).get("zt_level"), "none")
        finally:
            SystemSetting.objects.filter(setting_key="zt_lock_auto_signout_minutes").delete()
            cache.delete(zt_settings.CACHE_KEY)

    def test_no_role_forces_otp_unlock_by_default(self):
        # No role (treasurer included) requires OTP on unlock unless the
        # superadmin opts it back in - a fresh lock unlocks with password.
        for role in ("Treasurer", "Superadmin", "President"):
            officer = self._officer(role=role, with_password=True)
            # Unique usernames per role (helper derives from role only).
            officer.username = f"{role.lower()}_lock_norole"
            officer.email = f"{role.lower()}_lock_norole@isu.edu.ph"
            officer.save(update_fields=["username", "email"])
            session = self._login(officer)
            self._lock(session)

            resp = self.client.post(
                UNLOCK_URL, {"password": PASSWORD},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
            )
            self.assertFalse(
                resp.json().get("otp_required"),
                f"{role} should password-unlock by default",
            )
            self.assertNotIn("role policy", resp.json().get("reasons", []))
            session.refresh_from_db()
            self.assertFalse(zt_service.is_locked(session))

    def test_role_opt_in_restores_otp_unlock(self):
        # The panel can still force a role back to OTP-per-unlock.
        SystemSetting.objects.update_or_create(
            setting_key=zt_settings.ROLES_FIELD,
            defaults={"setting_value": "treasurer"},
        )
        cache.delete(zt_settings.CACHE_KEY)
        try:
            officer = self._officer(role="Treasurer")
            session = self._login(officer)
            self._lock(session)

            resp = self.client.post(
                UNLOCK_URL, {"password": PASSWORD},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
            )
            self.assertTrue(resp.json()["otp_required"])
            self.assertIn("role policy", resp.json().get("reasons", []))
        finally:
            SystemSetting.objects.filter(setting_key=zt_settings.ROLES_FIELD).delete()
            cache.delete(zt_settings.CACHE_KEY)

    # -- heartbeat backstop -------------------------------------------------

    def test_heartbeat_keeps_session_alive(self):
        officer = self._officer()
        session = self._login(officer)
        resp = self.client.post(
            HEARTBEAT_URL, HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertFalse(zt_service.is_locked(session))
        # Normal request still passes.
        self.assertEqual(self._ajax("get", LIST_URL).status_code, 200)

    def test_lost_heartbeat_auto_locks_server_side(self):
        officer = self._officer()
        session = self._login(officer)
        # The page had a heartbeat once, then went quiet - while requests
        # kept flowing (last_activity recent). That is a stripped lock UI.
        policy = session.session_policy or {}
        policy["zt_last_heartbeat"] = (timezone.now() - zt_service.ZT_LOCK_HEARTBEAT_STALE - timedelta(minutes=1)).isoformat()
        session.session_policy = policy
        session.save(update_fields=["session_policy"])

        resp = self._ajax("get", LIST_URL)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.json()["session_locked"])
        session.refresh_from_db()
        self.assertTrue(zt_service.is_locked(session))
        self.assertEqual((session.session_policy or {}).get("zt_lock_reason"), "heartbeat_lost")

    # -- status exposes lock state -------------------------------------------

    def test_status_reports_locked_with_requirements(self):
        officer = self._officer()
        session = self._login(officer)
        self._lock(session)
        resp = self._ajax("get", STATUS_URL)
        data = resp.json()
        self.assertTrue(data["locked"])
        self.assertEqual(data["officer_name"], officer.full_name)
        self.assertFalse(data["unlock"]["otp_required"])  # fresh lock, no failures

        # And the badge/status endpoint keeps answering while locked.
        resp2 = self.client.post(
            LOCK_URL, HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp2.status_code, 200)  # idempotent re-lock is fine


class LockAutoSignoutTests(TestCase):
    """A locked screen that is never unlocked signs the session out after
    the auto sign-out timer (default 5 minutes, superadmin-editable)."""

    def _officer(self, role="President"):
        return OfficerUser.objects.create(
            full_name=f"{role} User",
            username=f"{role.lower()}_signout",
            password_hash=hash_password(PASSWORD),
            role=role,
            account_status="Active",
            mfa_enabled=False,
            mfa_secret=generate_mfa_secret(),
            email=f"{role.lower()}_signout@isu.edu.ph",
        )

    def _login(self, officer):
        session, token = create_access_session(
            officer=officer,
            ip_address="127.0.0.1",
            device_info="tests",
        )
        session.trusted_device = True
        session.save()

        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return session

    def _ajax(self, method, url, **extra):
        do = self.client.post if method == "post" else self.client.get
        return do(
            url,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) tests",
            **extra,
        )

    def _backdate_lock(self, session, minutes):
        policy = session.session_policy or {}
        policy["zt_locked_at"] = (timezone.now() - timedelta(minutes=minutes)).isoformat()
        session.session_policy = policy
        session.save(update_fields=["session_policy"])

    def tearDown(self):
        SystemSetting.objects.filter(setting_key="zt_lock_auto_signout_minutes").delete()
        cache.delete(zt_settings.CACHE_KEY)

    def test_default_auto_signout_is_five_minutes(self):
        self.assertEqual(
            zt_settings.get_zt_timers()["lock_auto_signout"], timedelta(minutes=5)
        )

    def test_fresh_lock_stays_locked(self):
        officer = self._officer()
        session = self._login(officer)
        zt_service.lock_session(session, "idle")

        resp = self._ajax("get", LIST_URL)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.json()["session_locked"])
        session.refresh_from_db()
        self.assertEqual(session.session_status, "Active")

    def test_expired_lock_signs_out_api_calls(self):
        officer = self._officer()
        session = self._login(officer)
        zt_service.lock_session(session, "idle")
        self._backdate_lock(session, 6)

        resp = self._ajax("get", LIST_URL)
        self.assertEqual(resp.status_code, 401)
        self.assertTrue(resp.json()["session_expired"])
        session.refresh_from_db()
        self.assertEqual(session.session_status, "Revoked")
        self.assertFalse(zt_service.is_locked(session))

    def test_expired_lock_redirects_navigation(self):
        officer = self._officer()
        session = self._login(officer)
        zt_service.lock_session(session, "idle")
        self._backdate_lock(session, 6)

        resp = self.client.get("/some/page/")
        self.assertEqual(resp.status_code, 302)
        # Session-death redirects are obfuscated (?x= envelope, no plain flag).
        from urllib.parse import parse_qs, urlsplit
        from core_system.url_obfuscation import opaque_decode
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertIn("x", query)
        self.assertEqual(opaque_decode(query["x"][0]), {"session_expired": "1"})
        session.refresh_from_db()
        self.assertEqual(session.session_status, "Revoked")

    def test_status_reports_signout_times(self):
        officer = self._officer()
        session = self._login(officer)
        zt_service.lock_session(session, "idle")

        resp = self._ajax("get", STATUS_URL)
        data = resp.json()
        self.assertTrue(data["locked"])
        self.assertEqual(data["lock_auto_signout_seconds"], 300)
        self.assertLessEqual(data["lock_expires_in_seconds"], 300)
        self.assertGreater(data["lock_expires_in_seconds"], 0)

    def test_status_revokes_when_expired(self):
        officer = self._officer()
        session = self._login(officer)
        zt_service.lock_session(session, "idle")
        self._backdate_lock(session, 6)

        resp = self._ajax("get", STATUS_URL)
        self.assertEqual(resp.status_code, 401)
        self.assertTrue(resp.json()["session_expired"])
        session.refresh_from_db()
        self.assertEqual(session.session_status, "Revoked")

    def test_unlock_post_revoked_when_expired(self):
        officer = self._officer()
        session = self._login(officer)
        zt_service.lock_session(session, "idle")
        self._backdate_lock(session, 6)

        resp = self.client.post(
            UNLOCK_URL, {"password": PASSWORD},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertTrue(resp.json().get("session_revoked"))
        session.refresh_from_db()
        self.assertEqual(session.session_status, "Revoked")

    def test_unlock_page_redirects_when_expired(self):
        officer = self._officer()
        session = self._login(officer)
        zt_service.lock_session(session, "idle")
        self._backdate_lock(session, 6)

        resp = self.client.get("/zt-unlock/")
        self.assertEqual(resp.status_code, 302)
        # Session-death redirects are obfuscated (?x= envelope, no plain flag).
        from urllib.parse import parse_qs, urlsplit
        from core_system.url_obfuscation import opaque_decode
        query = parse_qs(urlsplit(resp["Location"]).query)
        self.assertIn("x", query)
        self.assertEqual(opaque_decode(query["x"][0]), {"session_expired": "1"})

    def test_custom_timer_is_respected(self):
        SystemSetting.objects.update_or_create(
            setting_key="zt_lock_auto_signout_minutes",
            defaults={"setting_value": "60"},
        )
        cache.delete(zt_settings.CACHE_KEY)

        officer = self._officer()
        session = self._login(officer)
        zt_service.lock_session(session, "idle")
        self._backdate_lock(session, 6)

        # 6 minutes locked, 60-minute timer: still just locked.
        resp = self._ajax("get", LIST_URL)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.json()["session_locked"])

        status = self._ajax("get", STATUS_URL).json()
        self.assertEqual(status["lock_auto_signout_seconds"], 3600)

    def test_superadmin_panel_offers_the_timer(self):
        officer = self._officer(role="Superadmin")
        self._login(officer)
        resp = self.client.get("/superadmin/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('name="zt_lock_auto_signout_minutes"', resp.content.decode())


class ZeroTrustChallengeDeliveryTests(TestCase):
    """The hard-check/unlock OTP email must report its REAL delivery outcome:
    a failed send is immediately retryable (no poisoned cooldown), and only a
    message that actually left the building starts the resend cooldown."""

    def _officer(self, role="President"):
        return OfficerUser.objects.create(
            full_name=f"{role} User",
            username=f"{role.lower()}_challenge",
            password_hash="unused",
            role=role,
            account_status="Active",
            mfa_enabled=False,
            mfa_secret=generate_mfa_secret(),
            email=f"{role.lower()}_challenge@isu.edu.ph",
        )

    def _login(self, officer):
        session, token = create_access_session(
            officer=officer, ip_address="127.0.0.1", device_info="tests",
        )
        session.trusted_device = True
        session.save()
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return session

    def _challenge(self):
        return self.client.post(
            CHALLENGE_URL, HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

    def test_failed_delivery_surfaces_error_and_stays_retryable(self):
        from unittest import mock

        officer = self._officer()
        self._login(officer)

        # Async contract: send_mfa_email returns False only when the message
        # could not even be queued. That is the retryable failure signal —
        # a queued (True) message is delivered by the background nets.
        def failing_send(officer, otp, subject="CAUFA MFA Verification Code", extra_context=None):
            return False

        with mock.patch("core_system.auth_views.send_mfa_email", side_effect=failing_send):
            resp1 = self._challenge()
            self.assertEqual(resp1.status_code, 503)
            body = resp1.json()
            self.assertIn("could not be queued", body["error"])

            # The cooldown must NOT have been poisoned: an immediate resend
            # attempts a new send instead of answering "a code was already sent".
            resp2 = self._challenge()
            self.assertEqual(resp2.status_code, 503)
            self.assertIn("could not be queued", resp2.json()["error"])

    def test_successful_delivery_starts_cooldown(self):
        from unittest import mock
        from core_system.models import OutgoingEmail

        officer = self._officer()
        self._login(officer)

        def working_send(officer, otp, subject="CAUFA MFA Verification Code", extra_context=None):
            OutgoingEmail.objects.create(
                recipient_list=[officer.email],
                subject=subject,
                html_template="emails/mfa_challenge.html",
                context=extra_context or {},
                status=OutgoingEmail.SENT,
            )
            return True

        with mock.patch("core_system.auth_views.send_mfa_email", side_effect=working_send):
            resp1 = self._challenge()
            self.assertEqual(resp1.status_code, 200)
            self.assertTrue(resp1.json()["sent"])
            # Fully async: the response reports queued, background nets deliver.
            self.assertEqual(resp1.json()["delivery"], "queued")

            resp2 = self._challenge()
            self.assertTrue(resp2.json()["ok"])
            self.assertFalse(resp2.json()["sent"])  # rate-limited: code already delivered


class LockoutSurvivalTests(TestCase):
    """Lockouts must not kill the session out from under a returning officer.

    Root cause these guard against: while locked, only exempt /api/auth/*
    endpoints answer, which never refresh last_activity_at - so the idle
    clock froze at lock time and the FIRST data request after a successful
    unlock triggered the hard idle logout."""

    LIST_URL = "/api/audit/trail/"

    def _officer(self):
        return OfficerUser.objects.create(
            full_name="President User",
            username="lock_survival",
            password_hash=hash_password(PASSWORD),
            role="President",
            account_status="Active",
            mfa_enabled=False,
            mfa_secret=generate_mfa_secret(),
            email="lock_survival@isu.edu.ph",
        )

    def _login(self, officer):
        session, token = create_access_session(
            officer=officer,
            ip_address="127.0.0.1",
            device_info="tests",
        )
        session.trusted_device = True
        session.save()

        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return session

    def _lock(self, session):
        zt_service.lock_session(session, "idle")

    def _ajax(self, method, url, **extra):
        return self.client.get(
            url,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
            HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) tests",
            **extra,
        )

    def _officer_and_login(self):
        officer = self._officer()
        session = self._login(officer)
        return officer, session

    def test_unlock_after_long_lockout_then_data_loads(self):
        officer, session = self._officer_and_login()
        self._lock(session)
        # Simulate a lockout far past the 30-minute idle kill.
        from core_system.models import AccessSession
        AccessSession.objects.filter(pk=session.pk).update(
            last_activity_at=timezone.now() - timedelta(minutes=75)
        )

        resp = self.client.post(
            UNLOCK_URL, {"password": PASSWORD},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

        # The session must survive: data loads right after unlocking.
        data_resp = self._ajax("get", self.LIST_URL)
        self.assertEqual(data_resp.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.session_status, "Active")

    def test_failed_unlock_attempt_refreshes_activity_without_unlocking(self):
        officer, session = self._officer_and_login()
        self._lock(session)
        from core_system.models import AccessSession
        AccessSession.objects.filter(pk=session.pk).update(
            last_activity_at=timezone.now() - timedelta(minutes=75)
        )

        resp = self.client.post(
            UNLOCK_URL, {"password": "wrong"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest", HTTP_ACCEPT="application/json",
        )
        self.assertEqual(resp.status_code, 403)

        # Still locked (only 1 failure) but the idle clock moved: the
        # session is neither idle-killed nor revoked.
        session.refresh_from_db()
        self.assertEqual(session.session_status, "Active")
        self.assertTrue(zt_service.is_locked(session))
        self.assertLess(timezone.now() - session.last_activity_at, timedelta(minutes=1))

        # And the unlock page itself also counts as interaction.
        page = self.client.get("/zt-unlock/")
        self.assertEqual(page.status_code, 200)
        session.refresh_from_db()
        self.assertLess(timezone.now() - session.last_activity_at, timedelta(minutes=1))


class MfaDeliveryStatusTests(TestCase):
    """MFA pages show the REAL queue status; Resend bypasses the 5-minute
    rate limit when the last code FAILED instead of arriving."""

    STATUS_URL = "/api/auth/mfa/status/"
    RESEND_URL = "/api/auth/mfa/challenge/"

    def _officer(self):
        return OfficerUser.objects.create(
            full_name="MFA User",
            username="mfa_status_user",
            password_hash=hash_password(PASSWORD),
            role="President",
            account_status="Active",
            mfa_enabled=False,
            mfa_secret=generate_mfa_secret(),
            email="mfa_status@isu.edu.ph",
        )

    def _pre_auth(self, officer):
        session = self.client.session
        session["mfa_pre_auth_token"] = "tok123"
        session["mfa_officer_id"] = officer.user_id_PK
        session["mfa_username"] = officer.username
        session["mfa_initiated_at"] = timezone.now().isoformat()
        session.save()

    def _backdate_row(self, row, minutes):
        from core_system.models import OutgoingEmail
        OutgoingEmail.objects.filter(pk=row.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes)
        )
        row.refresh_from_db()
        return row

    def _otp_row(self, officer, status):
        from core_system.models import OutgoingEmail
        return OutgoingEmail.objects.create(
            recipient_list=[officer.email],
            subject="CAUFA MFA Verification Code",
            html_template="emails/mfa_challenge.html",
            context={},
            status=status,
        )

    def test_status_404_without_pre_auth_session(self):
        resp = self.client.get(self.STATUS_URL)
        self.assertEqual(resp.status_code, 404)

    def test_status_reports_sent(self):
        from core_system.models import OutgoingEmail
        officer = self._officer()
        self._pre_auth(officer)
        self._otp_row(officer, OutgoingEmail.SENT)
        resp = self.client.get(self.STATUS_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["delivery"], "sent")

    def test_status_reports_sending_when_pending(self):
        from core_system.models import OutgoingEmail
        officer = self._officer()
        self._pre_auth(officer)
        self._otp_row(officer, OutgoingEmail.PENDING)
        resp = self.client.get(self.STATUS_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["delivery"], "sending")

    def test_status_reports_failed(self):
        from core_system.models import OutgoingEmail
        officer = self._officer()
        self._pre_auth(officer)
        self._otp_row(officer, OutgoingEmail.FAILED)
        resp = self.client.get(self.STATUS_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["delivery"], "failed")

    def test_status_never_reports_stale_row_as_sent(self):
        # The trap: 2nd login inside the rate window queues nothing, and the
        # poll must NOT present the 1st login's SENT row as this attempt's.
        from core_system.models import OutgoingEmail
        officer = self._officer()
        row = self._otp_row(officer, OutgoingEmail.SENT)
        self._backdate_row(row, minutes=10)
        self._pre_auth(officer)  # fresh attempt, nothing queued by it
        resp = self.client.get(self.STATUS_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["delivery"], "rate_limited")

    def test_resend_bypassed_when_last_code_failed(self):
        from unittest import mock
        from core_system.models import OutgoingEmail
        officer = self._officer()
        officer.last_mfa_email_sent_at = timezone.now()
        officer.save(update_fields=["last_mfa_email_sent_at"])
        self._pre_auth(officer)
        self._otp_row(officer, OutgoingEmail.FAILED)
        with mock.patch(
            "core_system.auth_views.send_mfa_email", return_value=True
        ):
            resp = self.client.post(
                self.RESEND_URL, {"username": officer.username}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_resend_still_limited_when_last_code_pending(self):
        from unittest import mock
        from core_system.models import OutgoingEmail
        officer = self._officer()
        officer.last_mfa_email_sent_at = timezone.now()
        officer.save(update_fields=["last_mfa_email_sent_at"])
        self._pre_auth(officer)
        self._otp_row(officer, OutgoingEmail.PENDING)
        with mock.patch(
            "core_system.auth_views.send_mfa_email", return_value=True
        ) as mocked:
            resp = self.client.post(
                self.RESEND_URL, {"username": officer.username}
            )
        self.assertEqual(resp.status_code, 429)
        mocked.assert_not_called()

    def test_resend_allowed_when_pending_row_stalled(self):
        from unittest import mock
        from core_system.models import OutgoingEmail
        officer = self._officer()
        officer.last_mfa_email_sent_at = timezone.now()
        officer.save(update_fields=["last_mfa_email_sent_at"])
        self._pre_auth(officer)
        row = self._otp_row(officer, OutgoingEmail.PENDING)
        self._backdate_row(row, minutes=5)  # worker died long ago
        with mock.patch(
            "core_system.auth_views.send_mfa_email", return_value=True
        ):
            resp = self.client.post(
                self.RESEND_URL, {"username": officer.username}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_resend_limited_when_code_just_sent(self):
        from unittest import mock
        from core_system.models import OutgoingEmail
        officer = self._officer()
        self._pre_auth(officer)
        self._otp_row(officer, OutgoingEmail.SENT)  # seconds old
        with mock.patch(
            "core_system.auth_views.send_mfa_email", return_value=True
        ) as mocked:
            resp = self.client.post(
                self.RESEND_URL, {"username": officer.username}
            )
        self.assertEqual(resp.status_code, 429)
        mocked.assert_not_called()

    def test_resend_allowed_when_sent_row_old(self):
        from unittest import mock
        from core_system.models import OutgoingEmail
        officer = self._officer()
        self._pre_auth(officer)
        row = self._otp_row(officer, OutgoingEmail.SENT)
        self._backdate_row(row, minutes=5)
        with mock.patch(
            "core_system.auth_views.send_mfa_email", return_value=True
        ):
            resp = self.client.post(
                self.RESEND_URL, {"username": officer.username}
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
