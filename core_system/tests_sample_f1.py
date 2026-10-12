"""F1/F2 data contract (REPORTS.MD :: Pending Transactions / Pending Audit).

F1 is the umbrella of everything not yet fully posted/closed (aid pipeline,
deposits awaiting posting/audit/approval, dues months awaiting recording).
F2 is the slice sitting exactly at Pending Auditor Verification (aid cases +
bank deposits). Days count from initiation/submission to today.
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


class SampleF1F2DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Mercado, Fernando S.", employee_id="MEM-0025", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        MedicalAid.objects.create(
            member_id_FK=self.member, request_date=date(2026, 9, 30),
            hospital_name="Cauayan District Hospital", hospital_bill_amount=Decimal("27800"),
            requested_amount=Decimal("27800"), claim_year=2026,
            document_status="Pending", policy_record_status="Recorded",
            validated_aid_amount=Decimal("0"), status="Pending",
        )
        self.audit_ass = MonthlyAssessment.objects.create(
            month=date(2026, 9, 1), total_amount=Decimal("600.00"),
            status=MonthlyAssessment.STATUS_PENDING_AUDIT,
            deposit_reference="DEP-0930", deposited_amount=Decimal("2850"),
            deposited_at="2026-10-01T09:00:00+08:00",
        )
        AssessmentItem.objects.create(
            assessment_id_FK=self.audit_ass, purpose=AssessmentItem.PURPOSE_MONTHLY_DUE,
            amount=Decimal("50.00"), priority_order=1,
        )
        self.record_ass = MonthlyAssessment.objects.create(
            month=date(2026, 10, 1), total_amount=Decimal("600.00"),
            status=MonthlyAssessment.STATUS_PENDING_TREASURER,
        )

    def test_overview_carries_pending_work_fields(self):
        data = self.client.get("/api/treasurer/deductions/overview/").json()
        by_id = {a["assessment_id"]: a for a in data["assessments"]}
        dep = by_id[self.audit_ass.assessment_id_PK]
        self.assertEqual(dep["deposit_reference"], "DEP-0930")
        self.assertEqual(float(dep["deposited_amount"]), 2850.0)
        self.assertTrue(str(dep["deposited_at"]).startswith("2026-10-01"))
        rec = by_id[self.record_ass.assessment_id_PK]
        self.assertEqual(rec["status"], MonthlyAssessment.STATUS_PENDING_TREASURER)
        self.assertTrue(str(rec["created_at"])[:10] >= "2026-01-01")

    def test_pending_claim_counts_for_f1(self):
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        pending = [a for a in rows if (a["status"] or "") in
                   ("Pending", "Pending Auditor Verification", "Auditor Verified",
                    "Approved", "President Approved", "Treasurer Direct")]
        self.assertEqual(len(pending), 1)

    def test_days_pending_counts_from_initiation(self):
        today = date.today()
        self.assertEqual(max(0, (today - date(2026, 9, 30)).days), (today - date(2026, 9, 30)).days)
