# Aid Tracking posts were stamped with the wall-clock month in which the
# President approved the claim (``timezone.now()`` at post creation). The
# Auditor's Aid Tracking page labels each card from that ``target_month``,
# so a February 2027 aid approved in September 2026 displayed as
# "September 2026 Aid". The month must come from the aid claim itself —
# the month whose monthly dues the contributions are charged through.
#
# Data-only correction: point every post's ``target_month`` at its linked
# claim's month (MedicalAid.request_date / DeathAid.claim_date), resolved
# via the post's own source pointer with the archive row as fallback.
# Rows whose claim date is missing keep their current value (nothing invented).
from django.db import migrations


def _claim_month(aid_type, record):
    field = "request_date" if aid_type == "medical_aid" else "claim_date"
    claim_date = getattr(record, field, None)
    try:
        month = claim_date.strftime("%Y-%m")
    except (AttributeError, TypeError, ValueError):
        return None
    if len(month) == 7 and month[4] == "-":
        return month
    return None


def forwards(apps, schema_editor):
    AidTrackingPost = apps.get_model("core_system", "AidTrackingPost")
    MedicalAid = apps.get_model("core_system", "MedicalAid")
    DeathAid = apps.get_model("core_system", "DeathAid")

    posts = list(
        AidTrackingPost.objects.select_related("archive_id_FK").all()
    )
    needed = {"medical_aid": set(), "death_aid": set()}
    for post in posts:
        aid_type = post.source_type or (
            post.archive_id_FK.transaction_type if post.archive_id_FK else None
        )
        record_id = post.source_id or (
            post.archive_id_FK.record_id if post.archive_id_FK else None
        )
        if aid_type in needed and record_id is not None:
            needed[aid_type].add(record_id)

    claims = {}
    if needed["medical_aid"]:
        for aid in MedicalAid.objects.filter(
            medical_aid_id_PK__in=needed["medical_aid"]
        ):
            claims[("medical_aid", aid.medical_aid_id_PK)] = aid
    if needed["death_aid"]:
        for aid in DeathAid.objects.filter(
            death_aid_id_PK__in=needed["death_aid"]
        ):
            claims[("death_aid", aid.death_aid_id_PK)] = aid

    fixed = 0
    for post in posts:
        aid_type = post.source_type or (
            post.archive_id_FK.transaction_type if post.archive_id_FK else None
        )
        record_id = post.source_id or (
            post.archive_id_FK.record_id if post.archive_id_FK else None
        )
        record = claims.get((aid_type, record_id))
        if record is None:
            continue
        month = _claim_month(aid_type, record)
        if month and month != post.target_month:
            post.target_month = month
            post.save(update_fields=["target_month"])
            fixed += 1
    print("  aid tracking target_month corrected to claim month: %d row(s)" % fixed)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0152_membercatchupdue'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
