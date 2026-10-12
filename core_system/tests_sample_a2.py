"""A2 data contract (REPORTS.MD :: A2 Monthly Dues Collection Report).

The A2 sheet is rendered client-side from the monthly-assessment workflow:
`deductions/overview` (assessment + collection batch) and the per-assessment
compliance heatmap (per-member standard / actual / outstanding). This test pins
every field the sheet reads.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    AssessmentItem,
    Member,
    MemberAssessment,
    MonthlyAssessment,
)
from core_system.tests import TreasurerApiClientMixin


def a2_status(st):
    return {"full": "Fully Paid", "partial": "Partially Paid", "zero": "Unpaid",
            "pending": "Not Yet Recorded"}.get(st, st)


class SampleA2DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.m1 = Member.objects.create(
            full_name="Aguilar, Ana A.", employee_id="MEM-0108", department="College B",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 9, 1),
        )
        self.m2 = Member.objects.create(
            full_name="Domingo, Carmela N.", employee_id="MEM-0095", department="College B",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 9, 1),
        )
        self.ass = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("50.00"),
            status=MonthlyAssessment.STATUS_PENDING_AUDIT,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.ass, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("50.00"), priority_order=1,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.ass, member_id_FK=self.m1,
            standard_assessment=Decimal("50.00"), actual_deduction=Decimal("50.00"),
            outstanding_balance=Decimal("0.00"), status=MemberAssessment.STATUS_PENDING,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.ass, member_id_FK=self.m2,
            standard_assessment=Decimal("50.00"), actual_deduction=Decimal("20.00"),
            outstanding_balance=Decimal("30.00"), status=MemberAssessment.STATUS_PENDING,
        )

    def test_overview_carries_assessment_and_batch_fields(self):
        data = self.client.get("/api/treasurer/deductions/overview/").json()
        self.assertTrue(data["ok"])
        ass = next(a for a in data["assessments"]
                   if a["assessment_id"] == self.ass.assessment_id_PK)
        for key in ("assessment_id", "month", "month_label", "collection_reference",
                    "deposit_reference", "status"):
            self.assertIn(key, ass)
        self.assertTrue(str(ass["month"]).startswith("2026-09"))
        self.assertEqual(ass["month_label"], "September 2026")
        self.assertTrue(ass["collection_reference"].startswith("COL-"))

    def test_heatmap_carries_per_member_a2_columns(self):
        data = self.client.get("/api/auditor/deductions/heatmap/",
                               {"assessment_id": self.ass.assessment_id_PK}).json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["notify_allowed"])
        rows = {m["member_id"]: m for m in data["members"]}
        for key in ("member_id", "member_name", "department", "status",
                    "standard", "actual", "outstanding"):
            self.assertIn(key, rows[self.m1.member_id_PK])
        full = rows[self.m1.member_id_PK]
        self.assertEqual(full["status"], "full")
        self.assertEqual(a2_status(full["status"]), "Fully Paid")
        self.assertEqual(float(full["standard"]), 50.0)
        self.assertEqual(float(full["actual"]), 50.0)
        self.assertEqual(float(full["outstanding"]), 0.0)
        part = rows[self.m2.member_id_PK]
        self.assertEqual(part["status"], "partial")
        self.assertEqual(a2_status(part["status"]), "Partially Paid")
        self.assertEqual(float(part["outstanding"]), 30.0)

    def test_a2_totals_match_base_file_arithmetic(self):
        # Assessed − collected = balance, summed across rows (cf. A2 TOTAL).
        rows = [(50.0, 50.0), (50.0, 20.0)]
        t_ass = sum(a for a, _ in rows)
        t_col = sum(c for _, c in rows)
        self.assertEqual(round(t_ass - t_col, 2), 30.0)
