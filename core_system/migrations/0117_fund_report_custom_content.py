# Generated for the Reports Management workflow: custom report content
# (title / filters / rows) carried through Treasurer -> Auditor -> President.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0116_member_dashboard_access'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizationfundreport',
            name='report_filters',
            field=models.CharField(blank=True, default='', max_length=300),
        ),
        migrations.AddField(
            model_name='organizationfundreport',
            name='report_rows',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='organizationfundreport',
            name='report_title',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
    ]
