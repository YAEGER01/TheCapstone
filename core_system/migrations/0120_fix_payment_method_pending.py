# payment_method must never hold a STATUS value. Legacy rows written by the
# pre-fix auto-fee workflows (treasurer_views auto-fee, president officer
# self-enroll, migration 0040 backfill) stored "Pending" in payment_method.
# Data-only correction: "Pending" -> "Unknown" (method genuinely not captured).
from django.db import migrations


def forwards(apps, schema_editor):
    MembershipFee = apps.get_model("core_system", "MembershipFee")
    MembershipFee.objects.filter(payment_method__iexact="Pending").update(payment_method="Unknown")


def backwards(apps, schema_editor):
    # Historical shape is intentionally not restored (it was invalid data).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0119_fund_report_returned_status'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
