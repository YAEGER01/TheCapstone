"""Prune rows that have aged out of usefulness.

Backups are already retained/rotated by run_backup_scheduler, but nothing was
ever deleting the *database rows* themselves, so sessions, notifications and
sent mails grew without bound.

The audit trail is deliberately excluded: GlobalAuditTrail is the compliance
record and is never pruned here.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core_system.models import (
    AccessSession,
    LoginAttemptLog,
    Notification,
    OutgoingEmail,
)

# days each table keeps rows after they stop being useful
RETENTION_DAYS = {
    "access_session": 30,        # past expiry/revocation
    "login_attempt_log": 90,
    "notification": 365,
    "outgoing_email": 90,        # sent/failed only; pending is never touched
}


class Command(BaseCommand):
    help = "Purge expired sessions, old login attempts, stale notifications and delivered emails."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting anything.",
        )

    def handle(self, *args, **options):
        dry = bool(options.get("dry_run"))
        now = timezone.now()

        def cutoff(days):
            return now - timedelta(days=days)

        plan = [
            (
                "access_session",
                AccessSession.objects.filter(expires_at__lt=cutoff(RETENTION_DAYS["access_session"])),
            ),
            (
                "login_attempt_log",
                LoginAttemptLog.objects.filter(attempted_at__lt=cutoff(RETENTION_DAYS["login_attempt_log"])),
            ),
            (
                "notification",
                Notification.objects.filter(sent_at__lt=cutoff(RETENTION_DAYS["notification"])),
            ),
            (
                "outgoing_email",
                OutgoingEmail.objects.filter(
                    status__in=[OutgoingEmail.SENT, OutgoingEmail.FAILED],
                    created_at__lt=cutoff(RETENTION_DAYS["outgoing_email"]),
                ),
            ),
        ]

        total = 0
        for label, qs in plan:
            count = qs.count()
            total += count
            if dry:
                self.stdout.write("%s: would delete %d row(s)" % (label, count))
            elif count:
                deleted, _ = qs.delete()
                self.stdout.write(self.style.SUCCESS("%s: deleted %d row(s)" % (label, deleted)))

        if dry:
            self.stdout.write("Dry run: %d row(s) would be deleted." % total)
        elif not total:
            self.stdout.write("Nothing to purge.")
