"""H5 data contract (REPORTS.MD :: Cash Ledger).

H5 lists every cash movement chronologically with the running balance from
the opening before the range, plus receipt/disbursement totals.
"""
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

from django.test import TestCase

from core_system.models import FundTransaction, Member
from core_system.tests import TreasurerApiClientMixin


class SampleH5DataContractTests(TreasurerApiClientMixin, TestCase):
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
        old = FundTransaction.objects.create(
            direction="inflow", amount=Decimal("2000"), source_type="membership_fee",
            source_id=1, description="Old fee",
            reference_number="OR-0001", recorded_by_user_id_FK=self.officer,
        )
        FundTransaction.objects.filter(pk=old.pk).update(
            recorded_at=datetime(2026, 1, 5, tzinfo=dt_timezone.utc))
        FundTransaction.objects.create(
            direction="outflow", amount=Decimal("1850"), source_type="other_transaction",
            source_id=0, description="To Sample supplier — Meeting refreshments",
            reference_number="OTH-000001", recorded_by_user_id_FK=self.officer,
        )

    def test_opening_captures_pre_range_movements(self):
        # Fixed-date comparison (no today()): UTC storage vs local date can
        # differ around midnight, so the fixture pins every movement's date.
        FundTransaction.objects.filter(reference_number="OR-1415").update(
            recorded_at=datetime(2026, 6, 1, tzinfo=dt_timezone.utc))
        FundTransaction.objects.filter(reference_number="OTH-000001").update(
            recorded_at=datetime(2026, 6, 2, tzinfo=dt_timezone.utc))
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        opening = sum(float(e["amount"]) if e["direction"] == "inflow" else -float(e["amount"])
                      for e in data["items"]
                      if str(e["recorded_at"])[:10] < "2026-03-01")
        self.assertEqual(round(opening, 2), 2000.0)

    def test_running_ends_at_book_balance(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        self.assertEqual(float(data["summary"]["balance"]), 5150.0)
        ordered = sorted(data["items"], key=lambda e: str(e["recorded_at"]))
        run = 0.0
        for e in ordered:
            run += float(e["amount"]) if e["direction"] == "inflow" else -float(e["amount"])
        self.assertEqual(round(run, 2), 5150.0)

    def test_items_carry_cash_ledger_columns(self):
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        for key in ("recorded_at", "description", "direction", "amount", "reference_number"):
            self.assertIn(key, data["items"][0])
