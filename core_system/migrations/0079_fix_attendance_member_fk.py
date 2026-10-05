# Generated manually to fix missing member_id_FK column in ATTENDANCE table.
#
# Idempotent: 0076 already creates the attendance table WITH member_id_FK, so
# on a fresh database this migration must not add the column again (MySQL
# raises "Duplicate column name"). Older deployments that pre-date 0076 are
# the only case where the column is genuinely missing — the conditional
# RunPython below covers that.

from django.db import migrations, models
import django.db.models.deletion


def _ensure_attendance_member_fk(apps, schema_editor):
    table = schema_editor.connection.ops.quote_name("attendance")
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, "attendance"
            )
        }
    if "member_id_FK" in columns:
        return
    schema_editor.add_field(
        apps.get_model("core_system", "attendance"),
        models.ForeignKey(
            db_column="member_id_FK",
            on_delete=django.db.models.deletion.CASCADE,
            related_name="attendance_records",
            to="core_system.member",
        ),
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0078_rename_sensitive_r_table_n_c95688_idx_sensitive_r_module_b2b1eb_idx_and_more'),
    ]

    operations = [
        # Add the missing member_id_FK column only when it is actually absent.
        migrations.RunPython(_ensure_attendance_member_fk, migrations.RunPython.noop),
    ]
