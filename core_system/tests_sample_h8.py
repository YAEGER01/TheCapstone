"""H8/H9/H10 data contract (REPORTS.MD :: Financial Summaries).

Monthly / quarterly / annual rollups of the book: beginning + receipts −
disbursements = ending, over the calendar span. Quarterly/annual sheets add
the budget variance line (empty budget reads as no record, per the base file).
"""
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from core_system.models import FundTransaction, Member
from core_system.tests import TreasurerApiClientMixin


class SampleH8H9H10DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        Member.objects.create(
            full_name="Treasurer Test Member", department="College B",
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

    def test_month_span_aggregates(self):
        # Fixed September dates: UTC storage vs local date can differ around
        # month boundaries, so fixtures pin their recorded dates.
        FundTransaction.objects.filter(reference_number="OR-1").update(
            recorded_at=datetime(2026, 9, 5, tzinfo=dt_timezone.utc))
        FundTransaction.objects.filter(reference_number="OTH-1").update(
            recorded_at=datetime(2026, 9, 6, tzinfo=dt_timezone.utc))
        data = self.client.get("/api/fund-ledger/?per_page=100").json()
        in_span = sum(float(e["amount"]) for e in data["items"]
                      if e["direction"] == "inflow" and str(e["recorded_at"])[:7] == "2026-09")
        out_span = sum(float(e["amount"]) for e in data["items"]
                       if e["direction"] == "outflow" and str(e["recorded_at"])[:7] == "2026-09")
        before = sum(float(e["amount"]) if e["direction"] == "inflow" else -float(e["amount"])
                     for e in data["items"] if str(e["recorded_at"])[:10] < "2026-09-01")
        self.assertEqual(in_span, 1000.0)
        self.assertEqual(out_span, 300.0)
        self.assertEqual(round(before + in_span - out_span, 2), 700.0)

    def test_budget_lines_endpoint_ok(self):
        year = timezone.localdate().year
        data = self.client.get(
            "/api/reports/association/budget/lines/", {"year": year}).json()
        self.assertTrue(data["ok"])
        self.assertIn("lines", data)
