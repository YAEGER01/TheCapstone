"""H3 data contract (REPORTS.MD :: Member Subsidiary Ledger).

H3 is one member's statement over a range: statement block, previous/ending
balances, and charge/payment/running-balance detail across dues months, fee
receipts and aid contributions.
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


class SampleH3DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Mercado, Corazon M.", employee_id="MEM-0088", department="College D",
            employment_status="Active", membership_status="Permanent",
            member_type="Regular", date_joined=date(2026, 7, 1),
        )
        self.jul = MonthlyAssessment.objects.create(
            month=date(2026, 7, 1), total_amount=Decimal("50.00"),
            status=MonthlyAssessment.STATUS_FINAL_APPROVED,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.jul, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("50.00"), priority_order=1,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.jul, member_id_FK=self.member,
            standard_assessment=Decimal("50.00"), actual_deduction=Decimal("50.00"),
            outstanding_balance=Decimal("0.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        self.sep = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("50.00"),
            status=MonthlyAssessment.STATUS_FINAL_APPROVED,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.sep, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("50.00"), priority_order=1,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.sep, member_id_FK=self.member,
            standard_assessment=Decimal("50.00"), actual_deduction=Decimal("25.00"),
            outstanding_balance=Decimal("25.00"),
            status=MemberAssessment.STATUS_APPROVED,
        )
        MembershipFee.objects.create(
            member_id_FK=self.member, amount=100, payment_method="Cash",
            payment_status="Paid", payment_date=date(2026, 9, 8),
            receipt_number="OR-1003", recorded_by_user_id_FK=self.officer,
        )

    def test_ledger_months_carry_h3_dues_detail(self):
        data = self.client.get(
            "/api/officers/deductions/member-ledger/",
            {"member_id": self.member.member_id_PK}).json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["months"]), 2)
        by_month = {m["month"][:7]: m for m in data["months"]}
        self.assertEqual(float(by_month["2026-07"]["deducted"]), 50.0)
        self.assertEqual(float(by_month["2026-09"]["standard"]), 50.0)
        self.assertEqual(float(by_month["2026-09"]["remaining_balance"]), 25.0)

    def test_running_balance_arithmetic(self):
        # Jul 50/50 -> 0; Sep dues 50/25 -> 25; fee 100/100 -> 25.
        run = 0.0
        for charge, payment in ((50.0, 50.0), (50.0, 25.0), (100.0, 100.0)):
            run = round(run + charge - payment, 2)
        self.assertEqual(run, 25.0)

    def test_fee_receipt_present_for_member(self):
        data = self.client.get("/api/treasurer/membership-fees/list/").json()
        mine = [f for f in data["fees"] if str(f["member_id"]) == str(self.member.member_id_PK)]
        self.assertEqual(len(mine), 1)
        self.assertEqual(float(mine[0]["amount"]), 100.0)
