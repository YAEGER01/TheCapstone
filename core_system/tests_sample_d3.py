"""D3/D4 data contract (REPORTS.MD :: General Disbursement / Summary).

D3 lists every fund outflow in range (payee + purpose parsed from the booking
description, recorder/method, reference, date). D4 rolls the same outflows by
purpose category within each month.
"""
import re
from decimal import Decimal

from django.test import TestCase

from core_system.models import FundTransaction, MedicalAid, Member
from core_system.tests import TreasurerApiClientMixin


def split_outflow(source_type, desc):
    st = (source_type or "").lower()
    m = re.match(r"^(Aid|Fund) disbursement — (.+?) \((.+?)\)(.*)$", desc or "")
    if m:
        return {"payee": m.group(2).strip(),
                "purpose": "Medical Aid" if st == "medical_aid" else "Death Aid"}
    m = re.match(r"^(From|To)\s+(.+?)\s+—\s*(.*)$", desc or "")
    if m:
        return {"payee": m.group(2).strip(), "purpose": (m.group(3).strip() or "—")}
    return {"payee": "—", "purpose": (desc or "").strip() or "—"}


def category_of(source_type, desc):
    st = (source_type or "").lower()
    if st in ("medical_aid", "death_aid", "aid_post_payment"):
        return "Aid (Medical Aid, Death Aid)"
    if re.search(r"retire|death donation|token", (desc or "").lower()):
        return "Retirement and Death Donation"
    return "Other charge to the Fund"


class SampleD3D4DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Navarro, Rosario H.", employee_id="MEM-0023", department="College D",
            employment_status="Active", membership_status="Permanent",
            date_joined="2026-01-05",
        )
        med = MedicalAid.objects.create(
            member_id_FK=self.member, request_date="2026-09-14",
            hospital_name="Cauayan Medical Center", hospital_bill_amount=Decimal("62500"),
            requested_amount=Decimal("62500"), claim_year=2026,
            document_status="Complete", policy_record_status="Recorded",
            validated_aid_amount=Decimal("14400"), status="Approved",
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("13300"), source_type="medical_aid",
            source_id=med.medical_aid_id_PK,
            description=f"Aid disbursement — {self.member.full_name} (medical_aid) · Cash",
            reference_number="DV-2026-051", recorded_by_user_id_FK=self.officer,
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("1850"), source_type="other_transaction",
            source_id=0, description="To Sample supplier — Meeting refreshments",
            reference_number="OTH-000001", recorded_by_user_id_FK=self.officer,
        )

    def test_d3_payee_purpose_parse(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        outs = sorted((e for e in data["items"] if e["direction"] == "outflow"),
                      key=lambda e: float(e["amount"]))
        self.assertEqual(len(outs), 2)
        small = split_outflow(outs[0]["source_type"], outs[0]["description"])
        self.assertEqual(small["payee"], "Sample supplier")
        self.assertEqual(small["purpose"], "Meeting refreshments")
        big = split_outflow(outs[1]["source_type"], outs[1]["description"])
        self.assertEqual(big["payee"], self.member.full_name)
        self.assertEqual(big["purpose"], "Medical Aid")

    def test_d4_category_buckets_and_total(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        outs = [e for e in data["items"] if e["direction"] == "outflow"]
        buckets = {}
        for e in outs:
            c = category_of(e["source_type"], e["description"])
            b = buckets.setdefault(c, {"n": 0, "tot": 0.0})
            b["n"] += 1
            b["tot"] += float(e["amount"])
        self.assertEqual(buckets["Aid (Medical Aid, Death Aid)"], {"n": 1, "tot": 13300.0})
        self.assertEqual(buckets["Other charge to the Fund"], {"n": 1, "tot": 1850.0})
        self.assertEqual(sum(b["tot"] for b in buckets.values()), 15150.0)
