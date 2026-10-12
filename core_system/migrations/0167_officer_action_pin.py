from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0166_fundtransaction_fund_transa_recorde_cc8f2c_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='officeruser',
            name='action_pin_hash',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='officeruser',
            name='action_pin_set_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='officeruser',
            name='action_pin_fail_count',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='officeruser',
            name='action_pin_locked_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='officeruser',
            name='action_pin_lock_minutes',
            field=models.IntegerField(default=1),
        ),
    ]
