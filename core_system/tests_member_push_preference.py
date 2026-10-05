import json

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core_system.auth_utils import create_access_session, hash_password
from core_system.models import Member, OfficerUser, PushSubscription


class MemberPushPreferenceTests(TestCase):
    """Member push is MANDATORY alongside email (force push).

    Subscribing sets Member.push_enabled, and unsubscribe attempts from
    member accounts are rejected (403) so delivery can never be opted out.
    Server-side delivery ignores the flag and pushes to all subscriptions.
    """

    def _member_session(self):
        officer = OfficerUser.objects.create(
            full_name="Push Member",
            username="push_member",
            password_hash=hash_password("MemberPass123!"),
            role="Member",
            account_status="Active",
            mfa_enabled=False,
        )
        member = Member.objects.create(
            full_name="Push Member",
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

    def test_subscribe_turns_account_preference_on(self):
        member = self._member_session()
        member.push_enabled = False
        member.save(update_fields=["push_enabled"])
        member.refresh_from_db()
        self.assertFalse(member.push_enabled)

        response = self.client.post(
            reverse("push_subscribe"),
            data=json.dumps({
                "recipient_type": "member",
                "endpoint": "https://push.example.test/subscription-1",
                "keys": {"p256dh": "BPbindingKey", "auth": "authSecret"},
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        member.refresh_from_db()
        self.assertTrue(member.push_enabled)
        self.assertEqual(PushSubscription.objects.filter(member_id_FK=member).count(), 1)

    def test_unsubscribe_clears_preference_and_all_subscriptions(self):
        # MANDATORY PUSH: member unsubscribe is rejected; subscriptions stay.
        member = self._member_session()
        member.push_enabled = True
        member.save(update_fields=["push_enabled"])
        PushSubscription.objects.create(
            member_id_FK=member,
            endpoint="https://push.example.test/subscription-1",
            p256dh_key="key-one",
            auth_key="auth-one",
        )
        PushSubscription.objects.create(
            member_id_FK=member,
            endpoint="https://push.example.test/subscription-2",
            p256dh_key="key-two",
            auth_key="auth-two",
        )

        response = self.client.post(
            reverse("push_unsubscribe"),
            data=json.dumps({"recipient_type": "member"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertFalse(payload["ok"])
        member.refresh_from_db()
        self.assertTrue(member.push_enabled)
        self.assertEqual(PushSubscription.objects.filter(member_id_FK=member).count(), 2)

    def test_dashboard_context_exposes_account_preference(self):
        member = self._member_session()
        member.push_enabled = True
        member.save(update_fields=["push_enabled"])

        response = self.client.get(reverse("member_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["member_push_enabled"])
        self.assertIn("window.MEMBER_PUSH_ENABLED = true", response.content.decode())

    def _subscribe(self, endpoint, origin):
        return self.client.post(
            reverse("push_subscribe"),
            data=json.dumps({
                "recipient_type": "member",
                "endpoint": endpoint,
                "keys": {"p256dh": "key-" + endpoint, "auth": "auth-" + endpoint},
            }),
            content_type="application/json",
            HTTP_ORIGIN=origin,
        )

    def test_subscribe_accepted_from_ngrok_origin(self):
        member = self._member_session()

        response = self._subscribe(
            "https://push.example.test/ngrok-1",
            "https://caufa-test.ngrok-free.app",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        sub = PushSubscription.objects.get(member_id_FK=member)
        self.assertEqual(sub.origin, "https://caufa-test.ngrok-free.app")

    def test_subscriptions_from_different_origins_are_kept(self):
        member = self._member_session()

        self._subscribe("https://push.example.test/tunnel-1", "https://a.ngrok-free.app")
        self._subscribe("https://push.example.test/local-1", "http://127.0.0.1:8000")

        self.assertEqual(PushSubscription.objects.filter(member_id_FK=member).count(), 2)

