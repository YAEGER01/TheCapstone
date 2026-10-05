from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core_system", "0115_add_member_registration_request_contact_number"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="dashboard_access",
            field=models.CharField(default="dashboard", max_length=20),
        ),
    ]
