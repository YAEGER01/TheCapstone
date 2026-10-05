from django.core.management.base import BaseCommand

from core_system.services.email_service import process_email_queue


class Command(BaseCommand):
    help = "Process pending emails from the OutgoingEmail queue"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=None,
            help="Optional maximum number of pending emails; defaults to all pending emails",
        )
        parser.add_argument(
            "--otp-only",
            action="store_true",
            help="Only drain a small OTP-first batch (for a */1-minute cron fast lane).",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if options.get("otp_only") and batch_size is None:
            batch_size = 10
        sent = process_email_queue(batch_size=batch_size)
        if sent:
            self.stdout.write(self.style.SUCCESS(f"Sent {sent} queued email(s)."))
        else:
            self.stdout.write("No pending emails to process.")
