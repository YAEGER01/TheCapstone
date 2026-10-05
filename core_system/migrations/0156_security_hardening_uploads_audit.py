# Security hardening: upload validators/dedup hash + fail-closed audit chain.
from django.core.validators import FileExtensionValidator
from django.db import migrations, models
import django.utils.timezone


def backfill_audit_hashes(apps, schema_editor):
    GlobalAuditTrail = apps.get_model("core_system", "GlobalAuditTrail")
    # NULL -> sentinel so the new NOT NULL columns apply; legacy rows verify
    # under the legacy scheme and are reported as `legacy_hash_scheme`.
    GlobalAuditTrail.objects.filter(previous_hash__isnull=True).update(
        previous_hash="0" * 64
    )
    GlobalAuditTrail.objects.filter(entry_hash__isnull=True).update(entry_hash="")
    GlobalAuditTrail.objects.filter(hmac_signature__isnull=True).update(
        hmac_signature=""
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0155_rename_member_cat_member__7a7e8b_idx_member_catc_member__b6ea3f_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="content_sha256",
            field=models.CharField(blank=True, db_index=True, max_length=80, null=True),
        ),
        migrations.AlterField(
            model_name="supportingproof",
            name="file",
            field=models.FileField(
                db_column="file_path",
                max_length=500,
                upload_to="secure_uploads/supporting_proofs/%Y/%m/%d/",
                validators=[
                    FileExtensionValidator(
                        allowed_extensions=[
                            "jpg", "jpeg", "png", "webp", "gif",
                            "pdf", "doc", "docx", "xls", "xlsx",
                            "csv", "txt",
                        ]
                    )
                ],
            ),
        ),
        migrations.RunPython(backfill_audit_hashes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="globalaudittrail",
            name="previous_hash",
            field=models.CharField(default="0" * 64, max_length=64),
        ),
        migrations.AlterField(
            model_name="globalaudittrail",
            name="entry_hash",
            field=models.CharField(default="", max_length=64),
        ),
        migrations.AlterField(
            model_name="globalaudittrail",
            name="hmac_signature",
            field=models.CharField(default="", max_length=64),
        ),
        migrations.AlterField(
            model_name="globalaudittrail",
            name="timestamp",
            field=models.DateTimeField(
                db_index=True, default=django.utils.timezone.now
            ),
        ),
    ]
