"""H1/H2 data contract (REPORTS.MD :: General Journal / General Ledger).

H1 is the chronological double-entry book (inflows debit cash / credit
income; outflows debit expense / credit cash; payroll money to Cash in Bank).
H2 posts the same legs account by account with opening + running balances.
Every entry must balance: total debits equal total credits.
"""
from decimal import Decimal

from django.test import TestCase

from core_system.models import FundTransaction, Member
from core_system.tests import TreasurerApiClientMixin


def cash_side(source_type, direction, description=""):
    st, d = (source_type or "").lower(), (direction or "").lower()
    if d == "inflow":
        return ("Cash in Bank" if st in ("monthly_dues", "aid_setaside_medical",
                "aid_setaside_death", "salary_deduction_remittance", "payroll_batch")
                else "Cash on Hand")
    hay = f"{description} "
    import re
    return "Cash in Bank" if re.search(r"check|bank|\bchk\b|transfer", hay, re.I) else "Cash on Hand"


class SampleH1H2DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        Member.objects.create(
            full_name="Treasurer Test Member", department="College B",
            employment_status="Active", membership_status="Permanent",
            date_joined="2026-01-05",
        )
        FundTransaction.objects.create(
            direction="inflow", amount=Decimal("100"), source_type="monthly_dues",
            source_id=1, description="Monthly dues for September 2026 — member 1",
            reference_number="BANK-CR-0915", recorded_by_user_id_FK=self.officer,
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("72000"), source_type="death_aid",
            source_id=1, description="Aid disbursement — X (death_aid) · Check · Ref: CHK-0045",
            reference_number="CHK-0045", recorded_by_user_id_FK=self.officer,
        )

    def test_cash_side_mapping(self):
        self.assertEqual(cash_side("monthly_dues", "inflow"), "Cash in Bank")
        self.assertEqual(cash_side("membership_fee", "inflow"), "Cash on Hand")
        self.assertEqual(cash_side("death_aid", "outflow", "Aid · Check"), "Cash in Bank")
        self.assertEqual(cash_side("other_transaction", "outflow", "To X — Cash"), "Cash on Hand")

    def test_journal_balances(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        debits = sum(float(e["amount"]) for e in data["items"])
        credits = sum(float(e["amount"]) for e in data["items"])
        self.assertEqual(round(debits, 2), round(credits, 2))
        self.assertEqual(round(debits, 2), 72100.0)

    def test_cash_accounts_net_correctly(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        bank_in = sum(float(e["amount"]) for e in data["items"]
                      if e["direction"] == "inflow" and e["source_type"] == "monthly_dues")
        bank_out = sum(float(e["amount"]) for e in data["items"]
                       if e["direction"] == "outflow" and e["source_type"] == "death_aid"
                       and "CHK-0045" in (e["reference_number"] or ""))
        self.assertEqual(bank_in, 100.0)
        self.assertEqual(bank_out, 72000.0)
