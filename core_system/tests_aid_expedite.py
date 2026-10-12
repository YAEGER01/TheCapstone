"""Tests for the Auditor -> Treasurer aid-filing expedite flow (NoticeCard)."""

import datetime
import json

from django.test import TestCase
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import (
    AidSetAside,
    AssessmentItem,
    FundTransaction,
    Member,
    MemberAssessment,
    MonthlyAssessment,
    Notification,
    OfficerUser,
)


def _make_officer(username, role):
    return OfficerUser.objects.create(
        full_name=f"{username} Full",
        username=username,
        password_hash=hash_password("TestPass123!"),
        role=role,
        account_status="Active",
        email=f"{username}@example.com",
    )


def _login(client, officer):
    session, token = create_access_session(
        officer=officer, ip_address="127.0.0.1", device_info="tests")
    session.trusted_device = True
    policy = session.session_policy or {}
    policy["zt_verified_at"] = timezone.now().isoformat()
    session.session_policy = policy
    session.save()
    s = client.session
    s["access_token"] = token
    s["officer_id"] = officer.user_id_PK
    s["role"] = officer.role
    s.save()
    return officer


class AidExpediteTests(TestCase):
    def setUp(self):
        self.auditor = _make_officer("exp_auditor", "Auditor")
        self.treasurer = _make_officer("exp_treasurer", "Treasurer")
        self.president = _make_officer("exp_president", "President")

    def _notify(self, item_id=77):
        return self.client.post(
            "/api/auditor/unfiled-aids/notify/",
            data=json.dumps({
                "kind": "item", "item_id": item_id,
                "recipient": "Juan Dela Cruz", "aid_label": "Medical Aid",
                "case_suffix": "Set-aside · Jan 2026",
                "collected": 5000, "set_aside": 1200,
            }),
            content_type="application/json",
        )

    def test_notify_fans_out_to_all_roles(self):
        _login(self.client, self.auditor)
        res = self._notify()
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["notified"], 3)
        for o in (self.auditor, self.treasurer, self.president):
            self.assertTrue(Notification.objects.filter(
                recipient_type="officer", recipient_id=o.user_id_PK,
                notification_type="AID_FILE_EXPEDITE",
                receipt_number="AID-EXPEDITE-ITEM-77",
                is_read=False,
            ).exists())

    def test_notify_dedupes_while_unread(self):
        _login(self.client, self.auditor)
        self.assertEqual(self._notify().status_code, 200)
        res = self._notify()
        self.assertEqual(res.status_code, 409)
        self.assertFalse(res.json()["ok"])

    def test_notify_requires_item_id(self):
        _login(self.client, self.auditor)
        res = self.client.post(
            "/api/auditor/unfiled-aids/notify/",
            data=json.dumps({"kind": "item", "item_id": 0}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_treasurer_cannot_notify_but_can_read(self):
        _login(self.client, self.treasurer)
        res = self._notify()
        self.assertIn(res.status_code, (302, 403))
        # Treasurer sees notices after auditor notifies.
        _login(self.client, self.auditor)
        self.assertEqual(self._notify(item_id=78).status_code, 200)
        _login(self.client, self.treasurer)
        res = self.client.get("/api/officer/expedite-notices/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["unread"], 1)
        self.assertEqual(len(data["notices"]), 1)
        self.assertIn("Juan Dela Cruz", data["notices"][0]["message"])
        # Collapsed drawer title: "{Aid} for {member}", no dev terms.
        n = data["notices"][0]
        self.assertEqual(n["title"], "Medical Aid for Juan Dela Cruz")
        self.assertEqual(n["aid_label"], "Medical Aid")
        self.assertEqual(n["recipient"], "Juan Dela Cruz")
        self.assertEqual(n["case_suffix"] if "case_suffix" in n else n["case_month"], "Jan 2026")
        self.assertEqual(n["collected"], "5,000.00")
        self.assertEqual(n["available"], "1,200.00")
        self.assertNotIn("set-aside", n["message"].lower())

    def test_legacy_message_is_sanitized(self):
        from core_system.models import Notification
        Member.objects.create(
            full_name="Andrea Kimi Antonelli",
            employee_id="EMP-LEG-001",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            email="antonnelli@test.local",
            date_joined=timezone.now().date(),
        )
        _login(self.client, self.auditor)
        Notification.objects.create(
            recipient_type="officer",
            recipient_id=self.auditor.user_id_PK,
            recipient_name=self.auditor.full_name,
            notification_type="AID_FILE_EXPEDITE",
            message=("exp_auditor Full (Auditor) asked the Treasurer to file Medical Aid "
                     "for ANTONELLI, Andrea Kimi (Set-aside · Apr 2026) "
                     "(collected ₱65,500.00, set-aside ₱65,500.00)."),
            delivery_status="Sent",
            category="aid",
            receipt_number="AID-EXPEDITE-ITEM-999",
        )
        res = self.client.get("/api/officer/expedite-notices/")
        data = res.json()
        self.assertTrue(data["ok"])
        n = data["notices"][0]
        self.assertEqual(n["title"], "Medical Aid for ANTONELLI, Andrea Kimi")
        self.assertEqual(n["recipient"], "ANTONELLI, Andrea Kimi")
        self.assertEqual(n["case_month"], "Apr 2026")
        self.assertEqual(n["collected"], "65,500.00")
        self.assertEqual(n["available"], "65,500.00")
        self.assertNotIn("set-aside", n["message"].lower())
        # NoticeCard File Aid intelligence: kind + resolved member.
        self.assertEqual(n["aid_kind"], "medical")
        from core_system.models import Member as _M
        self.assertEqual(
            n["member_id"],
            _M.objects.get(employee_id="EMP-LEG-001").member_id_PK)

    def test_unfiled_setasides_expose_member_and_kind(self):
        member = Member.objects.create(
            full_name="File Aid Member",
            employee_id="EMP-FILE-001",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            email="file_aid_member@test.local",
            date_joined=timezone.now().date(),
        )
        assessment = MonthlyAssessment.objects.create(
            month=datetime.date(2026, 3, 1),
            total_amount=100,
            status="final_approved",
        )
        item = AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose="medical_aid_fund",
            amount=100,
            recipient="File Aid Member",
            priority_order=1,
        )
        ma = MemberAssessment.objects.create(
            assessment_id_FK=assessment,
            member_id_FK=member,
            standard_assessment=100,
            actual_deduction=100,
        )
        tx = FundTransaction.objects.create(
            direction="inflow",
            amount=100,
            source_type="aid_setaside_medical",
            source_id=ma.member_assessment_id_PK,
            description=" test earmark",
            recorded_by_user_id_FK=self.treasurer,
        )
        AidSetAside.objects.create(
            member_assessment_id_FK=ma,
            assessment_item_id_FK=item,
            fund_transaction_id_FK=tx,
            aid_type="medical_aid",
            amount=100,
        )
        _login(self.client, self.treasurer)
        res = self.client.get("/api/treasurer/aid-release/unfiled-setasides/")
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertTrue(data["ok"])
        row = next(
            (r for r in data["unfiled"]
             if r.get("assessment_item_id") == item.item_id_PK),
            None,
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["member_id"], member.member_id_PK)
        self.assertEqual(row["aid_kind"], "medical")
        self.assertEqual(row["member_name"], "File Aid Member")

    def test_unfiled_member_match_is_order_proof(self):
        member = Member.objects.create(
            full_name="Alex Wurz",
            employee_id="EMP-ORD-001",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            email="alex.wurz@test.local",
            date_joined=timezone.now().date(),
        )
        retired = Member.objects.create(
            full_name="WURZ, Retired",
            employee_id="EMP-ORD-002",
            department="Finance",
            position="Staff",
            membership_status="Permanent",
            employment_status="Active",
            member_type="Member",
            member_classification="Retired",
            email="retired@test.local",
            date_joined=timezone.now().date(),
        )
        assessment = MonthlyAssessment.objects.create(
            month=datetime.date(2026, 4, 1),
            total_amount=200,
            status="final_approved",
        )
        item = AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose="death_aid_fund",
            amount=100,
            recipient="WURZ, Alex",
            priority_order=1,
        )
        ret_item = AssessmentItem.objects.create(
            assessment_id_FK=assessment,
            purpose="medical_aid_fund",
            amount=100,
            recipient="WURZ, Retired",
            priority_order=2,
        )
        for it, m in ((item, member), (ret_item, retired)):
            ma = MemberAssessment.objects.create(
                assessment_id_FK=assessment,
                member_id_FK=m,
                standard_assessment=100,
                actual_deduction=100,
            )
            tx = FundTransaction.objects.create(
                direction="inflow",
                amount=100,
                source_type="aid_setaside_death",
                source_id=ma.member_assessment_id_PK,
                description="test earmark",
                recorded_by_user_id_FK=self.treasurer,
            )
            AidSetAside.objects.create(
                member_assessment_id_FK=ma,
                assessment_item_id_FK=it,
                fund_transaction_id_FK=tx,
                aid_type="death_aid",
                amount=100,
            )
        _login(self.client, self.treasurer)
        res = self.client.get("/api/treasurer/aid-release/unfiled-setasides/")
        self.assertEqual(res.status_code, 200, res.content)
        rows = {r["assessment_item_id"]: r for r in res.json()["unfiled"]}
        # "LAST, First" recipient resolves to "First Last" member.
        self.assertEqual(rows[item.item_id_PK]["member_id"], member.member_id_PK)
        self.assertEqual(rows[item.item_id_PK]["aid_kind"], "death")
        # Retired members are excluded (filing picker can't select them).
        self.assertIsNone(rows[ret_item.item_id_PK]["member_id"])

    def test_mark_read_clears_dot(self):
        _login(self.client, self.auditor)
        self.assertEqual(self._notify().status_code, 200)
        _login(self.client, self.president)
        res = self.client.get("/api/officer/expedite-notices/")
        self.assertEqual(res.json()["unread"], 1)
        res = self.client.post(
            "/api/officer/expedite-notices/mark-read/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["marked"], 1)
        res = self.client.get("/api/officer/expedite-notices/")
        self.assertEqual(res.json()["unread"], 0)
        # Dedupe stays while other officers still have it unread...
        _login(self.client, self.auditor)
        self.assertEqual(self._notify().status_code, 409)
        # ...and a second notify works again once everyone read it.
        for o in (self.auditor, self.treasurer):
            _login(self.client, o)
            self.client.post(
                "/api/officer/expedite-notices/mark-read/",
                data=json.dumps({}),
                content_type="application/json",
            )
        _login(self.client, self.auditor)
        self.assertEqual(self._notify().status_code, 200)
