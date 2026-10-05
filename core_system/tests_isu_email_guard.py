import json

from django.test import TestCase
from django.urls import reverse

from core_system.auth_utils import create_access_session, hash_password
from core_system.isu_email_guard import (
    is_isu_email_guard_enabled,
    set_isu_email_guard_enabled,
)
from core_system.models import OfficerUser
from core_system.shared_view_utils import validate_isu_email, validate_optional_isu_email


class IsuEmailGuardToggleTests(TestCase):
    def test_default_guard_is_enabled(self):
        self.assertTrue(is_isu_email_guard_enabled())

    def test_guard_off_allows_non_isu_email(self):
        set_isu_email_guard_enabled(False)
        self.assertFalse(is_isu_email_guard_enabled())

        email, err = validate_isu_email("person@example.com")
        self.assertIsNone(err)
        self.assertEqual(email, "person@example.com")

        email, err = validate_isu_email("person@isu.edu.ph")
        self.assertIsNone(err)
        self.assertEqual(email, "person@isu.edu.ph")

        _, err = validate_isu_email("not-an-email")
        self.assertIsNotNone(err)

        _, err = validate_isu_email("   ")
        self.assertIsNotNone(err)

    def test_guard_on_rejects_non_isu_email(self):
        set_isu_email_guard_enabled(True)
        _, err = validate_isu_email("person@example.com")
        self.assertIsNotNone(err)

        email, err = validate_isu_email("Person@ISU.EDU.PH")
        self.assertIsNone(err)
        self.assertEqual(email, "Person@ISU.EDU.PH")

    def test_optional_passthrough_when_guard_off(self):
        set_isu_email_guard_enabled(False)
        self.assertEqual(validate_optional_isu_email(""), ("", None))
        email, err = validate_optional_isu_email("other@school.edu")
        self.assertIsNone(err)
        self.assertEqual(email, "other@school.edu")

    def test_treasurer_create_member_accepts_non_isu_when_guard_off(self):
        set_isu_email_guard_enabled(False)
        officer = OfficerUser.objects.create(
            full_name="Treasurer Guard",
            username="treasurer_guard",
            password_hash=hash_password("TreasurerPass123!"),
            role="Treasurer",
            account_status="Active",
            mfa_enabled=False,
        )
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

        response = self.client.post(
            reverse("treasurer_create_member"),
            data={
                "first_name": "Guard",
                "last_name": "Off",
                "email": "guard.off@example.com",
                "department": "CCSICT",
                "position": "Instructor",
                "membership_category": "Permanent",
                "classification": "Teaching",
                "amount": "100.00",
                "payment_method": "Cash",
            },
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.json()["ok"])

    def test_treasurer_create_member_rejects_non_isu_when_guard_on(self):
        set_isu_email_guard_enabled(True)
        officer = OfficerUser.objects.create(
            full_name="Treasurer Guard On",
            username="treasurer_guard_on",
            password_hash=hash_password("TreasurerPass123!"),
            role="Treasurer",
            account_status="Active",
            mfa_enabled=False,
        )
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

        response = self.client.post(
            reverse("treasurer_create_member"),
            data={
                "first_name": "Guard",
                "last_name": "On",
                "email": "guard.on@example.com",
                "department": "CCSICT",
                "position": "Instructor",
                "membership_category": "Permanent",
                "classification": "Teaching",
                "amount": "100.00",
                "payment_method": "Cash",
            },
        )
        self.assertEqual(response.status_code, 400, response.content[:500])
        self.assertFalse(response.json()["ok"])

    def test_superadmin_can_toggle_guard(self):
        officer = OfficerUser.objects.create(
            full_name="System Admin",
            username="systemadmin_guard",
            password_hash=hash_password("systemadmin"),
            role="Superadmin",
            account_status="Active",
            mfa_enabled=False,
        )
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

        response = self.client.post(
            reverse("superadmin_dashboard"),
            data={"form_type": "isu_email_guard", "isu_email_guard": "off"},
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertFalse(is_isu_email_guard_enabled())

        response = self.client.post(
            reverse("superadmin_dashboard"),
            data={"form_type": "isu_email_guard", "isu_email_guard": "on"},
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(is_isu_email_guard_enabled())
