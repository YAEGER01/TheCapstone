# Report workflow distinguishes Returned for Revision (needs correction +
# resubmission) from Rejected (terminal decision). Choices-only change: no
# database schema change (report_status is a varchar column).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0118_schema_drift_renames'),
    ]

    operations = [
        migrations.AlterField(
            model_name='organizationfundreport',
            name='report_status',
            field=models.CharField(
                choices=[
                    ('Draft', 'Draft'),
                    ('Submitted', 'Submitted'),
                    ('Auditor Verified', 'Auditor Verified'),
                    ('Returned for Revision', 'Returned for Revision'),
                    ('Approved', 'Approved'),
                    ('Rejected', 'Rejected'),
                ],
                default='Draft',
                max_length=50,
            ),
        ),
    ]
