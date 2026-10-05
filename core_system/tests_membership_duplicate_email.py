from django.test import TestCase
from django.urls import reverse

from core_system.auth_utils import create_access_session, hash_password
from core_system.isu_email_guard import (
    is_membership_duplicate_email_allowed,
    set_isu_email_guard_enabled,
    set_membership_duplicate_email_allowed,
)
from core_system.models import Member, OfficerUser


def _seed_test_session(self, officer):
    session, token = create_access_session(
        officer=officer,
        ip_address="127.0.0.1",
        device_info="tests",
    )
    session.save()
    test_session = self.client.session
    test_session["access_token"] = token
    test_session["officer_id"] = officer.user_id_PK
    test_session["role"] = officer.role
    test_session.save()


def _create_member(self, first_name, last_name, email):
    return self.client.post(
        reverse("treasurer_create_member"),
        data={
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "department": "CCSICT",
            "position": "Instructor",
            "membership_category": "Permanent",
            "classification": "Teaching",
            "amount": "100.00",
            "payment_method": "Cash",
        },
    )


class MembershipDuplicateEmailToggleTests(TestCase):
    def setUp(self):
        # Keep the ISU email guard off so plain test emails are accepted;
        # we are only exercising the duplicate-email policy here.
        set_isu_email_guard_enabled(False)
        set_membership_duplicate_email_allowed(False)

        self.officer = OfficerUser.objects.create(
            full_name="Treasurer Dup",
            username="treasurer_dup",
            password_hash=hash_password("TreasurerPass123!"),
            role="Treasurer",
            account_status="Active",
            mfa_enabled=False,
        )
        _seed_test_session(self, self.officer)

    def test_default_rejects_duplicate_emails(self):
        r1 = _create_member(self, "Alpha", "Beta", "dup@example.com")
        self.assertEqual(r1.status_code, 200, r1.content[:500])
        self.assertTrue(r1.json()["ok"])

        r2 = _create_member(self, "Gamma", "Delta", "dup@example.com")
        self.assertEqual(r2.status_code, 409, r2.content[:500])
        self.assertFalse(r2.json()["ok"])

    def test_toggle_on_allows_duplicate_emails(self):
        set_membership_duplicate_email_allowed(True)
        self.assertTrue(is_membership_duplicate_email_allowed())

        r1 = _create_member(self, "Alpha", "Beta", "dup@example.com")
        self.assertEqual(r1.status_code, 200, r1.content[:500])
        self.assertTrue(r1.json()["ok"])

        r2 = _create_member(self, "Gamma", "Delta", "dup@example.com")
        self.assertEqual(r2.status_code, 200, r2.content[:500])
        self.assertTrue(r2.json()["ok"])

        self.assertEqual(Member.objects.filter(email__iexact="dup@example.com").count(), 2)
        self.assertEqual(OfficerUser.objects.filter(email__iexact="dup@example.com").count(), 2)

    def test_toggle_off_rejects_duplicate_emails(self):
        set_membership_duplicate_email_allowed(False)
        # Seed a member first.
        _create_member(self, "Alpha", "Beta", "dup@example.com")

        r2 = _create_member(self, "Gamma", "Delta", "dup@example.com")
        self.assertEqual(r2.status_code, 409, r2.content[:500])
        self.assertFalse(r2.json()["ok"])

    def test_create_member_add_email_preview_respects_toggle(self):
        _create_member(self, "Alpha", "Beta", "dup@example.com")

        # When the toggle is off, the email is reported as taken.
        resp = self.client.post(
            reverse("treasurer_add_member"),
            data={"check_email": "dup@example.com"},
        )
        self.assertEqual(resp.status_code, 409, resp.content[:500])
        self.assertFalse(resp.json()["ok"])

        # When the toggle is on, the email is reported as available.
        set_membership_duplicate_email_allowed(True)
        resp2 = self.client.post(
            reverse("treasurer_add_member"),
            data={"check_email": "dup@example.com"},
        )
        self.assertEqual(resp2.status_code, 200, resp2.content[:500])
        self.assertTrue(resp2.json()["available"])

    def test_superadmin_can_toggle_duplicate_email_setting(self):
        from core_system.auth_utils import create_access_session

        superadmin = OfficerUser.objects.create(
            full_name="System Admin",
            username="sysadmin_dup",
            password_hash=hash_password("systemadmin"),
            role="Superadmin",
            account_status="Active",
            mfa_enabled=False,
        )
        session, token = create_access_session(
            officer=superadmin,
            ip_address="127.0.0.1",
            device_info="tests",
        )
        session.save()
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = superadmin.user_id_PK
        test_session["role"] = superadmin.role
        test_session.save()

        response = self.client.post(
            reverse("superadmin_dashboard"),
            data={"form_type": "membership_duplicate_email", "membership_duplicate_email": "on"},
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(is_membership_duplicate_email_allowed())

        response = self.client.post(
            reverse("superadmin_dashboard"),
            data={"form_type": "membership_duplicate_email", "membership_duplicate_email": "off"},
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertFalse(is_membership_duplicate_email_allowed())
