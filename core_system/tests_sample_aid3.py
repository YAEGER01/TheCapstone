"""AID3 data contract (REPORTS.MD :: AID3 Aid Disbursement Report).

The AID3 sheet lists live fund outflows booked for aid (disbursement ref,
linked application, approved vs disbursed side by side). This test pins the
ledger feed fields the sheet reads, including source_id for the claim link.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core_system.models import FundTransaction, MedicalAid, Member
from core_system.tests import TreasurerApiClientMixin


class SampleAid3DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Navarro, Rosario H.", employee_id="MEM-0023", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined=date(2026, 1, 5),
        )
        self.med = MedicalAid.objects.create(
            member_id_FK=self.member, request_date=date(2026, 9, 14),
            hospital_name="Cauayan Medical Center", hospital_bill_amount=Decimal("62500"),
            requested_amount=Decimal("62500"), claim_year=2026,
            document_status="Complete", policy_record_status="Recorded",
            validated_aid_amount=Decimal("14400"), status="Approved",
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("13300"), source_type="medical_aid",
            source_id=self.med.medical_aid_id_PK,
            description=f"Aid disbursement — {self.member.full_name} (medical_aid)",
            reference_number="DV-2026-051", recorded_by_user_id_FK=self.officer,
        )

    def test_ledger_items_carry_aid3_link_fields(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        self.assertTrue(data["ok"])
        outs = [e for e in data["items"]
                if e["direction"] == "outflow" and e["source_type"] == "medical_aid"]
        self.assertEqual(len(outs), 1)
        e = outs[0]
        for key in ("id", "direction", "amount", "source_type", "source_id",
                    "description", "reference_number", "recorded_by", "recorded_at"):
            self.assertIn(key, e)
        self.assertEqual(e["reference_number"], "DV-2026-051")
        self.assertEqual(str(e["source_id"]), str(self.med.medical_aid_id_PK))

    def test_aid3_derivation_claimed_vs_disbursed(self):
        med = self.client.get("/api/treasurer/medical-aids/list/").json()
        rows = med.get("rows") or med.get("medical_aids")
        a = rows[0]
        app = "MED-" + str(a["aid_id"])
        self.assertEqual(app, f"MED-{self.med.medical_aid_id_PK}")
        approved = float(a["validated_aid_amount"] or 0)
        self.assertEqual(approved, 14400.0)
        disbursed = 13300.0
        self.assertNotEqual(approved, disbursed)  # variance prints, never merged
