from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0114_memberregistrationrequest_account_creation'),
    ]

    operations = [
        migrations.AddField(
            model_name='memberregistrationrequest',
            name='contact_number',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
