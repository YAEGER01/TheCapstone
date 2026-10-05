# At-rest field encryption: contact numbers, MFA seed, health reason become
# Fernet ciphertext (core_system/fields.py). Columns widen first (token
# overhead ~120 chars), then existing plaintext rows are encrypted in place.
# Reverse decrypts back to plaintext (rollback path).
import core_system.fields
from django.db import migrations, models


def _get_models(apps):
    return (
        apps.get_model("core_system", "OfficerUser"),
        apps.get_model("core_system", "Member"),
        apps.get_model("core_system", "MedicalAid"),
    )


def encrypt_existing(apps, schema_editor):
    OfficerUser, Member, MedicalAid = _get_models(apps)
    for obj in OfficerUser.objects.exclude(mfa_secret__isnull=True).exclude(mfa_secret="").iterator():
        obj.save(update_fields=["mfa_secret"])  # get_prep_value encrypts
    for obj in Member.objects.exclude(contact_number__isnull=True).exclude(contact_number="").iterator():
        obj.save(update_fields=["contact_number"])
    for obj in Member.objects.exclude(emergency_number__isnull=True).exclude(emergency_number="").iterator():
        obj.save(update_fields=["emergency_number"])
    for obj in MedicalAid.objects.exclude(reason_for_request__isnull=True).exclude(reason_for_request="").iterator():
        obj.save(update_fields=["reason_for_request"])


def decrypt_existing(apps, schema_editor):
    # Raw SQL: ORM reads would auto-decrypt via from_db_value, so the prefix
    # check needs the stored ciphertext, not the converted value.
    from core_system.fields import decrypt_str

    jobs = [
        ("officer_user", "mfa_secret", "user_id_PK"),
        ("member", "contact_number", "member_id_PK"),
        ("member", "emergency_number", "member_id_PK"),
        ("medical_aid", "reason_for_request", "medical_aid_id_PK"),
    ]
    with schema_editor.connection.cursor() as cursor:
        for table, column, pk in jobs:
            cursor.execute(
                f"SELECT {pk}, {column} FROM {table}"
                f" WHERE {column} IS NOT NULL AND {column} != ''"
            )
            for row_pk, stored in cursor.fetchall():
                if isinstance(stored, str) and stored.startswith("enc1:"):
                    cursor.execute(
                        f"UPDATE {table} SET {column} = %s WHERE {pk} = %s",
                        [decrypt_str(stored), row_pk],
                    )


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0160_monthlyassessmentdocument_image_max_length"),
    ]

    operations = [
        migrations.AlterField(
            model_name="officeruser",
            name="mfa_secret",
            field=core_system.fields.EncryptedCharField(blank=True, max_length=500, null=True),
        ),
        migrations.AlterField(
            model_name="member",
            name="contact_number",
            field=core_system.fields.EncryptedCharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="member",
            name="emergency_number",
            field=core_system.fields.EncryptedCharField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="medicalaid",
            name="reason_for_request",
            field=core_system.fields.EncryptedTextField(blank=True, null=True),
        ),
        migrations.RunPython(encrypt_existing, decrypt_existing),
    ]
