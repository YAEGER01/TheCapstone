from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import Member, Notification, OfficerUser


class MemberNotificationsApiTests(TestCase):
    def _login_member(self):
        officer = OfficerUser.objects.create(
            full_name="Notif Member",
            username="notif_member",
            password_hash=hash_password("MemberPass123!"),
            role="Member",
            account_status="Active",
            mfa_enabled=False,
        )
        member = Member.objects.create(
            full_name="Notif Member",
            employment_status="Permanent",
            membership_status="Active",
            member_type="",
            date_joined=timezone.now().date(),
            officer_user_id_FK=officer,
        )
        session, token = create_access_session(
            officer=officer,
            ip_address="127.0.0.1",
            device_info="tests",
        )
        session.save()

        test_session = self.client.session
        test_session["access_token"] = token
        test_session["officer_id"] = officer.user_id_PK
        test_session["role"] = officer.role
        test_session.save()
        return member

    def test_notifications_list_returns_items(self):
        member = self._login_member()
        Notification.objects.create(
            recipient_type="member",
            recipient_id=member.member_id_PK,
            notification_type="Announcement",
            message="Test announcement with a fairly long message body for the member.",
            category="announcement",
            sender_role="Treasurer",
        )

        response = self.client.get(reverse("member_notifications"), {"filter": "all", "page": 1, "page_size": 6})

        self.assertEqual(response.status_code, 200, response.content[:500])
        payload = response.json()
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(len(payload["items"]), 1)
        self.assertIn("message", payload["items"][0])
