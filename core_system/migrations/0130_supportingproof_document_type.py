from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0129_alter_monthlyassessment_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='supportingproof',
            name='document_type',
            field=models.CharField(blank=True, db_column='document_type', default='', help_text="Category for aid claim documents: 'request_letter', 'hospital_bill', or 'other'. Empty for legacy/uncategorized uploads.", max_length=50),
        ),
    ]
