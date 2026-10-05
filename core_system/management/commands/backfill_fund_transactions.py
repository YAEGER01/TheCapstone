"""
Backfill missing FundTransaction rows for already-approved payments.

Audit finding (2026-09-09): some approved membership fees and monthly dues
existed as valid source records but never produced the FundTransaction inflow
that the Financial Transparency Summary is built from. Root causes:

  - Membership fees 1-5 were approved before the fee-approval flow existed;
    later flows (treasurer fee approve / president decision) DO create the
    FundTransaction row.
  - Monthly dues 59, 61, 62, 63 reached payment_status "Auditor Verified" in
    an earlier dues workflow generation; the current flow creates the
    FundTransaction only at President approval.

This command repairs the LEDGER for records that are already fully approved
by the workflow. It never invents money: only rows whose payment_status is in
Status.ALL_AUDITOR_VERIFIED (the system-wide "paid" definition) and that do
not already have a FundTransaction row are booked. Every insert is written to
the audit trail as BACKFILL_<TYPE>.

Run:  python manage.py backfill_fund_transactions [--dry-run]
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.utils import timezone

from core_system.constants.status_constants import Status
from core_system.models import FundTransaction, MembershipFee, MonthlyDues
from core_system.shared_view_utils import _record_audit_trail


class Command(BaseCommand):
    help = "Book FundTransaction inflows for approved membership fees / monthly dues that lack one."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only report what would be created.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        paid = set(Status.ALL_AUDITOR_VERIFIED)
        created = 0

        fees = MembershipFee.objects.all()
        for f in fees:
            if str(f.payment_status) not in paid:
                continue
            exists = FundTransaction.objects.filter(source_type="membership_fee", source_id=f.fee_id_PK).exists()
            if exists:
                continue
            created += 1
            self.stdout.write("membership_fee fee_id=%s member=%s amount=%s" % (f.fee_id_PK, f.member_id_FK.full_name, f.amount))
            if dry:
                continue
            with db_transaction.atomic():
                ft = FundTransaction.objects.create(
                    direction="inflow",
                    amount=f.amount,
                    source_type="membership_fee",
                    source_id=f.fee_id_PK,
                    description="%s (Membership Fee)" % (f.member_id_FK.full_name,),
                    reference_number=f.receipt_number or None,
                    recorded_at=timezone.make_aware(datetime.combine(f.payment_date, datetime.min.time())) if f.payment_date else timezone.now(),
                    recorded_by_user_id_FK=f.recorded_by_user_id_FK,
                )
                _record_audit_trail(
                    table="fund_transaction",
                    record_id=ft.transaction_id_PK,
                    action="BACKFILL_MEMBERSHIP_FEE",
                    actor=f.recorded_by_user_id_FK,
                    old=None,
                    new={
                        "source_type": "membership_fee",
                        "source_id": f.fee_id_PK,
                        "amount": str(f.amount),
                        "member": f.member_id_FK.full_name,
                    },
                    notes="Ledger backfill: approved membership fee had no FundTransaction inflow.",
                )

        dues = MonthlyDues.objects.all()
        for d in dues:
            if str(d.payment_status) not in paid:
                continue
            exists = FundTransaction.objects.filter(source_type="monthly_dues", source_id=d.dues_id_PK).exists()
            if exists:
                continue
            created += 1
            self.stdout.write("monthly_dues dues_id=%s member=%s month=%s amount=%s" % (d.dues_id_PK, d.member_id_FK.full_name, d.month_covered, d.amount))
            if dry:
                continue
            with db_transaction.atomic():
                ft = FundTransaction.objects.create(
                    direction="inflow",
                    amount=d.amount,
                    source_type="monthly_dues",
                    source_id=d.dues_id_PK,
                    description="%s (Monthly Dues)" % (d.member_id_FK.full_name,),
                    reference_number=d.receipt_number or d.remittance_reference or None,
                    recorded_at=timezone.make_aware(datetime.combine(d.payment_date, datetime.min.time())) if d.payment_date else timezone.now(),
                    recorded_by_user_id_FK=d.recorded_by_user_id_FK,
                )
                _record_audit_trail(
                    table="fund_transaction",
                    record_id=ft.transaction_id_PK,
                    action="BACKFILL_MONTHLY_DUES",
                    actor=d.recorded_by_user_id_FK,
                    old=None,
                    new={
                        "source_type": "monthly_dues",
                        "source_id": d.dues_id_PK,
                        "amount": str(d.amount),
                        "member": d.member_id_FK.full_name,
                        "month_covered": d.month_covered,
                    },
                    notes="Ledger backfill: approved monthly dues had no FundTransaction inflow.",
                )

        self.stdout.write(self.style.SUCCESS("%s FundTransaction row(s) created." % created))
