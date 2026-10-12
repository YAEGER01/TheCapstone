"""F3/F4 data contract (REPORTS.MD :: Pending Approval / Pending Disbursement).

F3 lists Auditor-verified items waiting on the President (verified claims +
pending_final deduction months; verification dates untracked). F4 lists
approved-but-unpaid remainders (approved − released > 0; authorization dates
untracked).
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    AssessmentItem,
    MedicalAid,
    Member,
    MonthlyAssessment,
)
from core_system.tests import TreasurerApiClientMixin


class SampleF3F4DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Valdez, Jericho G.", employee_id="MEM-0027", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        MedicalAid.objects.create(
            member_id_FK=self.member, request_date=date(2026, 9, 22),
            hospital_name="Cauayan Medical Center", hospital_bill_amount=Decimal("33200"),
            requested_amount=Decimal("33200"), claim_year=2026,
            document_status="Complete", policy_record_status="Recorded",
            validated_aid_amount=Decimal("14400"), status="Auditor Verified",
        )
        MedicalAid.objects.create(
            member_id_FK=self.member, request_date=date(2026, 9, 14),
            hospital_name="Cauayan Medical Center", hospital_bill_amount=Decimal("41000"),
            requested_amount=Decimal("41000"), claim_year=2026,
            document_status="Complete", policy_record_status="Recorded",
            validated_aid_amount=Decimal("14800"), status="Approved",
        )
        self.ass = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("600.00"),
            status=MonthlyAssessment.STATUS_PENDING_FINAL,
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.ass, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("50.00"), priority_order=1,
        )

    def test_auditor_verified_claim_waits_approval(self):
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        waiting = [a for a in rows if (a["status"] or "").strip() == "Auditor Verified"]
        self.assertEqual(len(waiting), 1)
        self.assertEqual(float(waiting[0]["validated_aid_amount"] or 0), 14400.0)

    def test_pending_final_month_waits_approval(self):
        data = self.client.get("/api/treasurer/deductions/overview/").json()
        pend = [a for a in data["assessments"]
                if a["status"] == MonthlyAssessment.STATUS_PENDING_FINAL]
        self.assertEqual(len(pend), 1)
        self.assertEqual(float(pend[0]["total_amount"]), 600.0)

    def test_approved_unreleased_is_full_remainder_without_outflow(self):
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        a = next(x for x in rows if (x["status"] or "").strip() == "Approved")
        approved = float(a["validated_aid_amount"] or 0)
        released = 0.0  # no outflow booked in this fixture
        self.assertEqual(round(approved - released, 2), 14800.0)
