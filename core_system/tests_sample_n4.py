"""N4 data contract (REPORTS.MD :: User Access & Activity Log).

N4 renders the system audit trail in range: actor, action, table + record,
old/new values and timestamp. This test pins the preview feed fields,
including the old/new value summaries.
"""
from django.test import TestCase

from core_system.models import GlobalAuditTrail, Member
from core_system.tests import TreasurerApiClientMixin


class SampleN4DataContractTests(TreasurerApiClientMixin, TestCase):
    def setUp(self):
        self.officer = self._login_treasurer()
        Member.objects.create(
            full_name="Activity Test Member", department="College B",
            employment_status="Active", membership_status="Permanent",
            date_joined="2026-01-05",
        )
        GlobalAuditTrail.objects.create(
            table_name="membership_fee", record_id=1, action="Created collection",
            result="Success", old_values=None, new_values={"amount": 100},
            actor_type="Officer", actor_id=self.officer.user_id_PK,
            actor_name="Treasurer Test", notes="test entry",
        )

    def test_preview_rows_carry_n4_columns(self):
        data = self.client.get(
            "/api/reports/association/audit_trail_export/preview/",
            {"limit": 50}).json()
        self.assertTrue(data["ok"])
        rows = data["report"]["rows"]
        self.assertGreaterEqual(len(rows), 1)
        row = next(r for r in rows if r["action"] == "Created collection")
        for key in ("timestamp", "actor", "actor_type", "action", "table",
                    "record_id", "result", "old_value", "new_value"):
            self.assertIn(key, row)
        self.assertEqual(row["actor"], "Treasurer Test")
        self.assertIn("100", str(row["new_value"]))

    def test_range_filters_apply(self):
        data = self.client.get(
            "/api/reports/association/audit_trail_export/preview/",
            {"date_from": "2000-01-01", "date_to": "2000-12-31", "limit": 50}).json()
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["report"]["rows"]), 0)
