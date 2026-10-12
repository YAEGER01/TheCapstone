"""F5 data contract (REPORTS.MD :: Incomplete Documentation Report).

F5 flags live records missing required proof: medical claims with no hospital
bill, death claims without a complete document set, and one-off outflows with
no receipt attached.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    Claimant,
    DeathAid,
    FundTransaction,
    MedicalAid,
    Member,
)
from core_system.tests import TreasurerApiClientMixin


class SampleF5DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Mercado, Fernando S.", employee_id="MEM-0025", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        MedicalAid.objects.create(
            member_id_FK=self.member, request_date=date(2026, 9, 30),
            hospital_name="", hospital_bill_amount=Decimal("0"),
            requested_amount=Decimal("0"), claim_year=2026,
            document_status="Pending", policy_record_status="Recorded",
            validated_aid_amount=Decimal("0"), status="Pending",
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
            document_status="Pending", status="Pending",
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("1850"), source_type="other_transaction",
            source_id=0, description="To Sample supplier — Meeting refreshments",
            reference_number="OTH-000001", recorded_by_user_id_FK=self.officer,
        )

    def test_medical_without_bill_flagged(self):
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        missing = [a for a in rows if float(a["bill"] or 0) <= 0]
        self.assertEqual(len(missing), 1)

    def test_death_without_complete_docs_flagged(self):
        import re
        deaths = self.client.get("/api/treasurer/death-aids/list/").json()["death_aids"]
        missing = [a for a in deaths
                   if not re.search(r"complete|verif|approv", str(a["document_status"] or ""), re.I)]
        self.assertEqual(len(missing), 1)

    def test_outflow_without_proof_flagged(self):
        data = self.client.get("/api/treasurer/other-transactions/list/").json()
        outs = [e for e in data["entries"] if e["direction"] == "outflow"
                and e["source"] == "other_transaction"]
        self.assertEqual(len(outs), 1)
        self.assertFalse(outs[0]["has_proof"])
