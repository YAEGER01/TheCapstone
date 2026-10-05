from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0137_alter_memberassessment_status_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="memberassessment",
            name="is_excluded",
            field=models.BooleanField(default=False),
        ),
    ]
