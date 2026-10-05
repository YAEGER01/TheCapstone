from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core_system", "0113_fund_report_verification_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="memberregistrationrequest",
            name="account_creation_requested",
            field=models.BooleanField(default=True),
        ),
    ]
