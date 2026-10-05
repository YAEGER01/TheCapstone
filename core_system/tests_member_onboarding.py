import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_system.auth_utils import (
    create_access_session,
    hash_password,
    verify_password,
)
from core_system.models import GlobalAuditTrail, Member, OfficerUser

TEMP_PASSWORD = "Temp-Pass-4821!"
NEW_PASSWORD = "NewPass-999!x"


class MemberOnboardingTests(TestCase):
    """First-login onboarding gate ported from FROMGROUP/isucaufa-onboarding-demo.html.

    The member dashboard shows a Data Privacy Notice + account activation card
    until the member completes it once. Completing activation verifies the
    emailed temporary password, enforces the canonical strength rules, records
    the agreement in the audit trail, and unlocks the dashboard.
    """

    def _member_session(self, *, setup_complete=False, must_change_password=False):
        officer = OfficerUser.objects.create(
            full_name="Onboard Member",
            username="onboard_member",
            password_hash=hash_password(TEMP_PASSWORD),
            role="Member",
            account_status="Active",
            mfa_enabled=False,
            must_change_password=must_change_password,
        )
        member = Member.objects.create(
            full_name="Onboard Member",
            employment_status="Permanent",
            membership_status="Active",
            member_type="",
            date_joined=timezone.now().date(),
            officer_user_id_FK=officer,
            setup_complete=setup_complete,
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
        return member, officer

    def _activate(self, **overrides):
        payload = {
            "temp_password": TEMP_PASSWORD,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
            "agreed_terms": True,
        }
        payload.update(overrides)
        return self.client.post(
            reverse("member_onboarding_activate"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_dashboard_shows_gate_when_onboarding_pending(self):
        self._member_session(setup_complete=False)
        response = self.client.get(reverse("member_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "obOverlay")
        self.assertContains(response, "Data Privacy Notice")
        self.assertContains(response, "Activate your account")

    def test_dashboard_shows_gate_while_password_change_forced(self):
        """Even a setup-complete member sees the gate while must_change_password is set."""
        self._member_session(setup_complete=True, must_change_password=True)
        response = self.client.get(reverse("member_dashboard"))
        self.assertContains(response, "obOverlay")

    def test_dashboard_hides_gate_after_completion(self):
        self._member_session(setup_complete=True, must_change_password=False)
        response = self.client.get(reverse("member_dashboard"))
        self.assertNotContains(response, "obOverlay")

    def test_activation_success_sets_password_and_flags(self):
        member, officer = self._member_session(setup_complete=False, must_change_password=True)

        response = self._activate()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        officer.refresh_from_db()
        member.refresh_from_db()
        self.assertTrue(verify_password(NEW_PASSWORD, officer.password_hash))
        self.assertFalse(officer.must_change_password)
        self.assertTrue(member.setup_complete)

        entry = GlobalAuditTrail.objects.filter(
            action="ACCOUNT_ACTIVATED", record_id=member.member_id_PK, result="Success"
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.table_name, "member")

        # Gate no longer rendered on the next dashboard load.
        self.assertNotContains(self.client.get(reverse("member_dashboard")), "obOverlay")

    def test_activation_rejects_wrong_temp_password(self):
        member, officer = self._member_session()
        response = self._activate(temp_password="WRONG-temp-1!")
        self.assertEqual(response.status_code, 400)
        self.assertIn("incorrect", response.json()["error"])
        officer.refresh_from_db()
        member.refresh_from_db()
        self.assertFalse(member.setup_complete)
        self.assertTrue(GlobalAuditTrail.objects.filter(
            action="ACCOUNT_ACTIVATED", record_id=member.member_id_PK, result="Failed"
        ).exists())

    def test_activation_enforces_password_strength(self):
        self._member_session()
        response = self._activate(new_password="weakpass", confirm_password="weakpass")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Password must", response.json()["error"])

    def test_activation_rejects_mismatched_confirmation(self):
        self._member_session()
        response = self._activate(confirm_password="Different-1!")
        self.assertEqual(response.status_code, 400)
        self.assertIn("do not match", response.json()["error"])

    def test_activation_rejects_same_as_temporary(self):
        self._member_session()
        response = self._activate(new_password=TEMP_PASSWORD, confirm_password=TEMP_PASSWORD)
        self.assertEqual(response.status_code, 400)
        self.assertIn("different", response.json()["error"])

    def test_activation_requires_terms_agreement(self):
        self._member_session()
        response = self._activate(agreed_terms=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("agree", response.json()["error"])

    def test_activation_twice_returns_error(self):
        self._member_session(setup_complete=False)
        self.assertEqual(self._activate().status_code, 200)
        response = self._activate()
        self.assertEqual(response.status_code, 400)
        self.assertIn("already completed", response.json()["error"])

    def test_member_login_redirect_goes_to_dashboard_not_change_password(self):
        """First-login members activate through the dashboard onboarding gate."""
        from core_system.auth_views import _login_success_redirect

        _, officer = self._member_session(setup_complete=False, must_change_password=True)
        self.assertEqual(_login_success_redirect(officer), "/member/")
        officer.must_change_password = False
        self.assertEqual(_login_success_redirect(officer), "/member/")

        secretary = OfficerUser(
            full_name="Sec", username="sec_onboard", role="Secretary", must_change_password=True
        )
        self.assertEqual(_login_success_redirect(secretary), "/change-password/")
