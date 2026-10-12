"""H6/H7 data contract (REPORTS.MD :: Donation / Disbursement Ledgers).

H6 tracks each donation receipt with disbursed-to-date and remainder (no
donation→disbursement linkage is tracked, so disbursed reads zero). H7 is the
voucher-level chronological record of every disbursement.
"""
from decimal import Decimal

from django.test import TestCase

from core_system.models import FundTransaction, Member
from core_system.tests import TreasurerApiClientMixin


class SampleH6H7DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        Member.objects.create(
            full_name="Treasurer Test Member", department="College B",
            employment_status="Active", membership_status="Permanent",
            date_joined="2026-01-05",
        )
        FundTransaction.objects.create(
            direction="inflow", amount=Decimal("2000"), source_type="other_transaction",
            source_id=0, description="From Sample Donor B — Medical aid support",
            reference_number="OR-1005", recorded_by_user_id_FK=self.officer,
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("72000"), source_type="death_aid",
            source_id=1, description="Aid disbursement — X (death_aid) · Check · Ref: CHK-0045",
            reference_number="CHK-0045", recorded_by_user_id_FK=self.officer,
        )

    def test_donation_receipts_listed(self):
        data = self.client.get("/api/treasurer/other-transactions/list/").json()
        ins = [e for e in data["entries"] if e["direction"] == "inflow"
               and e["source"] == "other_transaction"]
        self.assertEqual(len(ins), 1)
        self.assertEqual(float(ins[0]["amount"]), 2000.0)
        self.assertEqual(ins[0]["donor"], "Sample Donor B")

    def test_voucher_reference_prefers_bank_ref(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        outs = [e for e in data["items"] if e["direction"] == "outflow"]
        self.assertEqual(len(outs), 1)
        import re
        ref = outs[0]["reference_number"] or ""
        shown = ref if re.search(r"CHK|BANK", ref, re.I) else "—"
        self.assertEqual(shown, "CHK-0045")

    def test_h7_total_equals_outflows(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        outs = [e for e in data["items"] if e["direction"] == "outflow"]
        self.assertEqual(sum(float(e["amount"]) for e in outs), 72000.0)
