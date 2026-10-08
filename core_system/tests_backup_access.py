"""Standalone backup codes, first-login reveal, and nudge status tests."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core_system.services.mfa_service import (
    backup_codes_remaining,
    generate_authenticator_secret,
    generate_backup_codes,
    generate_mfa_secret,
    generate_otp,
    hash_backup_code,
)


class BackupIssueTests(TestCase):
    def _officer(self, **kw):
        from core_system.models import OfficerUser

        defaults = dict(
            full_name="Codes Officer",
            username="codes_officer",
            password_hash="x",
            role="treasurer",
            account_status="active",
            email="codes@example.com",
            mfa_secret=generate_mfa_secret(),
        )
        defaults.update(kw)
        return OfficerUser.objects.create(**defaults)

    def _login_as(self, officer):
        session = self.client.session
        session["officer_id"] = officer.user_id_PK
        session.save()

    def test_standalone_issue_without_authenticator(self):
        officer = self._officer()
        self._login_as(officer)
        resp = self.client.post("/api/auth/backup-codes/issue/")
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        codes = resp.json()["backup_codes"]
        self.assertEqual(len(codes), 10)
        self.assertEqual(backup_codes_remaining(officer), 10)
        officer.refresh_from_db()
        self.assertIsNotNone(officer.backup_codes_issued_at)

    def test_issue_requires_replace_confirm(self):
        officer = self._officer()
        self._login_as(officer)
        first = self.client.post("/api/auth/backup-codes/issue/").json()["backup_codes"]
        resp = self.client.post("/api/auth/backup-codes/issue/")
        self.assertEqual(resp.status_code, 409)
        self.assertTrue(resp.json()["needs_replace_confirm"])
        # Old code still valid (not wiped by the refused request).
        from core_system.models import MfaBackupCode
        self.assertTrue(
            MfaBackupCode.objects.filter(officer_id_FK=officer, used_at__isnull=True).exists()
        )
        resp2 = self.client.post("/api/auth/backup-codes/issue/", {"replace": "true"})
        self.assertEqual(resp2.status_code, 200)
        second = resp2.json()["backup_codes"]
        self.assertNotEqual(set(first), set(second))

    def test_standalone_code_logs_in(self):
        from core_system.services.mfa_service import generate_mfa_secret  # noqa

        officer = self._officer(username="codes_login")
        self._login_as(officer)
        code = self.client.post("/api/auth/backup-codes/issue/").json()["backup_codes"][0]
        # Spend it through the real pre-auth verify path.
        session = self.client.session
        session["mfa_pre_auth_token"] = "tok9"
        session["mfa_officer_id"] = officer.user_id_PK
        session["mfa_username"] = officer.username
        session.save()
        resp = self.client.post("/api/auth/mfa/verify/", {"otp": code, "pre_auth_token": "tok9"})
        self.assertEqual(resp.status_code, 200, resp.content[:300])


class BackupRevealTests(TestCase):
    def _officer(self, **kw):
        from core_system.models import OfficerUser

        defaults = dict(
            full_name="Reveal Officer",
            username="reveal_officer",
            password_hash="x",
            role="member",
            account_status="active",
            email="reveal@example.com",
            mfa_secret=generate_mfa_secret(),
        )
        defaults.update(kw)
        return OfficerUser.objects.create(**defaults)

    def _fresh_session(self, officer, issued_ago_minutes=0):
        from core_system.auth_utils import create_access_session

        sess, token = create_access_session(
            officer=officer, ip_address="127.0.0.1", device_info="t",
        )
        if issued_ago_minutes:
            sess.issued_at = timezone.now() - timedelta(minutes=issued_ago_minutes)
            sess.save(update_fields=["issued_at"])
        s = self.client.session
        s["access_token"] = token
        s["officer_id"] = officer.user_id_PK
        s["pending_backup_reveal"] = ["AAAA-1111", "BBBB-2222"]
        s["show_backup_modal"] = True
        s.save()
        return token

    def test_reveal_once_then_gone(self):
        officer = self._officer()
        self._fresh_session(officer)
        first = self.client.get("/api/auth/backup-codes/reveal/")
        self.assertEqual(first.status_code, 200, first.content[:300])
        self.assertEqual(first.json()["backup_codes"], ["AAAA-1111", "BBBB-2222"])
        second = self.client.get("/api/auth/backup-codes/reveal/")
        self.assertEqual(second.status_code, 410)
        self.assertTrue(second.json()["gone"])

    def test_reveal_refuses_stale_login(self):
        officer = self._officer(username="reveal_stale")
        self._fresh_session(officer, issued_ago_minutes=60)
        resp = self.client.get("/api/auth/backup-codes/reveal/")
        self.assertEqual(resp.status_code, 410)

    def test_reveal_requires_auth(self):
        resp = self.client.get("/api/auth/backup-codes/reveal/")
        self.assertEqual(resp.status_code, 401)


class FirstLoginAutoIssueTests(TestCase):
    def test_member_first_login_issues_and_flags_modal(self):
        from datetime import date

        from core_system.models import Member, MfaBackupCode, OfficerUser

        officer = OfficerUser.objects.create(
            full_name="First Member",
            username="first_member",
            password_hash="x",
            role="member",
            account_status="active",
            email="first@example.com",
            mfa_secret=generate_mfa_secret(),
        )
        Member.objects.create(
            full_name="First Member",
            employee_id="EMP-0001",
            officer_user_id_FK=officer,
            employment_status="Active",
            membership_status="Active",
            date_joined=date(2024, 1, 1),
        )
        session = self.client.session
        session["mfa_pre_auth_token"] = "tok7"
        session["mfa_officer_id"] = officer.user_id_PK
        session["mfa_username"] = officer.username
        session.save()
        code = generate_otp(officer.mfa_secret)
        resp = self.client.post("/api/auth/mfa/verify/", {"otp": code, "pre_auth_token": "tok7"})
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertEqual(
            MfaBackupCode.objects.filter(officer_id_FK=officer, used_at__isnull=True).count(), 10
        )
        session = self.client.session
        self.assertTrue(session.get("show_backup_modal"))
        self.assertEqual(len(session.get("pending_backup_reveal") or []), 10)

    def test_second_login_does_not_reissue(self):
        from datetime import date

        from core_system.models import Member, MfaBackupCode, OfficerUser

        officer = OfficerUser.objects.create(
            full_name="Second Member",
            username="second_member",
            password_hash="x",
            role="member",
            account_status="active",
            email="second@example.com",
            mfa_secret=generate_mfa_secret(),
        )
        Member.objects.create(
            full_name="Second Member",
            employee_id="EMP-0002",
            officer_user_id_FK=officer,
            employment_status="Active",
            membership_status="Active",
            date_joined=date(2024, 1, 1),
        )
        for tok in ("tokA", "tokB"):
            session = self.client.session
            session["mfa_pre_auth_token"] = tok
            session["mfa_officer_id"] = officer.user_id_PK
            session["mfa_username"] = officer.username
            session.save()
            code = generate_otp(officer.mfa_secret)
            resp = self.client.post("/api/auth/mfa/verify/", {"otp": code, "pre_auth_token": tok})
            self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertEqual(
            MfaBackupCode.objects.filter(officer_id_FK=officer).count(), 10
        )


class BackupStatusTests(TestCase):
    def test_nudge_status_transitions(self):
        from core_system.models import OfficerUser

        officer = OfficerUser.objects.create(
            full_name="Nudge Officer",
            username="nudge_officer",
            password_hash="x",
            role="treasurer",
            account_status="active",
            email="nudge@example.com",
            mfa_secret=generate_mfa_secret(),
        )
        session = self.client.session
        session["officer_id"] = officer.user_id_PK
        session.save()
        self.assertTrue(self.client.get("/api/auth/backup-status/").json()["needs_fallback"])
        self.client.post("/api/auth/backup-codes/issue/")
        status = self.client.get("/api/auth/backup-status/").json()
        self.assertFalse(status["needs_fallback"])
        self.assertEqual(status["backup_remaining"], 10)


class ResetPasswordHardeningTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def _officer(self, **kw):
        from core_system.models import OfficerUser

        defaults = dict(
            full_name="Reset Officer",
            username="reset_officer",
            password_hash="x",
            role="member",
            account_status="active",
            email="reset@example.com",
            mfa_secret=generate_mfa_secret(),
        )
        defaults.update(kw)
        return OfficerUser.objects.create(**defaults)

    def _arm_reset(self, officer, otp="123456"):
        from django.utils import timezone
        session = self.client.session
        session["reset_email"] = officer.email
        session["reset_officer_id"] = officer.user_id_PK
        session["reset_otp"] = otp
        session["reset_otp_created_at"] = timezone.now().isoformat()
        session.save()

    def _post_reset(self, code, ip="10.210.0.21"):
        return self.client.post("/reset-password/", {
            "otp": code,
            "new_password": "NewPass1!",
            "confirm_password": "NewPass1!",
        }, REMOTE_ADDR=ip)

    def test_email_otp_still_resets(self):
        from core_system.auth_utils import verify_password

        officer = self._officer()
        self._arm_reset(officer)
        resp = self._post_reset("123456")
        self.assertEqual(resp.status_code, 302, resp.content[:300])
        officer.refresh_from_db()
        self.assertTrue(verify_password("NewPass1!", officer.password_hash))

    def test_backup_code_resets_and_burns(self):
        from core_system.auth_utils import verify_password
        from core_system.services.mfa_service import issue_backup_codes

        officer = self._officer(username="reset_via_backup")
        code = issue_backup_codes(officer)[0]
        self._arm_reset(officer)
        resp = self._post_reset(code, ip="10.210.0.22")
        self.assertEqual(resp.status_code, 302, resp.content[:300])
        officer.refresh_from_db()
        self.assertTrue(verify_password("NewPass1!", officer.password_hash))
        self.assertEqual(backup_codes_remaining(officer), 9)

    def test_wrong_codes_count_down_then_lock(self):
        officer = self._officer(username="reset_throttled")
        self._arm_reset(officer)
        for i in range(9):
            resp = self._post_reset(f"bad{i:02d}", ip="10.210.0.23")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("attempt(s) left", resp.content.decode())
        resp = self._post_reset("badlast", ip="10.210.0.23")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Too many wrong codes", content)
        # Reset state wiped: the real code no longer works.
        resp2 = self._post_reset("123456", ip="10.210.0.23")
        self.assertIn("expired", resp2.content.decode().lower())

    def test_reset_revokes_live_sessions(self):
        from core_system.auth_utils import create_access_session
        from core_system.models import AccessSession

        officer = self._officer(username="reset_revokes")
        create_access_session(officer=officer, ip_address="127.0.0.1", device_info="t")
        self.assertTrue(
            AccessSession.objects.filter(user_id_FK=officer, revoked_at__isnull=True).exists()
        )
        self._arm_reset(officer)
        self._post_reset("123456", ip="10.210.0.24")
        self.assertFalse(
            AccessSession.objects.filter(user_id_FK=officer, revoked_at__isnull=True).exists()
        )
