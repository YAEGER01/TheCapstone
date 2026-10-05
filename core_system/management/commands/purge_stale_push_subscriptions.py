from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q


class Command(BaseCommand):
    help = (
        "Inspect or clean up push subscriptions. Web Push now works on any "
        "secure origin (localhost, ngrok HTTPS tunnels, and the live domain), "
        "so this command never deletes anything unless you explicitly ask it to "
        "with --purge-all or --purge-origin."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be deleted without deleting anything.",
        )
        parser.add_argument(
            "--purge-all",
            action="store_true",
            help="Delete every push subscription (forces a fresh re-subscribe).",
        )
        parser.add_argument(
            "--purge-origin",
            default="",
            help="Delete subscriptions whose stored origin contains this text "
            "(e.g. a retired tunnel host). Nothing is deleted when omitted.",
        )

    def handle(self, *args, **options):
        from core_system.models import PushSubscription

        dry_run = options["dry_run"]
        purge_all = options["purge_all"]
        purge_origin = (options["purge_origin"] or "").strip().lower()

        host = (getattr(settings, "BASE_URL", "") or "").split("://")[-1].split("/")[0].lower()

        if purge_all:
            qs = PushSubscription.objects.all()
            label = "ALL push subscriptions"
        elif purge_origin:
            qs = PushSubscription.objects.filter(origin__icontains=purge_origin)
            label = f"push subscriptions whose origin contains '{purge_origin}'"
        else:
            qs = PushSubscription.objects.filter(
                Q(origin__isnull=True) | ~Q(origin__icontains=host)
            ) if host else PushSubscription.objects.none()
            label = (
                f"push subscriptions not tied to the live host '{host}' "
                "(report only — pass --purge-all or --purge-origin to delete)"
            )

        total = qs.count()
        self.stdout.write(f"Found {total} {label}.")

        for sub in qs[:50]:
            self.stdout.write(
                f"  - #{sub.subscription_id_PK} origin={sub.origin or '<none>'} "
                f"member={sub.member_id_FK_id} officer={sub.officer_id_FK_id}"
            )

        if dry_run or (not purge_all and not purge_origin):
            self.stdout.write("Nothing deleted.")
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} push subscription(s)."))
