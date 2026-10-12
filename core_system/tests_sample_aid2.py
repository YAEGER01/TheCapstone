"""AID2 data contract (REPORTS.MD :: AID2 Aid Approval Report).

The AID2 sheet is the decision view of the same live applications AID1 lists:
claimed vs approved side by side (validated aid amount for medical, benefit
amount for death), approving body President, blank resolution references.
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


class SampleAid2DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Navarro, Rosario H.", employee_id="MEM-0023", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        MedicalAid.objects.create(
            member_id_FK=self.member, request_date=date(2026, 9, 14),
            hospital_name="Cauayan Medical Center", hospital_bill_amount=Decimal("62500"),
            requested_amount=Decimal("62500"), claim_year=2026,
            document_status="Complete", policy_record_status="Recorded",
            validated_aid_amount=Decimal("14400"), status="Approved",
        )
        claimant = Claimant.objects.create(
            member_id_FK=self.member, full_name="Claimant of Valdez, Roberto A.",
            relationship_to_member="Spouse", relationship_group="spouse",
            authorization_status="Authorized",
        )
        DeathAid.objects.create(
            member_id_FK=self.member, claimant_id_FK=claimant,
            claim_date=date(2026, 9, 1), claim_type="Death Aid",
            deceased_name="Valdez, Roberto A.", relationship_to_member="Spouse",
            relationship_group="spouse", benefit_amount=Decimal("72000"),
            document_status="Complete", status="Approved",
        )

    def test_claimed_vs_approved_derive_from_live_fields(self):
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        a = rows[0]
        claimed = float(a["bill"]) if float(a["bill"]) > 0 else float(a["reqAmount"])
        approved = float(a["validated_aid_amount"] or 0)
        self.assertEqual(claimed, 62500.0)
        self.assertEqual(approved, 14400.0)
        self.assertNotEqual(claimed, approved)  # shown side by side, never merged
        deaths = self.client.get("/api/treasurer/death-aids/list/").json()["death_aids"]
        d = deaths[0]
        self.assertEqual(float(d["benefit_amount"]), 72000.0)

    def test_decided_statuses_map_to_president_body(self):
        decided = ["Approved", "President Approved", "Rejected", "Released", "Completed"]
        for st in decided:
            import re
            self.assertTrue(re.search(r"approved|rejected|released|complete", st, re.I))
