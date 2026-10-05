# MonthlyAssessmentDocument.image used Django's default max_length=100
# (VARCHAR(100) on MySQL). Secure-upload paths are
# "secure_uploads/assessment_documents/YYYYMMDD_<slug-up-to-60>_<12hex>.<ext>"
# which exceeds 100 chars for long original filenames, causing
# pymysql.err.DataError (1406, "Data too long for column 'image'") on upload.
# Widen to 500 to match SupportingProof.file.
from django.core.validators import FileExtensionValidator
from django.db import migrations, models

import core_system.models


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0159_alter_feedbackanswer_options"),
    ]

    operations = [
        migrations.AlterField(
            model_name="monthlyassessmentdocument",
            name="image",
            field=models.FileField(
                max_length=500,
                upload_to=core_system.models.assessment_document_upload_path,
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=["jpg", "jpeg", "png", "webp", "gif", "pdf"]
                    )
                ],
            ),
        ),
    ]
