"""Fail fast (with an actionable message) when SMTP rejects our login.

A dead/rotated password surfaces as 534/535 auth errors on every send.
Retrying those rows is pointless log spam — the queue worker must mark them
FAILED immediately with a message that tells the operator exactly what to
fix (correct EMAIL_HOST_PASSWORD / FALLBACK_SMTP_PASSWORD in .env -> restart).
"""
import smtplib
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core.mail.backends.smtp import EmailBackend

from core_system.email_backends import (
    AmbiguousSMTPDelivery,
    FallbackSMTPBackend,
    _normalise_smtp_password,
)
from core_system.models import OutgoingEmail
from core_system.services import email_service


class EmailAuthFailFastTests(TestCase):
    def _queued_row(self):
        return OutgoingEmail.objects.create(
            recipient_list=["member@test.local"],
            subject="Test",
            html_template="emails/announcement_notification.html",
            context={},
        )

    def test_app_password_formatting_spaces_are_removed(self):
        self.assertEqual(
            _normalise_smtp_password("abcd efgh ijkl mnop"),
            "abcdefghijklmnop",
        )

    @override_settings(
        FALLBACK_SMTP_HOST="fallback.example.com",
        FALLBACK_SMTP_PORT=587,
        FALLBACK_SMTP_USER="sender@example.com",
        FALLBACK_SMTP_PASSWORD="abcd efgh ijkl mnop",
        FALLBACK_SMTP_USE_TLS=True,
        FALLBACK_SMTP_USE_SSL=False,
    )
    def test_fallback_normalizes_app_password(self):
        backend = FallbackSMTPBackend()
        self.assertTrue(backend._prepare_fallback())
        self.assertEqual(backend.password, "abcdefghijklmnop")

    def test_stale_connection_is_closed_before_reuse(self):
        backend = FallbackSMTPBackend(fail_silently=True)

        class StaleConnection:
            def __init__(self):
                self.closed = False

            def noop(self):
                raise smtplib.SMTPServerDisconnected("Server not connected")

            def quit(self):
                raise smtplib.SMTPServerDisconnected("Server not connected")

            def close(self):
                self.closed = True

        stale = StaleConnection()
        backend.connection = stale
        backend._ensure_connection_usable()
        self.assertTrue(stale.closed)
        self.assertIsNone(backend.connection)

    def test_mid_send_disconnect_is_not_replayed_on_fallback(self):
        backend = FallbackSMTPBackend()
        with patch.object(
            EmailBackend,
            "send_messages",
            side_effect=smtplib.SMTPServerDisconnected("Server not connected"),
        ) as send_messages:
            with self.assertRaises(AmbiguousSMTPDelivery):
                backend.send_messages(["message"])
        self.assertEqual(send_messages.call_count, 1)
        self.assertFalse(backend._fell_back)

    @override_settings(SMTP_BULK_BATCH_SIZE=2)
    def test_bulk_email_uses_bounded_connections(self):
        tasks = [
            {
                "subject": f"Subject {index}",
                "recipient_list": [f"member{index}@test.local"],
                "html_template": "emails/announcement_notification.html",
                "context": {},
            }
            for index in range(3)
        ]
        with patch.object(
            email_service,
            "_build_html_email_message",
            side_effect=[f"message-{index}" for index in range(3)],
        ):
            with patch.object(email_service, "_send_bulk_batch", side_effect=[2, 1]) as send_batch:
                self.assertEqual(email_service.send_html_emails_bulk(tasks), 3)
        self.assertEqual(send_batch.call_count, 2)

    def test_detects_gmail_auth_errors(self):
        auth_534 = smtplib.SMTPAuthenticationError(
            534, b"5.7.9 Please log in with your web browser (WebLoginRequired)"
        )
        self.assertTrue(email_service._is_smtp_auth_error(auth_534))
        auth_535 = smtplib.SMTPAuthenticationError(
            535, b"5.7.5 Username and Password not accepted"
        )
        self.assertTrue(email_service._is_smtp_auth_error(auth_535))
        self.assertFalse(email_service._is_smtp_auth_error(Exception("Connection unexpectedly closed")))
        self.assertFalse(email_service._is_smtp_auth_error(Exception("boom")))

    def test_auth_failure_skips_retry_and_names_the_fix(self):
        row = self._queued_row()
        with patch.object(email_service, "send_html_email", return_value=False):
            with patch.object(email_service, "SMTP_AUTH_FAILED", True):
                self.assertFalse(email_service._send_queued_email(row))
        row.refresh_from_db()
        # Failed fast: no retry consumed, still PENDING? No — FAILED at once.
        self.assertEqual(row.status, OutgoingEmail.FAILED)
        self.assertEqual(row.retry_count, 0)
        self.assertIn("FALLBACK_SMTP_PASSWORD", row.error_message)

    def test_transient_failure_still_retries(self):
        row = self._queued_row()
        with patch.object(email_service, "send_html_email", return_value=False):
            with patch.object(email_service, "SMTP_AUTH_FAILED", False):
                self.assertFalse(email_service._send_queued_email(row))
        row.refresh_from_db()
        self.assertEqual(row.status, OutgoingEmail.PENDING)
        self.assertEqual(row.retry_count, 1)

    def test_new_otp_supersedes_older_pending_otp(self):
        older = OutgoingEmail.objects.create(
            recipient_list=["member@test.local"],
            subject="CAUFA MFA Verification Code",
            html_template="emails/mfa_challenge.html",
            context={"otp_code": "111111"},
        )

        email_service.queue_and_process_email(
            subject="CAUFA MFA Verification Code",
            recipient_list=["member@test.local"],
            html_template="emails/mfa_challenge.html",
            context={"otp_code": "222222"},
        )

        older.refresh_from_db()
        self.assertEqual(older.status, OutgoingEmail.FAILED)
        self.assertIn("Superseded", older.error_message)
        self.assertEqual(
            OutgoingEmail.objects.filter(
                recipient_list=["member@test.local"],
                status=OutgoingEmail.PENDING,
            ).count(),
            1,
        )

    def test_detects_transient_disconnect(self):
        drop = smtplib.SMTPServerDisconnected("Server not connected")
        self.assertTrue(email_service._is_transient_smtp_error(drop))
        self.assertTrue(email_service._is_transient_smtp_error(ConnectionResetError("reset")))
        self.assertFalse(email_service._is_transient_smtp_error(ValueError("boom")))
        auth = smtplib.SMTPAuthenticationError(535, b"bad password")
        self.assertFalse(email_service._is_transient_smtp_error(auth))

    def test_transient_drop_retries_once_then_succeeds(self):
        drop = smtplib.SMTPServerDisconnected("Server not connected")
        with patch.object(
            email_service, "_build_html_email_message", side_effect=["msg1", "msg2"]
        ) as build:
            msg = type("M", (), {"send": None})()
            sends = []

            def send_once(fail_silently=False):
                sends.append(1)
                if len(sends) == 1:
                    raise drop
                return 1

            msg.send = send_once
            # Patch happens before loop uses rebuilt message — both builds return stubs.
            built = [type("M2", (), {"send": staticmethod(send_once)})(), type("M2", (), {"send": staticmethod(send_once)})()]
            build.side_effect = built
            with patch.object(email_service, "_SMTP_SEND_LOCK"):
                ok = email_service.send_html_email(
                    "Subject", ["a@b.c"], "emails/announcement_notification.html", {}
                )
        self.assertTrue(ok)
        self.assertEqual(len(sends), 2)
        self.assertEqual(build.call_count, 2)

    def test_transient_drop_gives_up_after_one_retry(self):
        drop = smtplib.SMTPServerDisconnected("Server not connected")
        built = []
        for _ in range(2):
            m = type("M", (), {})()
            m.send = lambda fail_silently=False, _d=drop: (_ for _ in ()).throw(_d)
            built.append(m)
        with patch.object(email_service, "_build_html_email_message", side_effect=built):
            with patch.object(email_service, "SMTP_AUTH_FAILED", False):
                ok = email_service.send_html_email(
                    "Subject", ["a@b.c"], "emails/announcement_notification.html", {}
                )
        self.assertFalse(ok)
