"""F6/F7 data contract (REPORTS.MD :: Audit Exceptions / Discrepancy).

F6 lists months the Auditor formally flagged (rejected with remarks — all
live rows read Open). F7 runs live system checks: duplicate fund postings,
assessed-vs-collected per recorded month, approved-vs-released per claim, with
sign-preserving variances and a net total.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    AssessmentItem,
    FundTransaction,
    MedicalAid,
    Member,
    MonthlyAssessment,
)
from core_system.tests import TreasurerApiClientMixin


class SampleF6F7DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Navarro, Rosario H.", employee_id="MEM-0023", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        self.ass = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("600.00"),
            status=MonthlyAssessment.STATUS_REJECTED,
            auditor_remarks="Deduction sheet total does not match recorded total.",
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.ass, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("50.00"), priority_order=1,
        )
        self.med = MedicalAid.objects.create(
            member_id_FK=self.member, request_date=date(2026, 9, 14),
            hospital_name="Cauayan Medical Center", hospital_bill_amount=Decimal("62500"),
            requested_amount=Decimal("62500"), claim_year=2026,
            document_status="Complete", policy_record_status="Recorded",
            validated_aid_amount=Decimal("14400"), status="Approved",
        )
        for ref in ("DV-2026-051", "DV-2026-051-DUP"):
            FundTransaction.objects.create(
                direction="outflow", amount=Decimal("13300"), source_type="medical_aid",
                source_id=self.med.medical_aid_id_PK,
                description=f"Aid disbursement — {self.member.full_name} (medical_aid)",
                reference_number=ref, recorded_by_user_id_FK=self.officer,
            )

    def test_rejected_month_carries_auditor_remarks(self):
        data = self.client.get("/api/treasurer/deductions/overview/").json()
        rej = [a for a in data["assessments"]
               if a["status"] == MonthlyAssessment.STATUS_REJECTED]
        self.assertEqual(len(rej), 1)
        self.assertIn("Deduction sheet", rej[0]["action_remarks"])

    def test_duplicate_postings_detected(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        seen = {}
        for e in data["items"]:
            k = (e["direction"], e["source_type"], float(e["amount"]), e["description"])
            seen[k] = seen.get(k, 0) + 1
        dupes = {k: n for k, n in seen.items() if n > 1}
        self.assertEqual(len(dupes), 1)
        (_, _, amt, _), n = next(iter(dupes.items()))
        self.assertEqual(n, 2)
        self.assertEqual(amt * (n - 1), 13300.0)

    def test_approved_vs_released_variance_arithmetic(self):
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        approved = float(rows[0]["validated_aid_amount"] or 0)
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        released = sum(float(e["amount"]) for e in data["items"]
                       if e["direction"] == "outflow" and e["source_type"] == "medical_aid")
        # Two identical 13300 postings released against 14400 approved.
        self.assertEqual(released, 26600.0)
        self.assertEqual(round(approved - released, 2), -12200.0)
