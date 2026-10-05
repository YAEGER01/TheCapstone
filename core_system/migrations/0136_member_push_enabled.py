from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0135_globalaudittrail_result"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="push_enabled",
            field=models.BooleanField(db_column="push_enabled", default=False),
        ),
    ]
