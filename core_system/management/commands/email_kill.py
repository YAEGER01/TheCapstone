"""Emergency control for the master outgoing-email kill switch.

Usage (SSH / cPanel terminal / cron-time triage)::

    python manage.py email_kill status
    python manage.py email_kill stop
    python manage.py email_kill off [--purge-pending]
    python manage.py email_kill on

- ``stop`` (recommended): momentary STOP — blocks all SMTP, wipes the whole
  queue, then automatically turns email back ON fresh. Nothing pending,
  nothing stuck, nothing resumes.
- ``off`` holds email OFF until ``on`` (extended incidents; also blocks
  OTP login codes while held).
- ``--purge-pending`` with ``off`` additionally cancels every PENDING /
  stuck SENDING row so nothing resumes when you switch back ``on``.
- ``status`` prints the switch state plus queue counts.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Emergency master switch for all outbound email (status | stop | on | off [--purge-pending])"

    def add_arguments(self, parser):
        parser.add_argument(
            "action",
            choices=["status", "stop", "on", "off"],
            help="'stop' = momentary wipe + auto back ON (recommended); 'off' holds until 'on'; 'status' reports.",
        )
        parser.add_argument(
            "--purge-pending",
            action="store_true",
            help="With 'off': also cancel every PENDING / stuck SENDING row so nothing resumes on 'on'.",
        )

    def handle(self, *args, **options):
        from core_system.email_killswitch import (
            is_email_sending_enabled,
            set_email_sending_enabled,
        )
        from core_system.models import OutgoingEmail

        action = options["action"]

        if action == "status":
            pending = OutgoingEmail.objects.filter(status=OutgoingEmail.PENDING).count()
            sending = OutgoingEmail.objects.filter(status="sending").count()
            state = "ON (mail flows)" if is_email_sending_enabled() else "OFF (all SMTP blocked)"
            self.stdout.write(f"Outgoing email: {state}")
            self.stdout.write(f"Queued: {pending} pending, {sending} stuck/sending")
            return

        if action == "stop":
            from core_system.email_killswitch import momentary_email_stop

            result = momentary_email_stop()
            self.stdout.write(
                self.style.SUCCESS(
                    f"STOPPED — {result['cancelled']} queued email(s) wiped. "
                    "Email is back ON fresh: nothing pending, nothing resumes."
                )
            )
            return

        if action == "off":
            set_email_sending_enabled(False)
            self.stdout.write(
                self.style.WARNING("Outgoing email switched OFF — all SMTP paths blocked.")
            )
            if options.get("purge_pending"):
                now = timezone.now()
                cancelled = OutgoingEmail.objects.filter(
                    status__in=[OutgoingEmail.PENDING, "sending"]
                ).update(
                    status=OutgoingEmail.FAILED,
                    error_message="Cancelled by operator via email_kill off --purge-pending",
                    claimed_at=None,
                    sent_at=now,
                )
                self.stdout.write(
                    self.style.WARNING(f"Cancelled {cancelled} queued email row(s).")
                )
            else:
                pending = OutgoingEmail.objects.filter(status=OutgoingEmail.PENDING).count()
                self.stdout.write(
                    f"{pending} PENDING row(s) frozen (kept; they resume on 'email_kill on'). "
                    "Re-run with --purge-pending to cancel them permanently."
                )
            return

        set_email_sending_enabled(True)
        self.stdout.write(self.style.SUCCESS("Outgoing email switched ON — queue drains normally."))
