"""AID9/AID10/AID11 data contract (REPORTS.MD).

AID9 is the as-of statement per beneficiary over release outflows; AID10 the
period release totals by type; AID11 the approved-but-unreleased remainders
(approved − released > 0, approval dates untracked).
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


class SampleAid91011DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.m1 = Member.objects.create(
            full_name="Navarro, Rosario H.", employee_id="MEM-0023", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        self.m2 = Member.objects.create(
            full_name="Valdez, Roberto A.", employee_id="MEM-0022", department="College B",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        self.med = MedicalAid.objects.create(
            member_id_FK=self.m1, request_date=date(2026, 9, 14),
            hospital_name="Cauayan Medical Center", hospital_bill_amount=Decimal("62500"),
            requested_amount=Decimal("62500"), claim_year=2026,
            document_status="Complete", policy_record_status="Recorded",
            validated_aid_amount=Decimal("14400"), status="Approved",
        )
        claimant = Claimant.objects.create(
            member_id_FK=self.m2, full_name="Claimant of Valdez, Roberto A.",
            relationship_to_member="Spouse", relationship_group="spouse",
            authorization_status="Authorized",
        )
        self.death = DeathAid.objects.create(
            member_id_FK=self.m2, claimant_id_FK=claimant,
            claim_date=date(2026, 9, 1), claim_type="Death Aid",
            deceased_name="Valdez, Roberto A.", relationship_to_member="Spouse",
            relationship_group="spouse", benefit_amount=Decimal("72000"),
            document_status="Complete", status="Approved",
        )
        # Partial medical release (approved 14400, released 13300).
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("13300"), source_type="medical_aid",
            source_id=self.med.medical_aid_id_PK,
            description=f"Aid disbursement — {self.m1.full_name} (medical_aid) · Cash",
            reference_number="DV-2026-051", recorded_by_user_id_FK=self.officer,
        )
        # Full death release to the claimant.
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("72000"), source_type="death_aid",
            source_id=self.death.death_aid_id_PK,
            description="Aid disbursement — Claimant of Valdez, Roberto A. (death_aid) · Check · Ref: CHK-0045",
            reference_number="CHK-0045", recorded_by_user_id_FK=self.officer,
        )

    def _outs(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        return [e for e in data["items"] if e["direction"] == "outflow"
                and e["source_type"] in ("medical_aid", "death_aid")]

    def test_aid9_beneficiary_totals(self):
        outs = self._outs()
        med_out = next(e for e in outs if e["source_type"] == "medical_aid")
        self.assertEqual(float(med_out["amount"]), 13300.0)
        death_out = next(e for e in outs if e["source_type"] == "death_aid")
        self.assertEqual(float(death_out["amount"]), 72000.0)

    def test_aid10_totals_by_type(self):
        outs = self._outs()
        by_type = {}
        for e in outs:
            by_type.setdefault(e["source_type"], {"n": 0, "tot": 0.0})
            by_type[e["source_type"]]["n"] += 1
            by_type[e["source_type"]]["tot"] += float(e["amount"])
        self.assertEqual(by_type["medical_aid"], {"n": 1, "tot": 13300.0})
        self.assertEqual(by_type["death_aid"], {"n": 1, "tot": 72000.0})

    def test_aid11_remainder_keeps_partial_drops_full(self):
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        approved = float(rows[0]["validated_aid_amount"] or 0)
        released = sum(float(e["amount"]) for e in self._outs()
                       if e["source_type"] == "medical_aid")
        self.assertEqual(round(approved - released, 2), 1100.0)
        deaths = self.client.get("/api/treasurer/death-aids/list/").json()["death_aids"]
        d_approved = float(deaths[0]["benefit_amount"])
        d_released = sum(float(e["amount"]) for e in self._outs()
                         if e["source_type"] == "death_aid")
        self.assertLessEqual(round(d_approved - d_released, 2), 0.005)
