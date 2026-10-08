"""OTP fallback tests: authenticator TOTP, backup codes, push fallback endpoint.

- Pure crypto tests need no DB.
- View tests use Django TestCase (MySQL test DB) with a live pre-auth session.
"""
import time

from django.test import TestCase

from core_system.services.mfa_service import (
    authenticator_otpauth_uri,
    backup_code_matches,
    format_manual_key,
    generate_authenticator_code,
    generate_authenticator_secret,
    generate_backup_codes,
    generate_otp,
    hash_backup_code,
    verify_authenticator_code,
    verify_otp,
)


# RFC 6238 Appendix B vector: SHA-1, secret "12345678901234567890".
RFC_SECRET_B32 = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


class AuthenticatorTotpTests(TestCase):
    def test_rfc6238_vector(self):
        # T=59s -> counter 1 -> 8-digit 94287082 -> 6-digit 287082.
        self.assertEqual(generate_authenticator_code(RFC_SECRET_B32, for_time=59), "287082")

    def test_roundtrip_current_code(self):
        secret = generate_authenticator_secret()
        self.assertTrue(verify_authenticator_code(secret, generate_authenticator_code(secret)))

    def test_rejects_wrong_and_malformed(self):
        secret = generate_authenticator_secret()
        self.assertFalse(verify_authenticator_code(secret, "000000"))
        self.assertFalse(verify_authenticator_code(secret, "abcdef"))
        self.assertFalse(verify_authenticator_code(secret, "12345"))
        self.assertFalse(verify_authenticator_code(secret, ""))
        self.assertFalse(verify_authenticator_code("", "123456"))
        self.assertFalse(verify_authenticator_code(None, "123456"))

    def test_accepts_adjacent_step(self):
        # ±30s clock skew tolerance: previous step's code still verifies.
        secret = generate_authenticator_secret()
        prev = generate_authenticator_code(secret, for_time=time.time() - 30)
        self.assertTrue(verify_authenticator_code(secret, prev))

    def test_otpauth_uri_and_manual_key(self):
        secret = generate_authenticator_secret()
        uri = authenticator_otpauth_uri(secret, "officer@example.com")
        self.assertIn("otpauth://totp/", uri)
        self.assertIn(secret, uri)
        self.assertIn("period=30", uri)
        key = format_manual_key(secret)
        self.assertEqual(key.replace(" ", "").upper(), secret)


class BackupCodeTests(TestCase):
    def test_format_and_hash_roundtrip(self):
        codes = generate_backup_codes()
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        for code in codes:
            self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
            self.assertTrue(backup_code_matches(code, hash_backup_code(code)))
            # Case / separator insensitive.
            self.assertTrue(backup_code_matches(code.lower().replace("-", " "), hash_backup_code(code)))

    def test_mismatch(self):
        code = generate_backup_codes(count=1)[0]
        self.assertFalse(backup_code_matches("ZZZZ-ZZZZ", hash_backup_code(code)))


class EmailTotpUntouchedTests(TestCase):
    def test_existing_email_totp_still_roundtrips(self):
        secret = "deadbeef" * 8
        code = generate_otp(secret)
        self.assertRegex(code, r"^\d{6}$")
        self.assertTrue(verify_otp(secret, code))
        self.assertFalse(verify_otp(secret, "000000"))


