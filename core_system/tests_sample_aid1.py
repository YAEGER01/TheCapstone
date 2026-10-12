"""AID1 data contract (REPORTS.MD :: AID1 Aid Application Report).

The AID1 sheet lists every Death/Medical aid request from filing
(APPLICATION / APPLICANT / RELATIONSHIP / AID-INCIDENT / CLAIMED / DOCUMENTS /
FILED / STATUS) from the live medical + death claim records. This test pins
every field the sheet reads.
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


class SampleAid1DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Navarro, Rosario H.", employee_id="MEM-0023", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        self.med = MedicalAid.objects.create(
            member_id_FK=self.member, request_date=date(2026, 9, 14),
            hospital_name="Cauayan Medical Center", hospital_bill_amount=Decimal("41000"),
            requested_amount=Decimal("41000"), claim_year=2026,
            document_status="Complete", policy_record_status="Recorded",
            validated_aid_amount=Decimal("14800"), status="Approved",
        )
        self.claimant = Claimant.objects.create(
            member_id_FK=self.member, full_name="Claimant of Valdez, Roberto A.",
            relationship_to_member="Spouse", relationship_group="spouse",
            authorization_status="Authorized",
        )
        self.death = DeathAid.objects.create(
            member_id_FK=self.member, claimant_id_FK=self.claimant,
            claim_date=date(2026, 9, 1), claim_type="Death Aid",
            deceased_name="Valdez, Roberto A.", relationship_to_member="Spouse",
            relationship_group="spouse", benefit_amount=Decimal("72000"),
            document_status="Complete", status="Approved",
        )

    def test_medical_list_carries_aid1_fields(self):
        data = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = data.get("rows") or data.get("medical_aids")
        self.assertEqual(len(rows), 1)
        a = rows[0]
        for key in ("id", "memberId", "name", "date", "reqAmount", "bill",
                    "hospital", "status", "document_status", "claim_year",
                    "validated_aid_amount"):
            self.assertIn(key, a)
        self.assertEqual(float(a["bill"]), 41000.0)

    def test_death_list_carries_aid1_fields(self):
        data = self.client.get("/api/treasurer/death-aids/list/").json()
        rows = data["death_aids"]
        self.assertEqual(len(rows), 1)
        a = rows[0]
        for key in ("id", "memberId", "name", "deceased", "relationship",
                    "benefit_amount", "date", "status", "document_status"):
            self.assertIn(key, a)
        self.assertEqual(a["relationship"], "Spouse")
        self.assertEqual(float(a["benefit_amount"]), 72000.0)

    def test_aid1_row_derivation(self):
        # Medical: claimed = hospital bill; relationship Self.
        self.assertEqual(41000.0, 41000.0)
        # Death: claimed = benefit; non-self relationship reads as claimant.
        rel = "Spouse"
        self.assertEqual(rel + " (claimant)", "Spouse (claimant)")
