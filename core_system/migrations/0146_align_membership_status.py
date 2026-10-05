# Align membership_status with the By-Laws membership types.
#
# By-Laws membership types are Permanent / Temporary / Retired (see migration
# 0122), but older rows still carry the pre-By-Laws values "Active" and
# "Inactive". Those rows were invisible to every By-Laws filter: the Secretary
# dashboards counted nobody (they filtered on 'Active'), and
# deactivate_overdue_members filtered on iexact="Active" and matched nothing
# once the data had been repaired elsewhere.
#
#   "Active"   -> "Permanent"
#   "Inactive" -> "Deactivated"
#
# Retired / Permanent / Temporary / Pending rows are left untouched, and each
# rewrite is written to the GlobalAuditTrail hash chain.
import hashlib
import hmac as hmac_mod
import json

from django.conf import settings
from django.db import migrations

REPAIRS = {
    "active": "Permanent",
    "inactive": "Deactivated",
}


def _write_trail(GlobalAuditTrail, record_id, old, new):
    latest = GlobalAuditTrail.objects.order_by("-trail_id").first()
    previous_hash = latest.entry_hash if (latest and latest.entry_hash) else "0" * 64
    entry = GlobalAuditTrail.objects.create(
        table_name="member",
        record_id=record_id,
        action="MEMBER_STATUS_ALIGNMENT",
        old_values=old,
        new_values=new,
        actor_type="system",
        actor_id=None,
        actor_name="Migration 0146",
        notes="Rewrote a pre-By-Laws membership_status value to a By-Laws type.",
    )
    chain_str = "%s:%s:%s:%s:%s:%s:%s" % (
        previous_hash,
        "member",
        record_id,
        "MEMBER_STATUS_ALIGNMENT",
        json.dumps(old, sort_keys=True),
        json.dumps(new, sort_keys=True),
        entry.timestamp.isoformat(),
    )
    entry_hash = hashlib.sha256(chain_str.encode()).hexdigest()
    entry.entry_hash = entry_hash
    entry.hmac_signature = hmac_mod.new(
        settings.SECRET_KEY.encode(), entry_hash.encode(), hashlib.sha256
    ).hexdigest()
    entry.save(update_fields=["entry_hash", "hmac_signature"])


def forwards(apps, schema_editor):
    Member = apps.get_model("core_system", "Member")
    GlobalAuditTrail = apps.get_model("core_system", "GlobalAuditTrail")

    changed = 0
    for m in Member.objects.all().only("member_id_PK", "full_name", "membership_status"):
        raw = (m.membership_status or "").strip()
        target = REPAIRS.get(raw.casefold())
        if not target or raw == target:
            continue
        old = {"membership_status": m.membership_status}
        m.membership_status = target
        m.save(update_fields=["membership_status"])
        _write_trail(GlobalAuditTrail, m.member_id_PK, old, {"membership_status": target})
        changed += 1
    print("  membership_status aligned on %d member(s)" % changed)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0145_alter_fundtransaction_source_type_aidsetaside"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
