"""President must not rewrite the breakdown of an auditor-rejected month.

Regression: after the Auditor rejected a month's recorded deductions
(status "Rejected by Auditor"), the President could still open that month,
edit/remove its breakdown items, and save — the save wiped and replaced the
breakdown rows, corrupting the recorded member rows/allocations and yanking
the month out of the Treasurer's re-record queue. The breakdown must freeze
as soon as any member row is recorded against the month.
"""
import json
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import (
    AssessmentItem,
    Member,
    MemberAssessment,
    MonthlyAssessment,
    OfficerUser,
)


class PresidentBreakdownFreezeTests(TestCase):
    def _login(self, username="president_freeze"):
        officer = OfficerUser.objects.create(
            full_name="Freeze Tester",
            username=username,
            password_hash=hash_password("FreezePass123!"),
            role="President",
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
        return officer

    def _make_month(self, officer, status, month=date(2026, 9, 1)):
        assessment = MonthlyAssessment.objects.create(
            month=month,
            total_amount=Decimal("100.00"),
            status=status,
            created_by_id_FK=officer,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            custom_label="September 2026",
            amount=Decimal("100.00"),
            recipient="ISUCauFA, Inc.",
            priority_order=1,
        )
        return assessment

    def _make_member(self, index=1):
        return Member.objects.create(
            full_name=f"Freeze Member {index}",
            employee_id=f"EMP-FZ-{index:03d}",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            email=f"fz_member_{index}@test.local",
            date_joined=timezone.now().date(),
        )

    def _record_member(self, assessment, member):
        return MemberAssessment.objects.create(
            assessment_id_FK=assessment,
            member_id_FK=member,
            standard_assessment=Decimal("100.00"),
            actual_deduction=Decimal("100.00"),
            outstanding_balance=Decimal("0.00"),
        )

    def _save(self, month_label, items):
        return self.client.post(
            reverse("president_save_monthly_assessment"),
            data=json.dumps({"month": month_label, "draft": True, "items": items}),
            content_type="application/json",
        )

    def test_rejected_month_with_records_cannot_be_rewritten(self):
        officer = self._login()
        assessment = self._make_month(officer, MonthlyAssessment.STATUS_REJECTED)
        member = self._make_member()
        self._record_member(assessment, member)
        item_ids_before = list(
            assessment.items.values_list("item_id_PK", flat=True)
        )

        response = self._save("2026-09", [{"purpose": "monthly_due", "amount": "50.00"}])

        self.assertEqual(response.status_code, 409, response.content[:500])
        self.assertFalse(response.json()["ok"])
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, MonthlyAssessment.STATUS_REJECTED)
        self.assertEqual(assessment.total_amount, Decimal("100.00"))
        self.assertEqual(
            list(assessment.items.values_list("item_id_PK", flat=True)),
            item_ids_before,
        )
        self.assertTrue(
            MemberAssessment.objects.filter(
                assessment_id_FK=assessment, member_id_FK=member
            ).exists()
        )

    def test_returned_month_with_records_cannot_be_rewritten(self):
        officer = self._login(username="president_freeze_returned")
        assessment = self._make_month(officer, MonthlyAssessment.STATUS_RETURNED)
        self._record_member(assessment, self._make_member())

        response = self._save("2026-09", [{"purpose": "monthly_due", "amount": "50.00"}])

        self.assertEqual(response.status_code, 409, response.content[:500])
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, MonthlyAssessment.STATUS_RETURNED)
        self.assertEqual(assessment.items.count(), 1)

    def test_rejected_month_without_records_stays_editable(self):
        officer = self._login(username="president_freeze_empty")
        self._make_month(officer, MonthlyAssessment.STATUS_REJECTED)

        response = self._save("2026-09", [{"purpose": "monthly_due", "amount": "150.00"}])

        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.json()["ok"])
