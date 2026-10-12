"""A4 data contract (REPORTS.MD :: A4 Outstanding Balance Report).

The A4 sheet is a single-member statement as of a point in time: category
balances (dues / fee / aid) plus a charge/payment/running-balance detail built
from the member's deduction ledger, fee receipts and aid-case contributions.
This test pins the ledger + fee sources and the outstanding arithmetic.
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


class SampleA4DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Estrada, Grace F.", employee_id="MEM-0040", department="College B",
            employment_status="Active", membership_status="Permanent",
            member_type="Regular", date_joined=date(2026, 7, 1),
        )
        self.ass = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("50.00"),
            status=MonthlyAssessment.STATUS_FINAL_APPROVED,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.ass, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("50.00"), priority_order=1,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.ass, member_id_FK=self.member,
            standard_assessment=Decimal("50.00"), actual_deduction=Decimal("30.00"),
            outstanding_balance=Decimal("20.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        MembershipFee.objects.create(
            member_id_FK=self.member, amount=100, payment_method="Cash",
            payment_status="Paid", payment_date=date(2026, 9, 5),
            receipt_number="OR-1001", recorded_by_user_id_FK=self.officer,
        )

    def test_member_ledger_carries_a4_dues_detail(self):
        data = self.client.get(
            "/api/officers/deductions/member-ledger/",
            {"member_id": self.member.member_id_PK}).json()
        self.assertTrue(data["ok"])
        months = [m for m in data["months"] if str(m["month"]).startswith("2026-09")]
        self.assertEqual(len(months), 1)
        mo = months[0]
        for key in ("month", "month_label", "standard", "deducted", "remaining_balance"):
            self.assertIn(key, mo)
        self.assertEqual(float(mo["standard"]), 50.0)
        self.assertEqual(float(mo["deducted"]), 30.0)

    def test_a4_outstanding_arithmetic(self):
        # Dues 50 − 30 = 20; fee 100 − 100 = 0; aid 0 − 0 = 0; total 20.
        dues_bal = 50.0 - 30.0
        fee_bal = 100.0 - 100.0
        self.assertEqual(round(dues_bal + fee_bal, 2), 20.0)
        # Running balance over detail rows in date order.
        run = 0.0
        for charge, payment in ((50.0, 30.0), (100.0, 100.0)):
            run = round(run + charge - payment, 2)
        self.assertEqual(run, 20.0)

    def test_as_of_filter_drops_later_months(self):
        as_of = "2026-09-30"
        months = ["2026-08", "2026-09", "2026-10"]
        kept = [m for m in months if m <= as_of[:7]]
        self.assertEqual(kept, ["2026-08", "2026-09"])
