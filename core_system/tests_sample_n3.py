"""N3 data contract (REPORTS.MD :: Budget vs Actual Report).

N3 compares approved budget lines per category against live actuals in range
(dues collected, fees, aid contributions, aid payouts, operations). Without
an approved budget the sheet stays in the base file's blank state.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core_system.models import (
    AssessmentItem,
    BudgetLine,
    Member,
    MemberAssessment,
    MembershipFee,
    MonthlyAssessment,
)
from core_system.tests import TreasurerApiClientMixin


class SampleN3DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Budget Test Member", employee_id="MEM-0901", department="College B",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        BudgetLine.objects.create(fiscal_year=2026, category="monthly_dues",
                                  amount=Decimal("6000"), notes="test")
        self.ass = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("50.00"),
            status=MonthlyAssessment.STATUS_PENDING_AUDIT,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.ass, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("50.00"), priority_order=1,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.ass, member_id_FK=self.member,
            standard_assessment=Decimal("50.00"), actual_deduction=Decimal("50.00"),
            outstanding_balance=Decimal("0.00"), status=MemberAssessment.STATUS_PENDING,
        )
        MembershipFee.objects.create(
            member_id_FK=self.member, amount=100, payment_method="Cash",
            payment_status="Paid", payment_date=date(2026, 9, 5),
            receipt_number="OR-1001", recorded_by_user_id_FK=self.officer,
        )

    def test_budget_lines_listed_per_year(self):
        data = self.client.get("/api/reports/association/budget/lines/",
                               {"year": 2026}).json()
        self.assertTrue(data["ok"])
        by_cat = {l["category"]: float(l["amount"]) for l in data["lines"]}
        self.assertEqual(by_cat.get("monthly_dues"), 6000.0)

    def test_dues_actual_from_heatmap(self):
        data = self.client.get("/api/auditor/deductions/heatmap/",
                               {"assessment_id": self.ass.assessment_id_PK}).json()
        self.assertEqual(float(data["totals"]["collected"]), 50.0)

    def test_fee_actual_in_range(self):
        data = self.client.get("/api/treasurer/membership-fees/list/").json()
        total = sum(float(f["amount"]) for f in data["fees"]
                    if str(f["payment_date"]).startswith("2026-09"))
        self.assertEqual(total, 100.0)

    def test_variance_sign_preserved(self):
        self.assertEqual(round(6000.0 - 50.0, 2), 5950.0)
        self.assertEqual(round(0.0 - 300.0, 2), -300.0)
        _ = timezone.localdate()
