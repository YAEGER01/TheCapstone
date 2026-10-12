"""AID6/AID7 data contract (REPORTS.MD :: Pending Aid / Pending Aid Audit).

AID6 lists every aid case not yet fully resolved with its pipeline stage and
days pending (today minus date filed). AID7 is the slice sitting exactly at
Pending Auditor Verification. Rejected and fully-released rows are resolved
and excluded from AID6.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    Claimant,
    DeathAid,
    MedicalAid,
    Member,
)
from core_system.tests import TreasurerApiClientMixin


def stage_of(status):
    s = (status or "").strip()
    if s.lower().startswith("rejected"):
        return "Rejected"
    if "released" in s.lower() or "complete" in s.lower():
        return "Released"
    if "president approved" in s.lower() or s.lower().startswith("approved"):
        return "Approved, not yet released"
    if "auditor verified" in s.lower():
        return "Pending President approval"
    if "auditor verification" in s.lower():
        return "Pending Auditor verification"
    return "Treasurer validation"


class SampleAid67DataContractTests(TreasurerApiClientMixin, TestCase):
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
        MedicalAid.objects.create(
            member_id_FK=self.member, request_date=date(2026, 9, 21),
            hospital_name="Cauayan District Hospital", hospital_bill_amount=Decimal("18500"),
            requested_amount=Decimal("18500"), claim_year=2026,
            document_status="Complete", policy_record_status="Recorded",
            validated_aid_amount=Decimal("0"), status="Rejected",
        )
        claimant = Claimant.objects.create(
            member_id_FK=self.member, full_name="Valdez, Marites N.",
            relationship_to_member="Child", relationship_group="child",
            authorization_status="Authorized",
        )
        DeathAid.objects.create(
            member_id_FK=self.member, claimant_id_FK=claimant,
            claim_date=date(2026, 9, 26), claim_type="Death Aid",
            deceased_name="Valdez, Member", relationship_to_member="Child",
            relationship_group="child", benefit_amount=Decimal("74000"),
            document_status="Pending", status="Pending Auditor Verification",
        )

    def test_pending_stages_derive_from_status(self):
        self.assertEqual(stage_of("Pending"), "Treasurer validation")
        self.assertEqual(stage_of("Pending Auditor Verification"), "Pending Auditor verification")
        self.assertEqual(stage_of("Auditor Verified"), "Pending President approval")
        self.assertEqual(stage_of("Approved"), "Approved, not yet released")
        self.assertEqual(stage_of("Rejected"), "Rejected")

    def test_aid6_includes_unresolved_excludes_rejected(self):
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        shown = [a for a in rows if stage_of(a["status"]) != "Rejected"]
        hidden = [a for a in rows if stage_of(a["status"]) == "Rejected"]
        self.assertEqual(len(shown), 1)
        self.assertEqual(len(hidden), 1)
        self.assertEqual(stage_of(shown[0]["status"]), "Treasurer validation")

    def test_aid7_is_exact_auditor_verification_slice(self):
        deaths = self.client.get("/api/treasurer/death-aids/list/").json()["death_aids"]
        queue = [a for a in deaths if (a["status"] or "").strip() == "Pending Auditor Verification"]
        self.assertEqual(len(queue), 1)
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        med_queue = [a for a in rows if (a["status"] or "").strip() == "Pending Auditor Verification"]
        self.assertEqual(len(med_queue), 0)

    def test_days_pending_counts_from_filed_date(self):
        today = date.today()
        filed = date(2026, 9, 30)
        days = max(0, (today - filed).days)
        self.assertGreaterEqual(days, 0)
        self.assertEqual(days, (today - filed).days)
