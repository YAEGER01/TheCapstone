from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import OfficerUser


class ChangePasswordPageTests(TestCase):
    def _login(self, must_change=True):
        officer = OfficerUser.objects.create(
            full_name="Forced Officer",
            username="forced_officer",
            password_hash=hash_password("OldPass123!"),
            role="Treasurer",
            account_status="Active",
            must_change_password=must_change,
            mfa_enabled=False,
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

    def test_page_renders_without_icons_and_with_green_button(self):
        self._login()
        response = self.client.get("/change-password/")
        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        self.assertIn('href="' + reverse("logout") + '"', html)
        self.assertNotIn("fa-arrow-left", html)
        self.assertNotIn("fa-check", html)
        self.assertIn("linear-gradient(135deg, #1b5e20 0%, #14521b 100%)", html)

    def test_back_to_login_ends_session_and_shows_login(self):
        self._login()
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))

        login_response = self.client.get(reverse("login"))
        self.assertEqual(login_response.status_code, 200)
        self.assertNotIn("access_token", self.client.session)
