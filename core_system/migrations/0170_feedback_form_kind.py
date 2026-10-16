# Generated for FeedbackForm.kind (Pre/Post survey) + paired_pre_FK.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0169_aidsetaside_pooled_after_release'),
    ]

    operations = [
        migrations.AddField(
            model_name='feedbackform',
            name='kind',
            field=models.CharField(choices=[('normal', 'Normal survey'), ('pre', 'Pre-Survey'), ('post', 'Post-Survey')], default='normal', max_length=10),
        ),
        migrations.AddField(
            model_name='feedbackform',
            name='paired_pre_FK',
            field=models.ForeignKey(blank=True, db_column='paired_pre_FK', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='paired_posts', to='core_system.feedbackform'),
        ),
    ]
