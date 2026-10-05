# Upload hardening: content hashes for duplicate-image prevention on
# MonthlyAssessmentDocument (request letter / deduction sheet / deposit slip).
from django.core.validators import FileExtensionValidator
from django.db import migrations, models

import core_system.models


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0156_security_hardening_uploads_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="monthlyassessmentdocument",
            name="content_sha256",
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="monthlyassessmentdocument",
            name="norm_sha256",
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name="monthlyassessmentdocument",
            name="image",
            field=models.FileField(
                upload_to=core_system.models.assessment_document_upload_path,
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["jpg", "jpeg", "png", "webp", "gif", "pdf"]
                    )
                ],
            ),
        ),
    ]
