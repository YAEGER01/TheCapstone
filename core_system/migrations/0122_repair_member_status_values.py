# Member data repair: invalid status values on a seeded officer record.
#
# Audit finding (2026-09-09): member_id_PK=11 ("Secretary Member") was seeded
# with employment_status="Regular" (not a valid employment status) and
# membership_status="Active" (a member-status value in the membership-TYPE
# field). By-Laws membership types are Permanent / Temporary / Retired and the
# member-management validation expects employment_status Active/Inactive.
#
# Repair (values match what the create-flow would have written):
#   employment_status  "Regular" -> "Active"
#   membership_status  "Active"  -> "Permanent"
#   member_type        ""        -> "Member"
# department stays NULL: no college data exists for this record and none is
# invented — reports display it honestly as "Unassigned/—".
# The repair is written to the GlobalAuditTrail hash chain.
import json

from django.conf import settings
from django.db import migrations
from django.utils import timezone


def forwards(apps, schema_editor):
    Member = apps.get_model("core_system", "Member")
    GlobalAuditTrail = apps.get_model("core_system", "GlobalAuditTrail")

    import hashlib
    import hmac as hmac_mod

    invalid = Member.objects.filter(
        employment_status__iexact="Regular",
        membership_status__iexact="Active",
    )
    for m in invalid:
        old = {
            "employment_status": m.employment_status,
            "membership_status": m.membership_status,
            "member_type": m.member_type or "",
        }
        m.employment_status = "Active"
        m.membership_status = "Permanent"
        m.member_type = "Member"
        m.save(update_fields=["employment_status", "membership_status", "member_type"])

        new = {
            "employment_status": m.employment_status,
            "membership_status": m.membership_status,
            "member_type": m.member_type,
        }
        latest = GlobalAuditTrail.objects.order_by("-trail_id").first()
        previous_hash = latest.entry_hash if (latest and latest.entry_hash) else "0" * 64
        entry = GlobalAuditTrail.objects.create(
            table_name="member",
            record_id=m.member_id_PK,
            action="MEMBER_DATA_REPAIR",
            old_values=old,
            new_values=new,
            actor_type="system",
            actor_id=None,
            actor_name="Data Repair Migration 0122",
            notes="Seeded record carried invalid status values; repaired to By-Laws valid values.",
        )
        old_str = json.dumps(old, sort_keys=True)
        new_str = json.dumps(new, sort_keys=True)
        timestamp_str = entry.timestamp.isoformat()
        chain_str = "%s:%s:%s:%s:%s:%s:%s" % (previous_hash, "member", m.member_id_PK, "MEMBER_DATA_REPAIR", old_str, new_str, timestamp_str)
        entry_hash = hashlib.sha256(chain_str.encode()).hexdigest()
        entry.entry_hash = entry_hash
        entry.hmac_signature = hmac_mod.new(settings.SECRET_KEY.encode(), entry_hash.encode(), hashlib.sha256).hexdigest()
        entry.save(update_fields=["entry_hash", "hmac_signature"])
        print("  Repaired member %s (%s)" % (m.member_id_PK, m.full_name))


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core_system', '0121_salary_advance_consistency'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
