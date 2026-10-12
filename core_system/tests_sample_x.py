"""X1/X2 data contract (REPORTS.MD :: Retirement/Death Donation / Deposit).

X1 lists donation-flavored outflows (retirement/token/death-donation wording)
with roster-matched campus. X2 lists assessment deposits with references,
one-off deposits, and recorded-but-not-yet-deposited collections.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    AssessmentItem,
    FundTransaction,
    Member,
    MemberAssessment,
    MonthlyAssessment,
)
from core_system.tests import TreasurerApiClientMixin


class SampleXDataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Retiree Test Member", employee_id="MEM-0701", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("500"), source_type="other_transaction",
            source_id=0, description="To Retiree Test Member — Retirement and Death Donation (retirement)",
            reference_number="DV-2026-060", recorded_by_user_id_FK=self.officer,
        )
        self.ass = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("600.00"),
            status=MonthlyAssessment.STATUS_PENDING_DEPOSIT,
            deposit_reference="DEP-0930", deposited_amount=Decimal("600"),
            deposited_at="2026-09-30T10:00:00+08:00",
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.ass, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("600.00"), priority_order=1,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.ass, member_id_FK=self.member,
            standard_assessment=Decimal("600.00"), actual_deduction=Decimal("600.00"),
            outstanding_balance=Decimal("0.00"), status=MemberAssessment.STATUS_PENDING,
        )
        self.avoro = MonthlyAssessment.objects.create(
            month=date(2026, 10, 1), total_amount=Decimal("600.00"),
            status=MonthlyAssessment.STATUS_PENDING_DEPOSIT,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.avoro, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("600.00"), priority_order=1,
        )
        MemberAssessment.objects.create(
            assessment_id_FK=self.avoro, member_id_FK=self.member,
            standard_assessment=Decimal("600.00"), actual_deduction=Decimal("600.00"),
            outstanding_balance=Decimal("0.00"), status=MemberAssessment.STATUS_PENDING,
        )

    def test_x1_keyword_outflow_visible_in_ledger(self):
        import re
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        hits = [e for e in data["items"]
                if e["direction"] == "outflow"
                and re.search(r"retire|token incentive|death donation", e["description"], re.I)]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["reference_number"], "DV-2026-060")

    def test_x2_deposited_assessment_carries_reference(self):
        data = self.client.get("/api/treasurer/deductions/overview/").json()
        by_id = {a["assessment_id"]: a for a in data["assessments"]}
        dep = by_id[self.ass.assessment_id_PK]
        self.assertEqual(dep["deposit_reference"], "DEP-0930")
        self.assertEqual(float(dep["deposited_amount"]), 600.0)
        self.assertTrue(str(dep["deposited_at"]).startswith("2026-09-30"))

    def test_x2_pending_assessment_has_no_reference_but_recorded(self):
        data = self.client.get("/api/treasurer/deductions/overview/").json()
        by_id = {a["assessment_id"]: a for a in data["assessments"]}
        pend = by_id[self.avoro.assessment_id_PK]
        self.assertFalse(pend["deposit_reference"])
        self.assertGreater(float(pend["total_recorded"]), 0.0)
