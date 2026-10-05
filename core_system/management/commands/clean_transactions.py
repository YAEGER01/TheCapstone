"""Wipe all FINANCIAL transaction tables, preserving reference data.

EXEMPT (never touched):
  - Officer accounts: officer_user, officer_profile, access_session
  - Members & relatives: member, claimant, member_registration_request
  - Categories & ranks: category, announcement_category, event_type,
    position_rank, position_category, department
  - Everything else (CMS content, logs, settings, certificates, …)

WIPED (money-movement records + their attachments/workflow rows):
  monthly_dues, member_ledger, membership_fee,
  medical_aid, death_aid,
  contribution, aid_tracking_post, aid_set_asides,
  fund_transaction,
  payroll_batch, payroll_deduction,
  monthly_assessments, monthly_assessment_documents, assessment_items,
  member_assessments, member_catchup_dues, member_assessment_allocations,
  workflow_logs,
  salary_deduction_exemption,
  transaction_verification, transaction_archive,
  audit_findings_report, organization_fund_report,
  financial_document_archive, supporting_proof

Usage:
    python manage.py clean_transactions --dry-run   # preview counts only
    python manage.py clean_transactions --yes       # wipe without prompting
    python manage.py clean_transactions             # prompts for YES
"""
from django.core.management.base import BaseCommand
from django.db import connection

# Explicit wipe list: ONLY financial transaction tables. Anything not listed
# here is preserved, no matter what.
WIPE_TABLES = [
    # Dues / ledger / fees
    "monthly_dues",
    "member_ledger",
    "membership_fee",
    # Aid claims (claimant relatives are EXEMPT and untouched)
    "medical_aid",
    "death_aid",
    # Aid collection / contributions / set-asides
    "contribution",
    "aid_tracking_post",
    "aid_set_asides",
    # Fund movement
    "fund_transaction",
    # Payroll
    "payroll_batch",
    "payroll_deduction",
    # Monthly assessment workflow
    "monthly_assessments",
    "monthly_assessment_documents",
    "assessment_items",
    "member_assessments",
    "member_catchup_dues",
    "member_assessment_allocations",
    "workflow_logs",
    # Exemptions / verifications / archives
    "salary_deduction_exemption",
    "transaction_verification",
    "transaction_archive",
    # Financial reports & supporting attachments
    "audit_findings_report",
    "organization_fund_report",
    "financial_document_archive",
    "supporting_proof",
]


class Command(BaseCommand):
    help = (
        "Delete ALL financial transactions (dues, aids, contributions, "
        "payroll, assessments, fund ledger). Preserves officer accounts, "
        "members & relatives, categories & ranks."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show per-table row counts without deleting anything.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the interactive YES confirmation.",
        )

    def _existing_tables(self):
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES;")
            return {row[0].lower() for row in cursor.fetchall()}

    def _counts(self, tables):
        counts = {}
        with connection.cursor() as cursor:
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`;")
                counts[table] = cursor.fetchone()[0]
        return counts

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        existing = self._existing_tables()
        targets = [t for t in WIPE_TABLES if t in existing]
        missing = [t for t in WIPE_TABLES if t not in existing]

        counts = self._counts(targets) if targets else {}
        total = sum(counts.values())

        self.stdout.write("---- CLEAN TRANSACTIONS (financial only) ----")
        for table in targets:
            self.stdout.write(f"  {table}: {counts[table]} rows")
        for table in missing:
            self.stdout.write(f"  {table}: table not found, skipped")
        self.stdout.write(f"TOTAL rows to delete: {total}")
        self.stdout.write(
            "EXEMPT (preserved): officer accounts, members & relatives, "
            "categories & ranks, and all other tables."
        )

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — nothing deleted."))
            return

        if not options["yes"]:
            confirm = input('Type YES to permanently delete the rows above: ').strip()
            if confirm != "YES":
                self.stdout.write(self.style.WARNING("Aborted — nothing deleted."))
                return

        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            try:
                for table in targets:
                    # TRUNCATE also resets AUTO_INCREMENT so IDs restart at 1.
                    cursor.execute(f"TRUNCATE TABLE `{table}`;")
                    self.stdout.write(f"[WIPED] {table} ({counts[table]} rows)")
            finally:
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {total} transaction rows deleted; "
            "officers, members/relatives, categories/ranks preserved."
        ))
