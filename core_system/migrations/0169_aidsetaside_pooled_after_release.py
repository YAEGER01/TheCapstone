"""Flag surplus earmarks a release returned to the pooled reserve.

Schema: ``AidSetAside.pooled_after_release`` (set by ``consume_set_asides``
when it unlinks leftovers the payout did not need).

Backfill: pooled rows whose assessment item already funded a CLOSED claim
(sibling rows linked to a post outside the open finish statuses) are
returned surplus from that release — e.g. an UNFILED row re-appearing after
its claim was filed and released. Flag them so the UNFILED table stops
listing them; the money stays in the reserve headline and stays
re-linkable to future claims.
"""

from django.db import migrations, models


# Mirrors core_system.aid_setaside.OPEN_FINISH_STATUSES (hardcoded: migrations
# must not import app code that can drift).
_OPEN_FINISH_STATUSES = (
    "pending_approval",
    "pending_release",
    "pending_auditor",
    "pending_president",
)


def flag_returned_surplus(apps, schema_editor):
    AidSetAside = apps.get_model("core_system", "AidSetAside")
    AidTrackingPost = apps.get_model("core_system", "AidTrackingPost")

    closed_post_ids = set(
        AidTrackingPost.objects.exclude(
            finish_status__in=_OPEN_FINISH_STATUSES
        ).values_list("post_id_PK", flat=True)
    )
    if not closed_post_ids:
        return

    # Items that already funded a finished claim ...
    done_item_ids = set(
        AidSetAside.objects.filter(
            aid_tracking_post_id_FK_id__in=closed_post_ids
        ).values_list("assessment_item_id_FK_id", flat=True)
    )
    if not done_item_ids:
        return

    # ... their pooled leftovers are returned surplus, not unfiled cases.
    AidSetAside.objects.filter(
        aid_tracking_post_id_FK__isnull=True,
        pooled_after_release=False,
        assessment_item_id_FK_id__in=done_item_ids,
    ).update(pooled_after_release=True)


def unflag_returned_surplus(apps, schema_editor):
    # Reverse re-opens every surplus row as unfiled; the forward filter is
    # what hides them, so unflagging all flagged rows restores prior display.
    AidSetAside = apps.get_model("core_system", "AidSetAside")
    AidSetAside.objects.filter(pooled_after_release=True).update(
        pooled_after_release=False
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core_system", "0168_offline_bot_challenge"),
    ]

    operations = [
        migrations.AddField(
            model_name="aidsetaside",
            name="pooled_after_release",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(flag_returned_surplus, unflag_returned_surplus),
    ]
