"""What the Release Queue hands the front end: who can receive, and the math.

The release modal shows a "quick check" line so the Treasurer can sanity-check
the payout before releasing: the policy rate for that aid type times the
members still paying into it. Death aid uses the family tier that matches the
claim's relationship (member / spouse / parent-child / full-blood sibling).
"""
from django.test import TestCase
from django.utils import timezone

from core_system.constants.policy_constants import (
    get_accidental_sickness_aid_benefit,
    get_death_aid_amount,
)
from core_system.models import (
    AidTrackingPost,
    Claimant,
    DeathAid,
    Member,
    OfficerUser,
    TransactionArchive,
)
from core_system.treasurer_views import _relationship_label
from core_system.tests import _create_zt_verified_session


class ReleaseQueuePayloadTests(TestCase):
    def setUp(self):
        self.officer = OfficerUser.objects.create(
            full_name="Treasurer Queue Test",
            username="trez_queue_" + str(timezone.now().timestamp()),
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
        )
        session, token = _create_zt_verified_session(self.officer)
        s = self.client.session
        s["access_token"] = token
        s["officer_id"] = self.officer.user_id_PK
        s["role"] = self.officer.role
        s.save()

        self.active_member = self._member("ALPHA ONE")
        self._member("BETA TWO")
        self._member("GAMMA RETIRED", status="Retired", cls="Retired")

        self.medical_post = self._post("medical_aid", "ALPHA ONE", 200)
        self.death_post = self._post("death_aid", "BETA TWO", 600, relationship="spouse")

    def _member(self, full_name, status="Permanent", cls="Teaching"):
        return Member.objects.create(
            full_name=full_name,
            department="D",
            position="P",
            membership_status=status,
            member_classification=cls,
            employment_status="Active",
            member_type="REG",
            date_joined=timezone.now().date(),
        )

    def _post(self, aid_type, member_name, amount, relationship=""):
        member = Member.objects.get(full_name=member_name)
        record_id = 1
        if aid_type == "death_aid":
            claimant = Claimant.objects.create(
                member_id_FK=member,
                full_name=member_name,
                relationship_to_member=relationship,
                authorization_status="Approved",
            )
            death = DeathAid.objects.create(
                member_id_FK=member,
                claimant_id_FK=claimant,
                claim_date=timezone.now().date(),
                claim_type="Death",
                deceased_name="Someone",
                relationship_to_member=relationship,
                benefit_amount=0,
                document_status="Complete",
                status="Approved",
            )
            record_id = death.death_aid_id_PK
        archive = TransactionArchive.objects.create(
            transaction_type=aid_type,
            record_id=record_id,
            member_id_FK=member,
            member_name=member_name,
            amount=amount,
            status="Approved",
        )
        return AidTrackingPost.objects.create(
            archive_id_FK=archive,
            aid_type=aid_type,
            target_month="2026-09",
            total_expected=amount,
            total_collected=0,
            finish_status="pending_release",
            is_active=True,
        )

    def _payload(self):
        response = self.client.get("/api/treasurer/approved-aid-posts/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def _item(self, post):
        data = self._payload()
        return [p for p in data["posts"] if p["post_id"] == post.post_id_PK][0]

    def test_only_non_retired_members_are_offered_as_recipients(self):
        data = self._payload()

        self.assertEqual(data["active_member_count"], 2)
        self.assertEqual(data["member_names"], ["ALPHA ONE", "BETA TWO"])
        self.assertNotIn("GAMMA RETIRED", data["member_names"])

    def test_medical_quick_check_uses_the_policy_rate(self):
        item = self._item(self.medical_post)

        self.assertEqual(item["relationship"], "")
        self.assertEqual(item["relationship_label"], "")
        self.assertEqual(
            float(item["suggested_per_member"]),
            get_accidental_sickness_aid_benefit(),
        )

    def test_death_quick_check_uses_the_family_tier(self):
        item = self._item(self.death_post)

        self.assertEqual(item["relationship"], "spouse")
        self.assertEqual(item["relationship_label"], "spouse")
        self.assertEqual(
            float(item["suggested_per_member"]),
            get_death_aid_amount("spouse"),
        )

    def test_relationship_labels_are_human_readable(self):
        cases = [
            ("member", "member"),
            ("Spouse", "spouse"),
            ("child", "parent/child"),
            ("full-blood sister", "full-blood sibling"),
            ("cousin", "cousin"),
            ("", ""),
        ]
        for raw, label in cases:
            self.assertEqual(_relationship_label(raw), label)
