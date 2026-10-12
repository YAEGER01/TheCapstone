"""Tests for the offline personal action-PIN (all roles)."""

import json

from django.test import TestCase
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system import officer_pin as pin_service
from core_system.models import OfficerUser


def _make_officer(username="pin_officer", role="President"):
    return OfficerUser.objects.create(
        full_name="PIN Officer",
        username=username,
        password_hash=hash_password("TestPass123!"),
        role=role,
        account_status="Active",
        email=f"{username}@example.com",
    )


def _login(client, officer, trusted=True):
    session, token = create_access_session(
        officer=officer, ip_address="127.0.0.1", device_info="tests")
    if trusted:
        session.trusted_device = True
        session.save(update_fields=["trusted_device"])
    s = client.session
    s["access_token"] = token
    s["officer_id"] = officer.user_id_PK
    s["role"] = officer.role
    s.save()
    return officer


class OfficerPinServiceTests(TestCase):
    def test_setup_password_optional_but_checked(self):
        o = _make_officer("svc1")
        ok, _ = pin_service.setup_action_pin(officer=o, pin="4829", password="Wrong123!")
        self.assertFalse(ok)
        ok, _ = pin_service.setup_action_pin(officer=o, pin="4829")
        self.assertTrue(ok)
        o.refresh_from_db()
        self.assertTrue(o.action_pin_hash.startswith("pin_pbkdf2_sha256$"))
        self.assertNotIn("4829", o.action_pin_hash)

    def test_pin_format_4_digits(self):
        self.assertTrue(pin_service.validate_action_pin("4829") == [])
        self.assertTrue(pin_service.validate_action_pin("12345") != [])
        self.assertTrue(pin_service.validate_action_pin("abcd") != [])
        self.assertTrue(pin_service.validate_action_pin("1111") != [])

    def test_lockout_doubles(self):
        o = _make_officer("svc2")
        pin_service.setup_action_pin(officer=o, pin="4829", password="TestPass123!")
        for _ in range(3):
            pin_service.verify_action_pin(o, "0000", audit=False)
        o.refresh_from_db()
        locked, _ = pin_service.is_action_pin_locked(o)
        self.assertTrue(locked)
        self.assertEqual(o.action_pin_lock_minutes, 2)
        # expire, fail 3 more -> 2-min lock, next 4
        o.action_pin_locked_until = timezone.now() - timezone.timedelta(seconds=1)
        o.save(update_fields=["action_pin_locked_until"])
        for _ in range(3):
            pin_service.verify_action_pin(o, "0000", audit=False)
        o.refresh_from_db()
        self.assertEqual(o.action_pin_lock_minutes, 4)

    def test_success_resets(self):
        o = _make_officer("svc3")
        pin_service.setup_action_pin(officer=o, pin="4829", password="TestPass123!")
        pin_service.verify_action_pin(o, "0000", audit=False)
        ok, _, _ = pin_service.verify_action_pin(o, "4829", audit=False)
        self.assertTrue(ok)
        o.refresh_from_db()
        self.assertEqual(o.action_pin_fail_count, 0)
        self.assertEqual(o.action_pin_lock_minutes, 1)


class OfficerPinApiTests(TestCase):
    def test_status_setup_verify_change_reset(self):
        o = _make_officer("api1", role="Auditor")
        _login(self.client, o)
        r = self.client.get("/api/officer/pin/status/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["has_pin"])
        r = self.client.post("/api/officer/pin/setup/",
                             json.dumps({"pin": "4829", "password": "TestPass123!"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/officer/pin/verify/",
                             json.dumps({"pin": "4829"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/officer/pin/change/",
                             json.dumps({"current_pin": "4829", "new_pin": "9371",
                                         "password": "TestPass123!"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_reset_requires_mfa_grant(self):
        from core_system.services.mfa_service import generate_mfa_secret, generate_otp

        o = _make_officer("api3", role="Treasurer")
        _login(self.client, o)
        pin_service.setup_action_pin(officer=o, pin="4829", password="TestPass123!")
        # No grant: password alone is rejected (officer has email = MFA option).
        r = self.client.post("/api/officer/pin/reset/",
                             json.dumps({"new_pin": "2648", "password": "TestPass123!"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get("code"), "RESET_UNAUTHORIZED")
        # Step 1: verify an email-OTP code computed from the officer secret.
        o.mfa_secret = generate_mfa_secret()
        o.save(update_fields=["mfa_secret"])
        code = generate_otp(o.mfa_secret)
        r = self.client.post("/api/officer/pin/reset/verify/",
                             json.dumps({"code": code}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        # Step 2: grant is single-use — first reset works, replay fails.
        r = self.client.post("/api/officer/pin/reset/",
                             json.dumps({"new_pin": "2648"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        r = self.client.post("/api/officer/pin/reset/",
                             json.dumps({"new_pin": "3591"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 403)
        # New PIN verifies.
        r = self.client.post("/api/officer/pin/verify/",
                             json.dumps({"pin": "2648"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_reset_with_backup_code_burns_it(self):
        from core_system.services.mfa_service import issue_backup_codes

        o = _make_officer("api4", role="Auditor")
        _login(self.client, o)
        pin_service.setup_action_pin(officer=o, pin="4829", password="TestPass123!")
        codes = issue_backup_codes(o)
        r = self.client.post("/api/officer/pin/reset/verify/",
                             json.dumps({"code": codes[0]}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("method"), "mfa_backup_code")
        r = self.client.post("/api/officer/pin/reset/",
                             json.dumps({"new_pin": "7593"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_approval_requires_pin(self):
        o = _make_officer("api2", role="President")
        _login(self.client, o)
        # No PIN set yet -> PIN_NOT_SET
        r = self.client.post("/api/payments/presidential-decision/",
                             json.dumps({"target_id": 1, "decision": "Approved"}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json().get("code"), "PIN_NOT_SET")
        # Set PIN, then missing PIN -> PIN_REQUIRED
        pin_service.setup_action_pin(officer=o, pin="4829", password="TestPass123!")
        r = self.client.post("/api/payments/presidential-decision/",
                             json.dumps({"target_id": 1, "decision": "Approved"}),
                             content_type="application/json")
        self.assertEqual(r.json().get("code"), "PIN_REQUIRED")
