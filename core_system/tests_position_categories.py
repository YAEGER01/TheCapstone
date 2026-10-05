import json

from django.test import TestCase
from django.utils import timezone

from core_system.auth_utils import create_access_session
from core_system.models import OfficerUser, PositionCategory, PositionRank

LIST_URL = "/api/treasurer/members/position-categories/list/"
ADD_URL = "/api/treasurer/members/position-categories/add/"


def _update_url(category_id):
    return f"/api/treasurer/members/position-categories/{category_id}/update/"


def _delete_url(category_id):
    return f"/api/treasurer/members/position-categories/{category_id}/delete/"


class PositionCategoryApiTests(TestCase):
    def _login(self):
        officer = OfficerUser.objects.create(
            full_name="Treasurer Test",
            username="treasurer_poscat",
            password_hash="unused",
            role="Treasurer",
            account_status="Active",
        )
        session, token = create_access_session(
            officer=officer,
            ip_address="127.0.0.1",
            device_info="tests",
        )
        session.trusted_device = True
        policy = session.session_policy or {}
        policy["zt_verified_at"] = timezone.now().isoformat()
        session.session_policy = policy
        session.save()

        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return officer

    def _post(self, url, payload=None):
        return self.client.post(
            url, data=json.dumps(payload or {}), content_type="application/json"
        )

    def test_list_returns_seeded_defaults(self):
        self._login()
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        names = {category["name"] for category in data["categories"]}
        self.assertIn("Instructor", names)

    def test_add_category_and_reject_duplicate(self):
        self._login()
        response = self._post(ADD_URL, {"name": "Visiting Professor"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(PositionCategory.objects.filter(name="Visiting Professor").exists())

        duplicate = self._post(ADD_URL, {"name": "visiting professor"})
        self.assertEqual(duplicate.status_code, 400)
        self.assertFalse(duplicate.json()["ok"])

    def test_rename_cascades_to_ranks(self):
        self._login()
        category = PositionCategory.objects.create(name="Old Category")
        PositionRank.objects.create(name="Rank A", category="Old Category")

        response = self._post(_update_url(category.category_id_PK), {"name": "New Category"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["renamed_ranks"], 1)

        category.refresh_from_db()
        self.assertEqual(category.name, "New Category")
        self.assertEqual(PositionRank.objects.get(name="Rank A").category, "New Category")

    def test_delete_blocked_when_in_use_then_allowed(self):
        self._login()
        category = PositionCategory.objects.create(name="Used Category")
        PositionRank.objects.create(name="Rank B", category="Used Category")

        blocked = self._post(_delete_url(category.category_id_PK))
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("still use", blocked.json()["error"])

        PositionRank.objects.filter(name="Rank B").update(category="Other")
        allowed = self._post(_delete_url(category.category_id_PK))
        self.assertEqual(allowed.status_code, 200)
        self.assertFalse(
            PositionCategory.objects.filter(category_id_PK=category.category_id_PK).exists()
        )

    def test_rank_add_auto_creates_category(self):
        self._login()
        response = self._post(
            "/api/treasurer/members/position-ranks/add/",
            {"name": "Special Rank", "category": "Brand New Category"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(PositionCategory.objects.filter(name="Brand New Category").exists())
        self.assertEqual(
            PositionRank.objects.get(name="Special Rank").category, "Brand New Category"
        )
