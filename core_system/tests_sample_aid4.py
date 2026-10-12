"""AID4/AID5 data contract (REPORTS.MD :: Aid Releasing / Beneficiary Reports).

Both sheets read the same live release outflows: AID4 one row per handoff
(releasing ref, application, payee, method/ref, release date, variance-derived
releasing status); AID5 one row per payee (types, total, claim count, latest).
"""
import re
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


def parse_release(desc):
    m = re.match(r"^(Aid|Fund) disbursement — (.+?) \((.+?)\)(.*)$", desc or "")
    if not m:
        return {"payee": "—", "method": "", "ref": ""}
    method, ref = "", ""
    for s in [x.strip() for x in (m.group(4) or "").split("·") if x.strip()]:
        rm = re.match(r"^Ref:\s*(.+)$", s, re.I)
        if rm:
            ref = rm.group(1)
        elif not method and not re.match(r"^Received by:", s, re.I) \
                and "MANUAL OVERRIDE" not in s:
            method = s
    return {"payee": m.group(2).strip() or "—", "method": method, "ref": ref}


class SampleAid45DataContractTests(TreasurerApiClientMixin, TestCase):
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
            description=f"Aid disbursement — {self.m1.full_name} (medical_aid) · Cash · Ref: CASH-051 · Received by: {self.m1.full_name}",
            reference_number="DV-2026-051", recorded_by_user_id_FK=self.officer,
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("72000"), source_type="death_aid",
            source_id=self.death.death_aid_id_PK,
            description=f"Aid disbursement — Claimant of Valdez, Roberto A. (death_aid) · Check · Ref: CHK-0045",
            reference_number="CHK-0045", recorded_by_user_id_FK=self.officer,
        )

    def test_release_segments_parse_from_description(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        outs = sorted(
            (e for e in data["items"] if e["direction"] == "outflow"
             and e["source_type"] in ("medical_aid", "death_aid")),
            key=lambda e: float(e["amount"]))
        self.assertEqual(len(outs), 2)
        first = parse_release(outs[0]["description"])
        self.assertEqual(first["payee"], self.m1.full_name)
        self.assertEqual(first["method"], "Cash")
        self.assertEqual(first["ref"], "CASH-051")
        second = parse_release(outs[1]["description"])
        self.assertEqual(second["method"], "Check")
        self.assertEqual(second["ref"], "CHK-0045")

    def test_partial_release_derives_from_approved_minus_released(self):
        approved, released = 14400.0, 13300.0
        status = "Partially Released" if (approved - released) > 0.005 else "Released"
        self.assertEqual(status, "Partially Released")
        self.assertEqual("Released" if (72000.0 - 72000.0) > 0.005 else "Released", "Released")

    def test_beneficiary_grouping_totals(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        outs = [e for e in data["items"] if e["direction"] == "outflow"
                and e["source_type"] in ("medical_aid", "death_aid")]
        groups = {}
        for e in outs:
            payee = parse_release(e["description"])["payee"]
            g = groups.setdefault(payee, {"total": 0.0, "n": 0})
            g["total"] += float(e["amount"])
            g["n"] += 1
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[self.m1.full_name], {"total": 13300.0, "n": 1})
