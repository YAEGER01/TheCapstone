"""A release can never exceed the available fund balance.

Scenario from the treasurer's Release Queue: fund holds ₱400, the release
modal must refuse ₱401+. The frontend clamps the input, but the real
guarantee lives here — the release endpoint rejects any effective outflow
(manual override included, both fund-paid and contribution posts) that is
greater than the current fund balance.
"""
from decimal import Decimal
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from core_system.models import (
    AidTrackingPost,
    FundTransaction,
    Member,
    OfficerUser,
    SystemSetting,
    TransactionArchive,
)
from core_system.services.mfa_service import generate_otp
from core_system.tests import _create_zt_verified_session


class ReleaseFundCapTests(TestCase):
    def setUp(self):
        self.officer = OfficerUser.objects.create(
            full_name="Treasurer Cap Test",
            username="trez_cap_" + str(timezone.now().timestamp()),
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
            mfa_secret="release-otp-test-secret",
        )
        session, token = _create_zt_verified_session(self.officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = self.officer.user_id_PK
        test_session["role"] = self.officer.role
        test_session.save()

        self.member = Member.objects.create(
            full_name="Cap Test Member",
            employee_id="EMP-CAP-001",
            department="HR",
            position="Staff",
            membership_status="Active",
            employment_status="Active",
            member_type="REG",
            date_joined=timezone.now().date(),
        )
        # Fund holds exactly ₱400.
        FundTransaction.objects.create(
            direction="inflow",
            amount=Decimal("400.00"),
            source_type="contribution",
            source_id=1,
            description="test inflow",
            recorded_by_user_id_FK=self.officer,
        )
        # Post asking for ₱500, funded by contributions (not fund-paid).
        self.archive = TransactionArchive.objects.create(
            transaction_type="medical_aid",
            record_id=991,
            member_id_FK=self.member,
            member_name=self.member.full_name,
            amount=500,
            validated_amount=500,
            status="Approved",
        )
        self.post = AidTrackingPost.objects.create(
            archive_id_FK=self.archive,
            aid_type="medical_aid",
            target_month="2026-09",
            total_expected=500,
            total_collected=500,
            finish_paid_with_funds=False,
            finish_status="pending_release",
            is_active=True,
        )

    def _release(self, **extra):
        # Stand in for the emailed verification code: every release now needs
        # a code bound to this claim, a named recipient and an acknowledgement
        # that any shortfall leaves the general fund.
        test_session = self.client.session
        test_session["aid_release_otp"] = {
            "post_id": int(self.post.post_id_PK),
            "sent_at": timezone.now().timestamp(),
            "expires_at": (timezone.now() + timedelta(seconds=300)).isoformat(),
        }
        test_session.save()
        payload = {
            "post_id": str(self.post.post_id_PK),
            "otp": generate_otp(self.officer.mfa_secret or ""),
            "received_by": "Juan Dela Cruz",
            "ack_fund_deduction": "1",
            "override_reason": "Release approved from the general fund.",
        }
        payload.update(extra)
        return self.client.post("/api/treasurer/aid-post-release/", payload)

    def test_manual_override_above_fund_balance_rejected(self):
        response = self._release(override_amount="500")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("exceeds the available fund balance", response.json()["error"])
        self.assertIn("400.00", response.json()["error"])
        # Nothing booked, post still waiting.
        self.assertFalse(
            FundTransaction.objects.filter(direction="outflow").exists()
        )
        self.post.refresh_from_db()
        self.assertEqual(self.post.finish_status, "pending_release")

    def test_release_at_exact_fund_balance_allowed(self):
        response = self._release(override_amount="400")
        self.assertEqual(response.status_code, 200, response.content)
        outflows = FundTransaction.objects.filter(direction="outflow")
        self.assertEqual(outflows.count(), 1)
        self.assertEqual(float(outflows.first().amount), 400.0)

    def test_fund_paid_post_override_above_balance_rejected(self):
        """The paid-with-funds path also honors the cap (before its own
        safety-threshold check), using the override — not total_expected."""
        SystemSetting.objects.update_or_create(
            setting_key="safety_threshold", defaults={"setting_value": "0"}
        )
        self.post.finish_paid_with_funds = True
        self.post.save(update_fields=["finish_paid_with_funds"])
        response = self._release(override_amount="401")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("exceeds the available fund balance", response.json()["error"])
        self.assertFalse(
            FundTransaction.objects.filter(direction="outflow").exists()
        )
