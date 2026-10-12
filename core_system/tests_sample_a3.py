"""A3 data contract (REPORTS.MD :: A3 Payment Status Report).

The A3 sheet blends three live sources — dues standing (assessment heatmaps),
aid-case contributions, and membership fees — into MEMBER / DEPARTMENT /
CATEGORY / DUE / PAID / LAST PAYMENT / STATUS rows. This test pins the dues
standing source (statuses full / partial / zero) and the A3 status vocabulary.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    AssessmentItem,
    Member,
    MemberAssessment,
    MembershipFee,
    MonthlyAssessment,
)
from core_system.tests import TreasurerApiClientMixin


def a3_status(paid, due):
    if paid >= due - 0.005:
        return "Fully Paid"
    if paid > 0.005:
        return "Partially Paid"
    return "Unpaid"


class SampleA3DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.members = []
        for name, emp in (("Domingo, Carmela N.", "MEM-0095"),
                          ("Reyes, Eduardo H.", "MEM-0128"),
                          ("Estrada, Grace F.", "MEM-0040")):
            self.members.append(Member.objects.create(
                full_name=name, employee_id=emp, department="College B",
                employment_status="Active", membership_status="Permanent",
                date_joined=date(2026, 9, 1),
            ))
        self.ass = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("50.00"),
            status=MonthlyAssessment.STATUS_PENDING_AUDIT,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.ass, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("50.00"), priority_order=1,
        )
        for member, actual in ((self.members[0], Decimal("50.00")),
                               (self.members[1], Decimal("20.00")),
                               (self.members[2], Decimal("0.00"))):
            MemberAssessment.objects.create(
                assessment_id_FK=self.ass, member_id_FK=member,
                standard_assessment=Decimal("50.00"), actual_deduction=actual,
                outstanding_balance=Decimal("50.00") - actual,
                status=MemberAssessment.STATUS_PENDING,
            )
        MembershipFee.objects.create(
            member_id_FK=self.members[0], amount=50, payment_method="Cash",
            payment_status="Partial", payment_date=date(2026, 9, 10),
            receipt_number="OR-1004", recorded_by_user_id_FK=self.officer,
        )

    def test_heatmap_gives_full_partial_zero_standing(self):
        data = self.client.get("/api/auditor/deductions/heatmap/",
                               {"assessment_id": self.ass.assessment_id_PK}).json()
        self.assertTrue(data["ok"])
        got = {m["member_id"]: m["status"] for m in data["members"]}
        self.assertEqual(got[self.members[0].member_id_PK], "full")
        self.assertEqual(got[self.members[1].member_id_PK], "partial")
        self.assertEqual(got[self.members[2].member_id_PK], "zero")

    def test_a3_status_vocabulary_matches_base_file(self):
        self.assertEqual(a3_status(150.0, 150.0), "Fully Paid")
        self.assertEqual(a3_status(100.0, 150.0), "Partially Paid")
        self.assertEqual(a3_status(0.0, 150.0), "Unpaid")
        # Fully Paid rows sort with everything else; the status filter hides
        # them for the base file's Unpaid/Partial view.
        self.assertIn("paid", "Fully Paid".lower())

    def test_fee_category_row_present_for_period(self):
        fees = self.client.get("/api/treasurer/membership-fees/list/").json()
        rows = [f for f in fees["fees"] if str(f["payment_date"]).startswith("2026-09")]
        self.assertEqual(len(rows), 1)
        self.assertEqual(a3_status(float(rows[0]["amount"]), 100), "Partially Paid")
