# Cross-campus (other-campus) aid declaration.
#
# President declares external aid from the very start on the AssessmentItem
# (recipient_type + campus + beneficiary). External AidTrackingPosts link back
# to that item and carry a frozen display copy so the Release Queue stays
# readable even if the assessment is later revised.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0153_aid_tracking_post_claim_month'),
    ]

    operations = [
        migrations.AddField(
            model_name='assessmentitem',
            name='recipient_type',
            field=models.CharField(choices=[('member', 'Member (internal)'), ('external', 'Other Campus (external)')], default='member', max_length=20),
        ),
        migrations.AddField(
            model_name='assessmentitem',
            name='external_campus',
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name='assessmentitem',
            name='external_beneficiary',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='aidtrackingpost',
            name='assessment_item_id_FK',
            field=models.ForeignKey(blank=True, db_column='assessment_item_id_FK', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='external_aid_posts', to='core_system.assessmentitem'),
        ),
        migrations.AddField(
            model_name='aidtrackingpost',
            name='external_campus',
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AddField(
            model_name='aidtrackingpost',
            name='external_beneficiary',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
