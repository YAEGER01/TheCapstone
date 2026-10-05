from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0131_alter_fundtransaction_source_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="member",
            name="member_classification",
            field=models.CharField(
                choices=[
                    ("Teaching", "Teaching"),
                    ("Non-Teaching", "Non-Teaching"),
                    ("Retired", "Retired"),
                ],
                db_column="member_classification",
                default="Teaching",
                max_length=20,
            ),
        ),
    ]
