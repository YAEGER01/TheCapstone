"""Live-update broadcasts for the ISUCauFA, Inc. fund pages.

Every time a FundTransaction is written or removed, the three officer
dashboards (Treasurer, Auditor, President) get a `fund_updated` websocket
event so the Fund Overview / Fund Ledger / dashboard fund card reload
without a manual refresh.

Bulk writes (bulk_create) bypass post_save, so callers that use them also
call `broadcast_fund_update()` explicitly — see auditor_views, president_views
and treasurer_views aid-release flow.
"""

import logging

from asgiref.sync import async_to_sync
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

OFFICER_FUND_GROUPS = ("treasurer_dashboard", "auditor_dashboard", "president_dashboard")

# Shared fan-out group for every dashboard that shows the fund balance,
# including Member dashboards (MemberDashboardConsumer joins this group in
# addition to its per-member group so the fund cards stay live there too).
FUND_WATCHERS_GROUP = "fund_watchers"


def broadcast_fund_update():
    """Push a fund_updated event to every officer dashboard group."""
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is None:
        return
    for group in OFFICER_FUND_GROUPS + (FUND_WATCHERS_GROUP,):
        try:
            async_to_sync(layer.group_send)(group, {"type": "fund_updated"})
        except Exception:
            # A broken/unavailable channel layer must never break the
            # financial operation that triggered the broadcast.
            logger.debug("fund_updated broadcast to %s failed", group, exc_info=True)


@receiver(post_save, sender="core_system.FundTransaction", dispatch_uid="fund_live_broadcast_save")
def _fund_transaction_saved(sender, instance, **kwargs):
    if kwargs.get("raw"):
        return
    broadcast_fund_update()


@receiver(post_delete, sender="core_system.FundTransaction", dispatch_uid="fund_live_broadcast_delete")
def _fund_transaction_deleted(sender, instance, **kwargs):
    broadcast_fund_update()
