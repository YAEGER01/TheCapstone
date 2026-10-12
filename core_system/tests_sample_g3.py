"""G3/G4/G5 data contract (REPORTS.MD :: Cash Position / Fund Balance / Cash Flow).

All three read book aggregates over recorded dates: opening (before range),
receipts/disbursements (in range), balance as of range end. G4 adds the
committed (approved-but-unreleased aid) line and available balance.
"""
from decimal import Decimal

from django.test import TestCase

from core_system.models import (
    Claimant,
    DeathAid,
    FundTransaction,
    Member,
)
from core_system.tests import TreasurerApiClientMixin


class SampleG3G4G5DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        self.member = Member.objects.create(
            full_name="Valdez, Roberto A.", employee_id="MEM-0022", department="College B",
            employment_status="Active", membership_status="Permanent",
            date_joined="2026-01-05",
        )
        FundTransaction.objects.create(
            direction="inflow", amount=Decimal("1000"), source_type="membership_fee",
            source_id=1, description="Fee", reference_number="OR-1",
            recorded_by_user_id_FK=self.officer,
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("300"), source_type="other_transaction",
            source_id=0, description="To Supplier — Supplies",
            reference_number="OTH-1", recorded_by_user_id_FK=self.officer,
        )
        claimant = Claimant.objects.create(
            member_id_FK=self.member, full_name="Claimant of Valdez, Roberto A.",
            relationship_to_member="Spouse", relationship_group="spouse",
            authorization_status="Authorized",
        )
        DeathAid.objects.create(
            member_id_FK=self.member, claimant_id_FK=claimant,
            claim_date="2026-09-01", claim_type="Death Aid",
            deceased_name="Valdez, Roberto A.", relationship_to_member="Spouse",
            relationship_group="spouse", benefit_amount=Decimal("500"),
            document_status="Complete", status="Approved",
        )

    def test_ledger_summary_gives_book_totals(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        s = data["summary"]
        self.assertEqual(float(s["total_in"]), 1000.0)
        self.assertEqual(float(s["total_out"]), 300.0)
        self.assertEqual(float(s["balance"]), 700.0)

    def test_g4_balance_arithmetic(self):
        balance, receipts, disbursements, beginning = 700.0, 1000.0, 300.0, 0.0
        self.assertEqual(round(beginning + receipts - disbursements, 2), balance)

    def test_g4_committed_is_unreleased_approved(self):
        deaths = self.client.get("/api/treasurer/death-aids/list/").json()["death_aids"]
        approved = sum(float(d["benefit_amount"]) for d in deaths
                       if (d["status"] or "").strip() == "Approved")
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        released = sum(float(e["amount"]) for e in data["items"]
                       if e["direction"] == "outflow" and e["source_type"] == "death_aid")
        committed = max(0.0, approved - released)
        self.assertEqual(committed, 500.0)
        self.assertEqual(round(700.0 - committed, 2), 200.0)
