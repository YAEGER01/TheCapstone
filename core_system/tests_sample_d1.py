"""D1/D2 data contract (REPORTS.MD :: Cash Donation / Donation Disbursement).

Both sheets read one-off fund movements (other-transaction inflows for D1,
outflows for D2): donor/payee + purpose parsed from the booking description,
receiver/recorder and reference carried through. Outflows are not linked to
specific donations, so D2's linked-donation column reads blank.
"""
import re
from decimal import Decimal

from django.test import TestCase

from core_system.models import FundTransaction, Member
from core_system.tests import TreasurerApiClientMixin


def split_counterparty(desc):
    m = re.match(r"^(From|To)\s+(.+?)\s+—\s*(.*)$", desc or "")
    if not m:
        return {"who": "", "note": (desc or "").strip()}
    return {"who": m.group(2).strip(), "note": m.group(3).strip()}


class SampleD1D2DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        Member.objects.create(
            full_name="Treasurer Test Member", department="College B",
            employment_status="Active", membership_status="Permanent",
            date_joined="2026-01-05",
        )
        FundTransaction.objects.create(
            direction="inflow", amount=Decimal("5000"), source_type="other_transaction",
            source_id=0, description="From Donor A — Association activities",
            reference_number="OR-1415", recorded_by_user_id_FK=self.officer,
        )
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("1850"), source_type="other_transaction",
            source_id=0, description="To Sample supplier — Meeting refreshments",
            reference_number="OTH-000001", recorded_by_user_id_FK=self.officer,
        )

    def test_list_entries_carry_d1_d2_fields(self):
        data = self.client.get("/api/treasurer/other-transactions/list/").json()
        self.assertTrue(data["ok"])
        ins = [e for e in data["entries"] if e["direction"] == "inflow"
               and e["source"] == "other_transaction"]
        outs = [e for e in data["entries"] if e["direction"] == "outflow"
                and e["source"] == "other_transaction"]
        self.assertEqual(len(ins), 1)
        self.assertEqual(len(outs), 1)
        for key in ("donor", "description", "reference_number", "recorded_by",
                    "amount", "sort_at", "direction", "source"):
            self.assertIn(key, ins[0])

    def test_donor_purpose_parse(self):
        parts = split_counterparty("From Donor A — Association activities")
        self.assertEqual(parts, {"who": "Donor A", "note": "Association activities"})
        parts = split_counterparty("To Sample supplier — Meeting refreshments")
        self.assertEqual(parts, {"who": "Sample supplier", "note": "Meeting refreshments"})

    def test_d1_total_and_d2_total(self):
        data = self.client.get("/api/treasurer/other-transactions/list/").json()
        ins = [e for e in data["entries"] if e["direction"] == "inflow"]
        outs = [e for e in data["entries"] if e["direction"] == "outflow"]
        self.assertEqual(sum(float(e["amount"]) for e in ins), 5000.0)
        self.assertEqual(sum(float(e["amount"]) for e in outs), 1850.0)
