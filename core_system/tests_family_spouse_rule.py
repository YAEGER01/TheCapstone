"""Family list — one spouse per member.

The death-aid tiers assume at most one Spouse row in a member's family list:
with two, the treasurer filing a spouse claim could not tell which spouse is
the deceased. These tests pin the rule at the save endpoint and make sure the
treasurer's family feed keeps grouping relatives into the right tiers (which
is what drives the deceased-name dropdown in Aid Filing).
"""

import json

from django.test import TestCase
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import Claimant, Member, OfficerUser

PASSWORD = "Str0ng!Passw0rd"

FAMILY_SAVE_URL = "/api/member/family/save/"
FAMILY_DELETE_URL = "/api/member/family/delete/"


class FamilySpouseRuleTestBase(TestCase):
    def _officer_with_member(self, username, role="Member", name="Alpha Member", employee_id="fam-001"):
        officer = OfficerUser.objects.create(
            full_name=name,
            username=username,
            password_hash=hash_password(PASSWORD),
            role=role,
            account_status="Active",
            mfa_enabled=False,
            email=f"{username}@isu.edu.ph",
        )
        member = Member.objects.create(
            full_name=name,
            employee_id=employee_id,
            membership_status="Permanent",
            employment_status="Active",
            member_classification="Teaching",
            date_joined=timezone.now().date(),
            officer_user_id_FK=officer,
        )
        return officer, member

    def _login(self, officer, role=None):
        session, token = create_access_session(
            officer=officer, ip_address="127.0.0.1", device_info="tests",
        )
        session.trusted_device = True
        session.save()
        client_session = self.client.session
        client_session["access_token"] = token
        client_session["officer_id"] = officer.user_id_PK
        client_session["role"] = role or officer.role
        client_session.save()

    def _save_family(self, full_name, category, contact="09171234567", row_id=None):
        body = {"full_name": full_name, "category": category, "contact_number": contact}
        if row_id:
            body["id"] = row_id
        return self.client.post(
            FAMILY_SAVE_URL, data=json.dumps(body),
            content_type="application/json", **{"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"},
        )


class OneSpouseRuleTests(FamilySpouseRuleTestBase):
    def setUp(self):
        self.officer, self.member = self._officer_with_member("fam-member-1")
        self._login(self.officer)

    def test_first_spouse_is_accepted(self):
        res = self._save_family("Maria Santos", "spouse")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

    def test_second_spouse_is_rejected(self):
        self._save_family("Maria Santos", "spouse")
        res = self._save_family("Juana Reyes", "spouse")
        self.assertEqual(res.status_code, 409)
        self.assertFalse(res.json()["ok"])
        self.assertIn("Only one spouse", res.json()["error"])
        spouses = Claimant.objects.filter(
            member_id_FK=self.member, relationship_to_member="Spouse",
        )
        self.assertEqual(spouses.count(), 1)

    def test_turning_a_child_row_into_a_second_spouse_is_rejected(self):
        self._save_family("Maria Santos", "spouse")
        child_res = self._save_family("Boy Santos", "child")
        child_id = child_res.json()["item"]["id"]
        res = self._save_family("Boy Santos", "spouse", row_id=child_id)
        self.assertEqual(res.status_code, 409)
        child = Claimant.objects.get(claimant_id_PK=child_id)
        self.assertEqual(child.relationship_to_member, "Child")

    def test_editing_the_spouse_row_itself_still_saves(self):
        res = self._save_family("Maria Santos", "spouse")
        row_id = res.json()["item"]["id"]
        res = self._save_family("Maria Santos-Reyes", "spouse", row_id=row_id)
        self.assertEqual(res.status_code, 200)
        row = Claimant.objects.get(claimant_id_PK=row_id)
        self.assertEqual(row.full_name, "Maria Santos-Reyes")

    def test_legacy_second_spouse_can_still_be_edited(self):
        """Rows created before the rule (or by old claims) must not become
        uneditable — an edit that keeps a row's own spouse status is allowed
        even when another spouse row exists."""
        Claimant.objects.create(
            member_id_FK=self.member, full_name="Maria Santos",
            relationship_to_member="Spouse", relationship_group="spouse",
            authorization_status="Active",
        )
        legacy = Claimant.objects.create(
            member_id_FK=self.member, full_name="Juana Reyes",
            relationship_to_member="Spouse", relationship_group="spouse",
            authorization_status="Active",
        )
        res = self._save_family("Juana Reyes-Cruz", "spouse", row_id=legacy.claimant_id_PK)
        self.assertEqual(res.status_code, 200)
        legacy.refresh_from_db()
        self.assertEqual(legacy.full_name, "Juana Reyes-Cruz")

    def test_spouse_can_be_replaced_after_removal(self):
        res = self._save_family("Maria Santos", "spouse")
        row_id = res.json()["item"]["id"]
        del_res = self.client.post(
            FAMILY_DELETE_URL, data=json.dumps({"id": row_id}),
            content_type="application/json", **{"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"},
        )
        self.assertEqual(del_res.status_code, 200)
        res = self._save_family("Juana Reyes", "spouse")
        self.assertEqual(res.status_code, 200)

    def test_other_categories_allow_multiple_rows(self):
        """The rule is spouse-only — several children/parents are expected."""
        self._save_family("Boy Santos", "child")
        res = self._save_family("Girl Santos", "child")
        self.assertEqual(res.status_code, 200)
        children = Claimant.objects.filter(
            member_id_FK=self.member, relationship_to_member="Child",
        )
        self.assertEqual(children.count(), 2)


class TreasurerFamilyFeedTests(FamilySpouseRuleTestBase):
    """The treasurer feed groups relatives into death-aid tiers — this is
    what the deceased-name dropdown (single vs multiple matches) reads."""

    FAMILY_LIST_URL = "/api/treasurer/member/{member_id}/family/"

    def setUp(self):
        self.officer, self.member = self._officer_with_member("fam-member-2")
        self.treasurer, _ = self._officer_with_member(
            "fam-treasurer-2", role="Treasurer", name="Tresa Treasurer", employee_id="fam-tr-2",
        )
        self._login(self.treasurer, role="Treasurer")

    def test_multiple_children_arrive_as_one_tier(self):
        Claimant.objects.create(
            member_id_FK=self.member, full_name="Boy Santos",
            relationship_to_member="Child", relationship_group="parent_child",
            authorization_status="Active",
        )
        Claimant.objects.create(
            member_id_FK=self.member, full_name="Girl Santos",
            relationship_to_member="Child", relationship_group="parent_child",
            authorization_status="Active",
        )
        res = self.client.get(
            self.FAMILY_LIST_URL.format(member_id=self.member.member_id_PK),
            **{"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"},
        )
        self.assertEqual(res.status_code, 200)
        items = res.json()["items"]
        children = [i for i in items if i["category"] == "child"]
        self.assertEqual(len(children), 2)
        self.assertEqual({i["full_name"] for i in children}, {"Boy Santos", "Girl Santos"})
