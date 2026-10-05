from django.core.management.base import BaseCommand

from core_system.models import OrganizationFundReport
from core_system.fund_report_views import _archive_approved_report_document


class Command(BaseCommand):
    help = (
        "Re-file approved fund reports into the Treasurer's and President's "
        "Document Repositories (for approvals that failed to archive, or "
        "copies missing from just one repository). Idempotent per repository."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--report-id",
            type=int,
            default=None,
            help="Only backfill this report id (default: all Approved reports).",
        )

    def handle(self, *args, **options):
        report_id = options.get("report_id")

        qs = OrganizationFundReport.objects.filter(report_status="Approved")
        if report_id:
            qs = qs.filter(report_id_PK=report_id)

        total_created = 0
        for report in qs:
            created = _archive_approved_report_document(report, report.approved_by_user_id_FK)
            label = f"FR-{report.report_id_PK:05d} ({report.report_period})"
            if created:
                total_created += created
                self.stdout.write(self.style.SUCCESS(f"{label}: {created} document copy(ies) archived."))
            else:
                self.stdout.write(f"{label}: nothing to do (already filed in both repositories or no report file).")

        self.stdout.write(self.style.SUCCESS(f"Done. {total_created} document copy(ies) newly archived."))
