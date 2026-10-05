# Advance-payment data consistency for legacy salary-deduction rows.
#
# Audit finding (2026-09-09): the bulk salary-deduction flow created rows for
# FUTURE covered months with is_advance=0 and payment_date = the covered
# month's first day (a synthetic date). The single-entry flow correctly sets
# is_advance and uses the actual recording date.
#
# Data-only correction, limited to what the database itself proves:
#   1. month_covered in the future  ->  is_advance = True
#   2. If a FundTransaction inflow exists for the dues row, its recorded_at is
#      the real approval/booking date -> use that date as payment_date when
#      payment_date is still the synthetic first-of-month value.
# Rows with no ledger row keep their payment_date (nothing invented).
from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    MonthlyDues = apps.get_model("core_system", "MonthlyDues")
    FundTransaction = apps.get_model("core_system", "FundTransaction")

    now_ym = timezone.localdate().strftime("%Y-%m")
    fixed_advance = 0
    fixed_date = 0
    for d in MonthlyDues.objects.all().iterator():
        month = str(d.month_covered or "")
        if len(month) != 7 or month[4] != "-":
            continue
        updates = {}
        if month > now_ym and not d.is_advance:
            updates["is_advance"] = True
        if d.payment_date is not None:
            synthetic = ("%s-01" % month) == d.payment_date.strftime("%Y-%m-%d")
            if synthetic:
                ft = (FundTransaction.objects
                      .filter(source_type="monthly_dues", source_id=d.dues_id_PK)
                      .order_by("recorded_at").first())
                if ft is not None and ft.recorded_at is not None:
                    real = timezone.localdate(ft.recorded_at)
                    if real != d.payment_date:
                        updates["payment_date"] = real
        if updates:
            for k, v in updates.items():
                setattr(d, k, v)
            d.save(update_fields=list(updates.keys()))
            if "is_advance" in updates:
                fixed_advance += 1
            if "payment_date" in updates:
                fixed_date += 1
    print("  is_advance flagged: %d row(s); payment_date corrected from ledger: %d row(s)" % (fixed_advance, fixed_date))


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0120_fix_payment_method_pending'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