class MfaVerifyThrottleTests(TestCase):
    # NOTE: OTP failures feed the shared login throttle (per-principal AND
    # per-IP). Each test uses a unique REMOTE_ADDR so counters never leak
    # into other test classes running in the same process.
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def _make_officer(self, **kw):
        from core_system.models import OfficerUser
        from core_system.services.mfa_service import generate_mfa_secret

        defaults = dict(
            full_name="Throttle Officer",
            username="throttle_officer",
            password_hash="x",
            role="treasurer",
            account_status="active",
            email="throttle@example.com",
            mfa_secret=generate_mfa_secret(),
        )
        defaults.update(kw)
        return OfficerUser.objects.create(**defaults)

    def _pre_auth(self, officer, token="tokT"):
        session = self.client.session
        session["mfa_pre_auth_token"] = token
        session["mfa_officer_id"] = officer.user_id_PK
        session["mfa_username"] = officer.username
        session.save()
        return token

    def _wrong(self, token, code="000000", ip="10.200.0.11"):
        return self.client.post(
            "/api/auth/mfa/verify/",
            {"otp": code, "pre_auth_token": token},
            REMOTE_ADDR=ip,
        )

    def test_attempts_left_counts_down_then_locks_out(self):
        from core_system.auth_views import MAX_MFA_ATTEMPTS

        officer = self._make_officer()
        token = self._pre_auth(officer)
        for i in range(1, MAX_MFA_ATTEMPTS):
            resp = self._wrong(token, f"{i:06d}")
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.json()["attempts_left"], MAX_MFA_ATTEMPTS - i)
        resp = self._wrong(token, "999999")
        self.assertEqual(resp.status_code, 429)
        self.assertTrue(resp.json()["locked_out"])
        # Pre-auth state is dead: even the right code is rejected as no-session.
        from core_system.services.mfa_service import generate_otp
        resp2 = self.client.post("/api/auth/mfa/verify/", {
            "otp": generate_otp(officer.mfa_secret), "pre_auth_token": token,
        })
        self.assertEqual(resp2.status_code, 400)

    def test_correct_code_still_works_after_a_few_failures(self):
        from core_system.services.mfa_service import generate_otp

        officer = self._make_officer(username="throttle_ok")
        token = self._pre_auth(officer)
        self._wrong(token, "111111", ip="10.200.0.12")
        self._wrong(token, "222222", ip="10.200.0.12")
        resp = self.client.post("/api/auth/mfa/verify/", {
            "otp": generate_otp(officer.mfa_secret), "pre_auth_token": token,
        }, REMOTE_ADDR="10.200.0.12")
        self.assertEqual(resp.status_code, 200, resp.content[:300])

    def test_failures_feed_shared_login_throttle(self):
        from core_system.login_throttle import check_throttle

        officer = self._make_officer(username="throttle_shared")
        token = self._pre_auth(officer)
        for i in range(5):
            self._wrong(token, f"{i:06d}", ip="10.200.0.13")
        locked, _reason, _retry = check_throttle(officer.username, "10.200.0.13")
        self.assertTrue(locked)


class MfaFallbackViewTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def _make_officer(self, **kw):
        from core_system.models import OfficerUser

        defaults = dict(
            full_name="Fallback Officer",
            username="fallback_officer",
            password_hash="x",
            role="treasurer",
            account_status="active",
            email="fallback@example.com",
        )
        defaults.update(kw)
        return OfficerUser.objects.create(**defaults)

    def _pre_auth(self, officer):
        session = self.client.session
        session["mfa_pre_auth_token"] = "tok123"
        session["mfa_officer_id"] = officer.user_id_PK
        session["mfa_username"] = officer.username
        session["mfa_email_masked"] = "f***@example.com"
        session.save()

    def test_verify_accepts_authenticator_code(self):
        from core_system.services.mfa_service import generate_mfa_secret

        officer = self._make_officer(
            mfa_secret=generate_mfa_secret(),
            authenticator_secret=generate_authenticator_secret(),
            authenticator_enabled=True,
        )
        self._pre_auth(officer)
        code = generate_authenticator_code(officer.authenticator_secret)
        resp = self.client.post("/api/auth/mfa/verify/", {"otp": code, "pre_auth_token": "tok123"})
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertTrue(resp.json()["ok"])

    def test_verify_accepts_backup_code_once(self):
        from core_system.models import MfaBackupCode
        from core_system.services.mfa_service import generate_mfa_secret

        officer = self._make_officer(mfa_secret=generate_mfa_secret())
        code = generate_backup_codes(count=1)[0]
        MfaBackupCode.objects.create(officer_id_FK=officer, code_hash=hash_backup_code(code))

        self._pre_auth(officer)
        resp = self.client.post("/api/auth/mfa/verify/", {"otp": code, "pre_auth_token": "tok123"})
        self.assertEqual(resp.status_code, 200, resp.content[:300])

        # Burned: second use fails (re-arm pre-auth state first).
        self._pre_auth(officer)
        resp2 = self.client.post("/api/auth/mfa/verify/", {"otp": code, "pre_auth_token": "tok123"})
        self.assertEqual(resp2.status_code, 401)

    def test_push_fallback_without_device_reports_no_push(self):
        from core_system.services.mfa_service import generate_mfa_secret

        officer = self._make_officer(username="fallback_nopush", mfa_secret=generate_mfa_secret())
        self._pre_auth(officer)
        resp = self.client.post("/api/auth/mfa/push/", {"pre_auth_token": "tok123"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["has_push"])
