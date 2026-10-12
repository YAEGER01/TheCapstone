"""G1/G2 data contract (REPORTS.MD :: Withdrawal / Bank Withdrawal Summary).

G1 lists recorded one-off outflows (bank-level withdrawals): date, reference,
amount, purpose, recorder, proof-backed approval state, and the running
one-off sub-ledger balance. G2 rolls withdrawals by month.
"""
from decimal import Decimal

from django.test import TestCase

from core_system.models import FundTransaction, Member
from core_system.tests import TreasurerApiClientMixin


class SampleG1G2DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        Member.objects.create(
            full_name="Treasurer Test Member", department="College B",
            employment_status="Active", membership_status="Permanent",
            date_joined="2026-01-05",
        )
        FundTransaction.objects.create(
            direction="inflow", amount=Decimal("20000"), source_type="other_transaction",
            source_id=0, description="From Donor B — Cash for aid vouchers",
            reference_number="OR-1005", recorded_by_user_id_FK=self.officer,
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("20000"), source_type="other_transaction",
            source_id=0, description="To Cashier — Cash for aid and donation vouchers",
            reference_number="BANK-WD-0917", recorded_by_user_id_FK=self.officer,
        )

    def test_withdraw_entries_carry_g1_fields(self):
        data = self.client.get("/api/treasurer/other-transactions/list/").json()
        outs = [e for e in data["entries"] if e["direction"] == "outflow"
                and e["source"] == "other_transaction"]
        self.assertEqual(len(outs), 1)
        w = outs[0]
        for key in ("date", "sort_at", "reference_number", "amount", "description",
                    "recorded_by", "has_proof", "action"):
            self.assertIn(key, w)
        self.assertEqual(w["action"], "withdraw")
        self.assertEqual(w["reference_number"], "BANK-WD-0917")

    def test_running_balance_nets_inflows_minus_outflows(self):
        data = self.client.get("/api/treasurer/other-transactions/list/").json()
        txns = sorted(
            (e for e in data["entries"] if e["source"] == "other_transaction"),
            key=lambda e: str(e["sort_at"] or e["date"]))
        run = 0.0
        for t in txns:
            amt = float(t["amount"])
            run += amt if t["direction"] == "inflow" else -amt
        self.assertEqual(round(run, 2), 0.0)

    def test_g2_rollup_counts_and_sums(self):
        data = self.client.get("/api/treasurer/other-transactions/list/").json()
        outs = [e for e in data["entries"] if e["direction"] == "outflow"
                and e["source"] == "other_transaction"]
        self.assertEqual(len(outs), 1)
        self.assertEqual(sum(float(e["amount"]) for e in outs), 20000.0)
