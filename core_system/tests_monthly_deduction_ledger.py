"""Final approval must post each member's deduction to their ledger.

Regression: the new monthly-deduction workflow notified members ("Your
September 2026 monthly deduction of 150.00 was recorded") but never wrote
MemberLedger rows, so Monthly Deductions History stayed empty (the legacy
MonthlyDues/MembershipFee fallback only runs when the member has zero ledger
rows — and the membership fee row already exists). The member API must show
every approved month with a running balance.
"""
import json

from django.test import TestCase
from django.utils import timezone

from core_system.models import (
    Member,
    MemberAssessment,
    MemberLedger,
    MonthlyAssessment,
    OfficerUser,
)
from core_system.tests import _create_zt_verified_session, deposit_monthly_batch


class MonthlyDeductionLedgerTests(TestCase):
    def setUp(self):
        self.members = []
        for index in range(1, 4):
            self.members.append(
                Member.objects.create(
                    full_name=f"Deduction Ledger Member {index}",
                    employee_id=f"EMP-DL-{index:03d}",
                    department="Finance",
                    position="Staff",
                    membership_status="Permanent",
                    employment_status="Active",
                    member_type="Member",
                    email=f"dl_member_{index}@test.local",
                    date_joined=timezone.now().date(),
                )
            )
        self.assessment_payload = {
            "month": "2026-09",
            "items": [
                {"purpose": "monthly_due", "amount": 200, "priority_order": 1},
                {"purpose": "medical_aid_fund", "amount": 100, "priority_order": 2,
                 "recipient": "Josephine C. Cristobal"},
            ],
        }

    def _login(self, role, suffix):
        officer = OfficerUser.objects.create(
            full_name=f"{role} DL Test {suffix}",
            username=f"{role.lower()}_dl_{suffix}_{timezone.now().timestamp()}",
            password_hash="unused",
            role=role,
            account_status="Active",
        )
        session, token = _create_zt_verified_session(officer)
        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def _approve_full_workflow(self, amounts):
        self._login("President", "setup")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(self.assessment_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment_id = response.json()["assessment"]["assessment_id"]

        self._login("Treasurer", "record")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": assessment_id,
                "members": [
                    {"member_id": m.member_id_PK, "actual_deduction": amount}
                    for m, amount in zip(self.members, amounts)
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        deposit_monthly_batch(self.client, assessment_id)

        self._login("Auditor", "verify")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "ok"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        self._login("President", "final")
        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "Approved."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return assessment_id

    def _login_as_member(self, member):
        officer = self._login("Member", f"m{member.member_id_PK}")
        member.officer_user_id_FK = officer
        member.save(update_fields=["officer_user_id_FK"])
        return officer

    def test_final_approval_posts_member_ledger_rows(self):
        assessment_id = self._approve_full_workflow([300, 150, 0])

        rows = list(
            MemberLedger.objects.filter(
                reference_type="MemberAssessment",
                reference_id__in=MemberAssessment.objects.filter(
                    assessment_id_FK_id=assessment_id
                ).values_list("member_assessment_id_PK", flat=True),
            ).order_by("ledger_id_PK")
        )
        # Only members with an actual deduction get a row (300 + 150, not 0).
        self.assertEqual(len(rows), 2)
        self.assertEqual([float(r.amount) for r in rows], [300.0, 150.0])
        for row in rows:
            self.assertEqual(row.transaction_type, "monthly_dues")
            self.assertEqual(row.direction, "credit")
            self.assertIn("September 2026", row.description)
        # Each member's running balance reflects their own posting.
        self.assertEqual(float(rows[0].balance_after), 300.0)
        self.assertEqual(float(rows[1].balance_after), 150.0)

        # Re-approving is blocked by status — and could never double-post.
        self._login("President", "final2")
        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "approve"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(
            MemberLedger.objects.filter(reference_type="MemberAssessment").count(), 2
        )

    def test_excluded_members_get_carry_rows_visible_downstream(self):
        """Excluded-from-batch members must not vanish or lose their debt.

        The Treasurer's exclusion records a zero-amount row carrying the full
        expected balance, so the member stays visible to the Auditor and
        President as unpaid, the exclusion survives a return round-trip, and
        the balance carries into the next month's prior.
        """
        self._login("President", "setup")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(self.assessment_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment_id = response.json()["assessment"]["assessment_id"]

        excluded_id = self.members[2].member_id_PK
        self._login("Treasurer", "record")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": assessment_id,
                "members": [
                    {"member_id": self.members[0].member_id_PK, "actual_deduction": 300},
                    {"member_id": self.members[1].member_id_PK, "actual_deduction": 150},
                ],
                "excluded_member_ids": [excluded_id],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        rows = {
            ma.member_id_FK_id: ma
            for ma in MemberAssessment.objects.filter(assessment_id_FK_id=assessment_id)
        }
        self.assertEqual(len(rows), 3)
        excluded_row = rows[excluded_id]
        self.assertTrue(excluded_row.is_excluded)
        self.assertEqual(float(excluded_row.actual_deduction), 0.0)
        self.assertEqual(float(excluded_row.standard_assessment), 300.0)
        self.assertEqual(float(excluded_row.outstanding_balance), 300.0)
        deposit_monthly_batch(self.client, assessment_id)

        # Overlap between recorded and excluded is rejected (fresh month so
        # the assessment is still recordable).
        self._login("President", "setup2")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({"month": "2026-11", "items": self.assessment_payload["items"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        october_check_id = response.json()["assessment"]["assessment_id"]
        self._login("Treasurer", "record2")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": october_check_id,
                "members": [
                    {"member_id": self.members[0].member_id_PK, "actual_deduction": 300},
                ],
                "excluded_member_ids": [self.members[0].member_id_PK],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)

        # Treasurer roster reports the exclusion flag (restores the checkbox).
        response = self.client.get(f"/api/treasurer/deductions/members/{assessment_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        roster = {m["member_id"]: m for m in response.json()["members"]}
        self.assertTrue(roster[excluded_id]["is_excluded"])
        self.assertFalse(roster[self.members[0].member_id_PK]["is_excluded"])

        # Auditor review sees all three members, excluded flagged.
        self._login("Auditor", "review")
        response = self.client.get(f"/api/auditor/deductions/detail/{assessment_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        detail = {m["member_id"]: m for m in response.json()["member_assessments"]}
        self.assertEqual(len(detail), 3)
        self.assertTrue(detail[excluded_id]["is_excluded"])

        # Full approval, then the excluded balance carries as next month prior.
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "ok"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self._login("President", "final")
        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "Approved."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps({"month": "2026-10", "items": self.assessment_payload["items"]}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        october_id = response.json()["assessment"]["assessment_id"]
        self._login("Treasurer", "october")
        response = self.client.get(f"/api/treasurer/deductions/members/{october_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        october_roster = {m["member_id"]: m for m in response.json()["members"]}
        self.assertEqual(october_roster[excluded_id]["prior_outstanding"], 300.0)

    def test_treasurer_can_rerecord_after_president_return(self):
        """A President return must send the month back to a recordable state.

        Regression: the record endpoint accepted auditor-rejected months but
        rejected president-returned ones with 409, so the Treasurer could not
        fix and resubmit.
        """
        self._login("President", "setup")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(self.assessment_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment_id = response.json()["assessment"]["assessment_id"]

        members_payload = {
            "assessment_id": assessment_id,
            "members": [
                {"member_id": m.member_id_PK, "actual_deduction": amount}
                for m, amount in zip(self.members, [300, 150, 0])
            ],
        }
        self._login("Treasurer", "record")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps(members_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        deposit_monthly_batch(self.client, assessment_id)

        self._login("Auditor", "verify")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "ok"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        self._login("President", "return")
        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "return", "notes": "Fix amounts."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        # The returned month records again (rows are replaced, not duplicated).
        self._login("Treasurer", "rerecord")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps(members_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            MemberAssessment.objects.filter(assessment_id_FK_id=assessment_id).count(), 3
        )

    def test_president_return_resets_member_rows_to_pending(self):
        self._login("President", "setup")
        response = self.client.post(
            "/api/president/monthly-assessment/save/",
            json.dumps(self.assessment_payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        assessment_id = response.json()["assessment"]["assessment_id"]

        self._login("Treasurer", "record")
        response = self.client.post(
            "/api/treasurer/deductions/record/",
            json.dumps({
                "assessment_id": assessment_id,
                "members": [
                    {"member_id": m.member_id_PK, "actual_deduction": amount}
                    for m, amount in zip(self.members, [300, 150, 0])
                ],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        deposit_monthly_batch(self.client, assessment_id)

        self._login("Auditor", "verify")
        response = self.client.post(
            "/api/auditor/deductions/verify/",
            json.dumps({"assessment_id": assessment_id, "action": "approve", "notes": "ok"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        self._login("President", "return")
        response = self.client.post(
            "/api/president/deductions/approve/",
            json.dumps({"assessment_id": assessment_id, "action": "return", "notes": "Fix this."}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)

        rows = list(MemberAssessment.objects.filter(assessment_id_FK_id=assessment_id).order_by("member_id_FK__full_name"))
        self.assertTrue(rows)
        self.assertEqual({row.status for row in rows}, {MemberAssessment.STATUS_PENDING})
        self.assertTrue(all(row.verified_by_id_FK is None for row in rows))
        self.assertTrue(all(row.approved_by_id_FK is None for row in rows))
        self.assertEqual(
            MonthlyAssessment.objects.get(pk=assessment_id).status,
            MonthlyAssessment.STATUS_RETURNED,
        )

    def test_member_ledger_api_shows_approved_deductions(self):
        self._approve_full_workflow([400, 150, 0])

        self._login_as_member(self.members[0])
        response = self.client.get("/api/member/ledger/")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        dues_entries = [e for e in data["entries"] if e["transaction_type"] == "monthly_dues"]
        self.assertEqual(len(dues_entries), 1)
        self.assertEqual(dues_entries[0]["amount"], 400.0)
        self.assertEqual(dues_entries[0]["direction"], "credit")
        self.assertIn("September 2026", dues_entries[0]["description"])
        self.assertEqual(dues_entries[0]["outstanding_after"], 0.0)
        self.assertEqual(data["monthly_total_paid"], 400.0)
        self.assertEqual(data["monthly_outstanding"], 0.0)
        self.assertEqual(data["current_balance"], 0.0)

        self._login_as_member(self.members[1])
        response = self.client.get("/api/member/ledger/")
        data = response.json()
        dues_entries = [e for e in data["entries"] if e["transaction_type"] == "monthly_dues"]
        self.assertEqual(len(dues_entries), 1)
        self.assertEqual(dues_entries[0]["amount"], 150.0)
        self.assertEqual(dues_entries[0]["outstanding_after"], 150.0)
        self.assertEqual(data["monthly_total_paid"], 150.0)
        self.assertEqual(data["monthly_outstanding"], 150.0)
        self.assertEqual(data["current_balance"], 150.0)
