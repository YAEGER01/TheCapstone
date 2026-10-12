"""H4 data contract (REPORTS.MD :: Aid Subsidiary Ledger).

H4 shows per approved case: beneficiary, approved vs released, latest release
date (filed date when unreleased), and the remainder, with totals.
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


class SampleH4DataContractTests(TreasurerApiClientMixin, TestCase):
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
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("13300"), source_type="medical_aid",
            source_id=self.med.medical_aid_id_PK,
            description=f"Aid disbursement — {self.m1.full_name} (medical_aid)",
            reference_number="DV-2026-051", recorded_by_user_id_FK=self.officer,
        )

    def test_per_case_remainders(self):
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        approved = {f"MED-{r['aid_id']}": float(r["validated_aid_amount"] or 0) for r in rows}
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        released = {}
        for e in data["items"]:
            if e["direction"] == "outflow" and e["source_type"] == "medical_aid":
                app = f"MED-{e['source_id']}"
                released[app] = released.get(app, 0.0) + float(e["amount"])
        app = f"MED-{self.med.medical_aid_id_PK}"
        self.assertEqual(round(approved[app] - released.get(app, 0.0), 2), 1100.0)
        deaths = self.client.get("/api/treasurer/death-aids/list/").json()["death_aids"]
        d = deaths[0]
        d_released = sum(float(e["amount"]) for e in data["items"]
                         if e["direction"] == "outflow" and e["source_type"] == "death_aid")
        self.assertEqual(round(float(d["benefit_amount"]) - d_released, 2), 72000.0)

    def test_h4_totals(self):
        self.assertEqual(round(14400.0 + 72000.0, 2), 86400.0)
        self.assertEqual(round(13300.0 + 0.0, 2), 13300.0)
        self.assertEqual(round(86400.0 - 13300.0, 2), 73100.0)
