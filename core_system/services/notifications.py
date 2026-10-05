"""Reusable notification service.

`notify_member` / `notify_officer` do three things in one call:

  1. Persist a Notification row (the permanent in-app history behind the bell).
  2. Send a Web Push to every device the recipient has subscribed.
  3. Broadcast a WebSocket event to the recipient's live dashboard group so the
     notification count / bell dot updates instantly (no manual refresh).
  4. Send an Email notification to the recipient's email address.

Web Push is best-effort: missing VAPID keys or a dead subscription never raise
and never break the caller's request.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.mail import send_mail
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

NOTIFICATION_CHANNEL_PUSH = "push"

# Friendly display names for internal notification types. Raw type strings
# (e.g. "zt_new_login") must never leak into email subjects — members and
# officers only ever see plain, human wording.
EMAIL_SUBJECT_NAMES = {
    "zt_new_login": "New Sign-In to Your Account",
    "zt_medium": "Quick Security Notice",
}


def email_subject_for(notification_type: str) -> str:
    """Human-friendly email subject for a notification type."""
    friendly = EMAIL_SUBJECT_NAMES.get(notification_type, notification_type)
    return f"ISUCauFA, Inc.: {friendly}"


def _send_notification_email(
    *,
    notification_type: str,
    recipient_contact: str,
    html_template: str | None,
    thread_template_context: dict | None,
    message: str,
) -> None:
    """Background worker: actually sends one notification email.

    Runs in a daemon thread; any failure is logged and never raised so the
    originating request is unaffected.

    The master email kill switch is honored here: when OFF, no SMTP is
    attempted (the in-app Notification row already saved by the caller is
    unaffected).
    """
    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            logger.warning(
                "Email kill switch is OFF — skipped notification email to %s (%s)",
                recipient_contact, notification_type,
            )
            return
    except Exception:
        pass
    try:
        from core_system.services.email_service import send_html_email

        try:
            subject = email_subject_for(notification_type)
            if html_template:
                send_html_email(
                    subject=subject,
                    recipient_list=[recipient_contact],
                    html_template=html_template,
                    context=thread_template_context or {},
                )
            else:
                # Fallback to plain text for notification types without templates
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient_contact],
                    fail_silently=True,
                )
            logger.info("Email sent successfully to %s for notification: %s", recipient_contact, notification_type)
        finally:
            close_old_connections()
    except Exception as e:
        logger.error("Failed to send email to %s: %s", recipient_contact, e)

# Retry configuration for failed push notifications
MAX_PUSH_RETRIES = 2
PUSH_RETRY_DELAY_SECONDS = 1


def _abs_url(path: str, origin: str | None = None) -> str:
    """Return an absolute URL for push payloads.

    Resolves relative paths against the origin the device subscribed from
    (localhost, an ngrok tunnel, or the production domain) so the notification
    link matches where that device actually opened the app. Falls back to
    settings.BASE_URL when the subscription has no stored origin.
    """
    base = (origin or settings.BASE_URL or "").rstrip("/")
    if not path:
        return base + "/"
    if "://" in path:
        return path
    return base + "/" + path.lstrip("/")


def _broadcast_ws(group_name: str, payload: dict) -> None:
    try:
        async_to_sync(get_channel_layer().group_send)(group_name, payload)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("WS broadcast to %s failed: %s", group_name, exc)


def _send_push_subs(subs, notification_type: str, message: str, url: str) -> None:
    """Send a Web Push payload to a list of PushSubscription rows with retry logic.

    `subs` is a materialized list (evaluated on the request thread) so the
    caller can hand this off to a background worker without re-querying.
    """
    # VAPID Configuration Verification
    logger.info("=== PUSH NOTIFICATION START ===")
    logger.info("Notification Type: %s", notification_type)
    logger.info("Message: %s", message[:100] if message else "")
    logger.info("URL: %s", url)
    
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        logger.warning("VAPID keys not configured - PRIVATE_KEY: %s, PUBLIC_KEY: %s", 
                      bool(settings.VAPID_PRIVATE_KEY), bool(settings.VAPID_PUBLIC_KEY))
        logger.warning("Skipping push notifications due to missing VAPID keys")
        logger.info("=== PUSH NOTIFICATION END (SKIPPED) ===")
        return
    
    logger.info("VAPID keys configured - Push notifications enabled")
    
    try:
        from pywebpush import webpush
        logger.info("pywebpush library available")
    except Exception as exc:
        logger.warning("pywebpush unavailable: %s", exc)
        logger.warning("Skipping push notifications due to missing pywebpush library")
        logger.info("=== PUSH NOTIFICATION END (SKIPPED) ===")
        return

    if not subs:
        logger.info("No push subscriptions found in database - skipping push notifications")
        logger.info("=== PUSH NOTIFICATION END (NO SUBSCRIPTIONS) ===")
        return

    logger.info("Found %d push subscriptions to attempt", len(subs))
    
    # Log subscription details for debugging
    for sub in subs:
        logger.info("Subscription ID: %s, Endpoint: %s, Member ID: %s, Officer ID: %s",
                   sub.subscription_id_PK, sub.endpoint[:50] + "...",
                   sub.member_id_FK_id, sub.officer_id_FK_id)

    payload_url = url or "/"

    # Single small logo only: the payload carries just `badge` (left-side /
    # status-bar logo). No `icon` is sent so devices never render the large
    # right-side logo image.
    # Branding assets AND the click URL resolve against each subscription's own
    # origin (the ngrok tunnel / host the phone actually opened). settings
    # BASE_URL defaults to http://127.0.0.1:8000, which a phone can never
    # reach — absolute logo URLs built from it load as broken images on the
    # device (wrong left logo, placeholder on the right).

    success_count = 0
    failure_count = 0
    retry_count = 0
    
    for sub in subs:
        logger.info("--- Attempting push to subscription %s ---", sub.subscription_id_PK)

        # Resolve click URL and logo against the subscription origin
        # (local/ngrok/production) so both open and load on that device.
        # Use the official CAUFA logo directly; transparent icon fallbacks cause
        # Chrome to substitute its generic app icon in the large slot.
        sub_base = sub.origin or settings.BASE_URL
        badge_url = _abs_url("/static/img/isu_caufa_official_badge.png", sub_base)
        icon_url = _abs_url("/static/img/isu_caufa_official_192.png", sub_base)
        payload = json.dumps({
            "title": notification_type,
            "body": message,
            "url": _abs_url(payload_url, sub_base),
            "icon": icon_url,
            "badge": badge_url,
        })
        
        # Retry logic for each subscription
        for attempt in range(MAX_PUSH_RETRIES):
            try:
                logger.info("Attempt %d/%d for subscription %s", attempt + 1, MAX_PUSH_RETRIES, sub.subscription_id_PK)
                
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh_key, "auth": sub.auth_key},
                    },
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={
                        "sub": "mailto:isucaufa@isucaufa-fms.online",
                    },
                    timeout=10,
                    # Keep the message queued 24h so a phone that is briefly
                    # offline/Doze-asleep still receives it (ttl=0 discards it
                    # instantly — the bell and email would arrive but the
                    # device push would be lost). High urgency wakes Doze.
                    ttl=86400,
                    headers={"Urgency": "high"},
                )
                
                success_count += 1
                logger.info("✓ SUCCESS: Push notification sent to subscription %s on attempt %d", 
                           sub.subscription_id_PK, attempt + 1)
                break  # Success - stop retrying this subscription, move to the next
                
            except Exception as exc:
                error_str = str(exc)
                logger.error("✗ FAILED: Attempt %d/%d for subscription %s: %s", 
                           attempt + 1, MAX_PUSH_RETRIES, sub.subscription_id_PK, error_str)
                
                # If this is not the last attempt, wait before retry
                if attempt < MAX_PUSH_RETRIES - 1:
                    retry_count += 1
                    logger.info("Waiting %d seconds before retry...", PUSH_RETRY_DELAY_SECONDS)
                    time.sleep(PUSH_RETRY_DELAY_SECONDS)
                else:
                    # All retries failed
                    failure_count += 1
                    logger.error("All %d retries failed for subscription %s", MAX_PUSH_RETRIES, sub.subscription_id_PK)
                    
                    # 410 Gone means subscription expired - delete it
                    if "410" in error_str or "Gone" in error_str:
                        logger.info("Subscription %s expired (410 Gone) - deleting from database", sub.subscription_id_PK)
                        try:
                            sub.delete()
                            logger.info("✓ Successfully deleted expired subscription %s", sub.subscription_id_PK)
                        except Exception as delete_exc:
                            logger.warning("✗ Failed to delete expired subscription %s: %s", 
                                         sub.subscription_id_PK, delete_exc)
                    elif "404" in error_str or "Not Found" in error_str:
                        logger.warning("Subscription %s not found (404) - deleting invalid endpoint", sub.subscription_id_PK)
                        try:
                            sub.delete()
                        except Exception as delete_exc:
                            logger.warning("Failed to delete invalid subscription %s: %s", sub.subscription_id_PK, delete_exc)
                    elif "403" in error_str or "Forbidden" in error_str:
                        logger.warning("Subscription %s forbidden (403) - VAPID keys may be invalid", sub.subscription_id_PK)
                    continue  # All retries failed - move on to the next subscription
    
    logger.info("=== PUSH NOTIFICATION SUMMARY ===")
    logger.info("Total subscriptions: %d", len(subs))
    logger.info("Successful deliveries: %d", success_count)
    logger.info("Failed deliveries: %d", failure_count)
    logger.info("Total retries attempted: %d", retry_count)
    logger.info("=== PUSH NOTIFICATION END ===")


def check_subscription_health():
    """Check the health of all push subscriptions in the database."""
    from core_system.models import PushSubscription
    
    logger.info("=== SUBSCRIPTION HEALTH CHECK ===")
    
    try:
        total_subs = PushSubscription.objects.count()
        logger.info("Total subscriptions in database: %d", total_subs)
        
        if total_subs == 0:
            logger.info("No subscriptions found in database")
            return {"total": 0, "active": 0, "expired": 0, "details": []}
        
        member_subs = PushSubscription.objects.filter(member_id_FK__isnull=False).count()
        officer_subs = PushSubscription.objects.filter(officer_id_FK__isnull=False).count()
        
        logger.info("Member subscriptions: %d", member_subs)
        logger.info("Officer subscriptions: %d", officer_subs)
        
        # Check for recently created subscriptions (last 30 days)
        from django.utils import timezone
        from datetime import timedelta
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_subs = PushSubscription.objects.filter(created_at__gte=thirty_days_ago).count()
        
        logger.info("Recent subscriptions (last 30 days): %d", recent_subs)
        
        # Check for old subscriptions (older than 90 days)
        ninety_days_ago = timezone.now() - timedelta(days=90)
        old_subs = PushSubscription.objects.filter(created_at__lt=ninety_days_ago).count()
        
        logger.info("Old subscriptions (older than 90 days): %d", old_subs)
        
        health_report = {
            "total": total_subs,
            "member_subs": member_subs,
            "officer_subs": officer_subs,
            "recent_subs": recent_subs,
            "old_subs": old_subs,
            "vapid_configured": bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY),
        }
        
        logger.info("Subscription Health Report: %s", health_report)
        logger.info("=== SUBSCRIPTION HEALTH CHECK END ===")
        
        return health_report
        
    except Exception as e:
        logger.error("Error during subscription health check: %s", e)
        logger.info("=== SUBSCRIPTION HEALTH CHECK END (ERROR) ===")
        return {"error": str(e)}


def verify_vapid_configuration():
    """Verify VAPID configuration is properly set up."""
    logger.info("=== VAPID CONFIGURATION VERIFICATION ===")
    
    vapid_config = {
        "private_key_configured": bool(settings.VAPID_PRIVATE_KEY),
        "public_key_configured": bool(settings.VAPID_PUBLIC_KEY),
        "private_key_length": len(settings.VAPID_PRIVATE_KEY) if settings.VAPID_PRIVATE_KEY else 0,
        "public_key_length": len(settings.VAPID_PUBLIC_KEY) if settings.VAPID_PUBLIC_KEY else 0,
    }
    
    logger.info("VAPID Private Key Configured: %s", vapid_config["private_key_configured"])
    logger.info("VAPID Public Key Configured: %s", vapid_config["public_key_configured"])
    
    if settings.VAPID_PRIVATE_KEY:
        logger.info("VAPID Private Key Length: %d characters", vapid_config["private_key_length"])
    if settings.VAPID_PUBLIC_KEY:
        logger.info("VAPID Public Key Length: %d characters", vapid_config["public_key_length"])
    
    # Check if pywebpush is available
    try:
        from pywebpush import webpush
        logger.info("pywebpush library: AVAILABLE")
        vapid_config["pywebpush_available"] = True
    except Exception as exc:
        logger.warning("pywebpush library: NOT AVAILABLE - %s", exc)
        vapid_config["pywebpush_available"] = False
    
    # Overall status
    vapid_config["status"] = "OK" if (
        vapid_config["private_key_configured"] and 
        vapid_config["public_key_configured"] and 
        vapid_config["pywebpush_available"]
    ) else "MISSING_REQUIREMENTS"
    
    logger.info("VAPID Configuration Status: %s", vapid_config["status"])
    logger.info("=== VAPID CONFIGURATION VERIFICATION END ===")
    
    return vapid_config


def notify(
    *,
    recipient_type: str,
    recipient_id: int,
    notification_type: str,
    message: str,
    recipient_name: str = "",
    recipient_contact: str = "",
    category: str | None = None,
    url: str = "/",
    ws_group: str | None = None,
    ws_payload: dict | None = None,
    send_push: bool = True,
    sender_name: str = "",
    sender_role: str = "",
    receipt_number: str = "",
    extra_context: dict = None,
    create_notification: bool = True,
    send_email: bool = True,
) -> None:
    """Persist a notification, send Web Push, and broadcast to a WS group."""
    from core_system.models import Notification, PushSubscription

    logger.info("Creating notification for %s %s: type=%s, message=%s", 
               recipient_type, recipient_id, notification_type, message[:50])

    if create_notification:
        notification = Notification.objects.create(
            recipient_type=recipient_type,
            recipient_id=recipient_id,
            recipient_name=recipient_name,
            recipient_contact=recipient_contact,
            notification_type=notification_type,
            message=message,
            delivery_status="Sent",
            category=category,
            channel=NOTIFICATION_CHANNEL_PUSH,
            sender_name=sender_name,
            sender_role=sender_role,
            receipt_number=receipt_number,
        )
        logger.info("Notification created with ID: %s", notification.notification_id_PK)

    if send_push:
        subs = PushSubscription.objects.none()
        if recipient_type == "member":
            # MANDATORY FORCE PUSH: every member email also pushes to ALL of
            # the member's subscribed devices, regardless of the account
            # preference flag. The flag is kept for UI display only.
            subs = PushSubscription.objects.filter(
                member_id_FK_id=recipient_id,
            )
        elif recipient_type == "officer":
            subs = PushSubscription.objects.filter(officer_id_FK_id=recipient_id)

        if subs.exists():
            def _push_worker(sub_list, n_type, msg, n_url):
                try:
                    _send_push_subs(sub_list, n_type, msg, n_url)
                finally:
                    close_old_connections()

            sub_list = list(subs)
            if recipient_type == "member":
                # Member actions must dispatch before the request finishes so
                # a short-lived worker cannot drop the push after saving the
                # notification row. Officer fan-out remains asynchronous.
                _push_worker(sub_list, notification_type, message, url)
            else:
                threading.Thread(
                    target=_push_worker,
                    args=(sub_list, notification_type, message, url),
                    daemon=True,
                ).start()

    # Send email notification using HTML template
    if send_email and recipient_contact and '@' in recipient_contact:
        # Build the email context now (fast, needs request-scope values),
        # then deliver everything in a background thread so the HTTP request
        # returns instantly. SMTP (2-5s) and push delivery (up to 10s per
        # subscription) must never block officer actions.
        thread_template_context = None
        try:
            from core_system.services.email_service import send_html_email  # noqa: F401

            # Map notification types to email templates
            template_map = {
                "Payment Approved": "emails/monthly_dues_approved.html",
                "Payment Rejected": "emails/finance_item_returned.html",
                "Payment Returned": "emails/finance_item_returned.html",
                "Aid Contribution Required": "emails/aid_bulk_contribution_notice.html",
                "Aid Approved – Not Included in Contribution": "emails/aid_processing_notice.html",
                "Claim Approved": "emails/claim_approved_returned.html",
                "Claim Returned": "emails/claim_approved_returned.html",
                "Claim Completed": "emails/claim_completed.html",
                "Aid Released": "emails/aid_released.html",
                "Claim Update": "emails/claim_update.html",
                "Claim Submitted": "emails/claim_submitted.html",
                "Monthly Dues Reminder": "emails/dues_reminder.html",
                "Payment Reminder": "emails/payment_reminder.html",
                "exemption_request": "emails/exemption_request.html",
                "exemption_response": "emails/exemption_response.html",
                "membership_approved": "emails/membership_approved.html",
                "Attendance Completed": "emails/certificate_notification.html",
                "Announcement": "emails/announcement_notification.html",
                "Contribution Recorded": "emails/contribution_recorded.html",
                "Outstanding Reminder": "emails/outstanding_reminder.html",
                "Monthly Deduction": "emails/monthly_deduction_update.html",
                "zt_new_login": "emails/zt_security_notice.html",
                "zt_medium": "emails/zt_security_notice.html",
            }

            # Check if there's a template for this notification type
            html_template = template_map.get(notification_type)

            if html_template:
                # Use HTML template with full branding
                thread_template_context = {
                    "member_name": recipient_name,
                    "notification_type": notification_type,
                    "message": message,
                    "sender_name": sender_name,
                    "sender_role": sender_role,
                    "receipt_number": receipt_number,
                }

                # Merge with provided context if available
                if extra_context:
                    thread_template_context.update(extra_context)
                # Parse month_covered and amount from message if it's a payment approval
                if notification_type == "Payment Approved":
                    import re
                    # Try multiple patterns for month extraction
                    month_match = re.search(r'for (\d{4}-\d{2})', message)
                    if not month_match:
                        month_match = re.search(r'(\d{4}-\d{2})', message)

                    # Try multiple patterns for amount extraction
                    amount_match = re.search(r'₱[\d,]+\.?\d*', message)
                    if not amount_match:
                        amount_match = re.search(r'\([\s₱]*([\d,]+\.?\d*)\)', message)

                    # Check if this is a membership fee payment (no month covered)
                    is_membership_fee = "membership fee" in message.lower()

                    if month_match and not is_membership_fee:
                        from datetime import datetime as dt
                        month_str = month_match.group(1)
                        try:
                            month_date = dt.strptime(month_str, "%Y-%m")
                            thread_template_context["month_covered"] = month_date.strftime("%B %Y")
                        except:
                            thread_template_context["month_covered"] = month_str
                    else:
                        thread_template_context["month_covered"] = "N/A"
                    
                    if amount_match:
                        amount_str = amount_match.group(1) if amount_match.lastindex else amount_match.group(0)
                        thread_template_context["amount"] = amount_str.replace('₱', '').replace('(', '').replace(')', '').strip()
                    else:
                        thread_template_context["amount"] = "0.00"
                    
                    thread_template_context["payment_method"] = "Direct Encoding" if "directly" in message.lower() else "Online Banking"
                    thread_template_context["receipt_number"] = receipt_number or "N/A"
                    thread_template_context["approval_date"] = timezone.now().strftime("%B %d, %Y")
                
                # Parse claim-related notification data
                elif notification_type in ["Claim Approved", "Claim Completed", "Aid Released", "Claim Update", "Claim Submitted", "Claim Returned"]:
                    import re
                    # Extract aid type (Medical Aid or Death Aid)
                    aid_type_match = re.search(r'(Medical Aid|Death Aid)', message)
                    if aid_type_match:
                        thread_template_context["aid_type"] = aid_type_match.group(1)
                    else:
                        thread_template_context["aid_type"] = "Aid"

                    # Derive the human-readable status/action from the message
                    # so templates never render "has been ___ by the ___".
                    lowered = message.lower()
                    if "returned for revision" in lowered or "rejected" in lowered or "return" in lowered:
                        claim_status = "Returned for Revision"
                        claim_action = "Returned for Revision"
                    elif "sent to the president" in lowered or "forwarded to the president" in lowered:
                        claim_status = "Verified - Sent to President"
                        claim_action = "Approved"
                    elif "verified" in lowered:
                        claim_status = "Verified"
                        claim_action = "Approved"
                    elif "approved" in lowered:
                        claim_status = "Approved"
                        claim_action = "Approved"
                    elif "completed" in lowered:
                        claim_status = "Completed"
                        claim_action = "Completed"
                    elif "released" in lowered:
                        claim_status = "Released"
                        claim_action = "Released"
                    elif "submitted" in lowered:
                        claim_status = "Submitted"
                        claim_action = "Submitted"
                    elif "withdrawn" in lowered:
                        claim_status = "Withdrawn"
                        claim_action = "Withdrawn"
                    else:
                        claim_status = notification_type.replace("Claim ", "")
                        claim_action = claim_status
                    thread_template_context["status"] = claim_status
                    thread_template_context["action"] = claim_action
                    # The acting office comes from the sender (Auditor /
                    # Treasurer / President) instead of a hardcoded name.
                    thread_template_context["actor"] = sender_role or "Treasurer"
                    # Surface any trailing "Reason: ..."/"Remarks: ..." as remarks.
                    reason_match = re.search(r'(?:reason|remarks)\s*:\s*(.+)$', message, re.IGNORECASE)
                    if reason_match:
                        thread_template_context["remarks"] = reason_match.group(1).strip()
                    
                    # Extract payout amount for Claim Approved
                    if notification_type == "Claim Approved":
                        amount_match = re.search(r'₱[\d,]+\.?\d*', message)
                        if amount_match:
                            thread_template_context["payout_amount"] = amount_match.group(0).replace('₱', '')
                        else:
                            thread_template_context["payout_amount"] = "0.00"
                        thread_template_context["approval_date"] = timezone.now().strftime("%B %d, %Y")
                    
                    # Set dates for other claim types
                    if notification_type == "Claim Completed":
                        thread_template_context["completion_date"] = timezone.now().strftime("%B %d, %Y")
                    elif notification_type == "Aid Released":
                        thread_template_context["release_date"] = timezone.now().strftime("%B %d, %Y")
                    elif notification_type == "Claim Update":
                        thread_template_context["update_message"] = message
                        thread_template_context["update_date"] = timezone.now().strftime("%B %d, %Y")
                    elif notification_type == "Claim Submitted":
                        thread_template_context["submission_date"] = timezone.now().strftime("%B %d, %Y")
                
                # Parse attendance completion notification data
                elif notification_type == "Attendance Completed":
                    import re
                    # Extract event title from message if not already provided
                    if not thread_template_context.get("event_title"):
                        event_match = re.search(r'event [\'"]([^\'"]+)[\'"]', message)
                        if event_match:
                            thread_template_context["event_title"] = event_match.group(1)
                        else:
                            thread_template_context["event_title"] = "Event"
                    
                    # Check if certificate_number was provided in extra_context (for "Processing" status)
                    if not thread_template_context.get("certificate_number"):
                        thread_template_context["certificate_number"] = "TBD"
                    
                    # Set default values for certificate_notification.html template
                    if not thread_template_context.get("event_venue"):
                        thread_template_context["event_venue"] = "ISUCauFA, Inc. Campus"
                    if not thread_template_context.get("has_pdf_attachment"):
                        thread_template_context["has_pdf_attachment"] = False
                    if not thread_template_context.get("dashboard_url"):
                        thread_template_context["dashboard_url"] = "/member/dashboard"
                    
                    # Set default dates if not provided
                    if not thread_template_context.get("event_date"):
                        thread_template_context["event_date"] = timezone.now().strftime("%B %d, %Y")
                    if not thread_template_context.get("issue_date"):
                        thread_template_context["issue_date"] = timezone.now().strftime("%B %d, %Y")
                
                # Parse announcement notification data
                elif notification_type == "Announcement":
                    import re
                    # Extract announcement title from message if not already provided
                    if not thread_template_context.get("announcement_title"):
                        title_match = re.search(r'New announcement: ([^.]+)', message)
                        if title_match:
                            thread_template_context["announcement_title"] = title_match.group(1).strip()
                        else:
                            thread_template_context["announcement_title"] = "New Announcement"
                    
                    # Set default values if not provided
                    if not thread_template_context.get("announcement_category"):
                        thread_template_context["announcement_category"] = "General"
                    if not thread_template_context.get("announcement_description"):
                        thread_template_context["announcement_description"] = message
                    if not thread_template_context.get("posted_date"):
                        thread_template_context["posted_date"] = timezone.now().strftime("%B %d, %Y")
                    if not thread_template_context.get("expiry_date"):
                        thread_template_context["expiry_date"] = None
                
                # Parse monthly dues reminder notification data
                elif notification_type == "Monthly Dues Reminder":
                    import re
                    # Extract month covered
                    month_match = re.search(r'for\s+([A-Za-z]+\s+\d{4})', message, re.IGNORECASE)
                    if not month_match:
                        month_match = re.search(r'([A-Za-z]+\s+\d{4})', message)
                    if month_match:
                        thread_template_context["month_label"] = month_match.group(1)
                    else:
                        thread_template_context["month_label"] = "N/A"
                    thread_template_context["days_overdue"] = "0"  # Default, can be enhanced with regex
                    thread_template_context["message"] = message
                
                # Parse payment reminder notification data
                elif notification_type == "Payment Reminder":
                    import re
                    # Extract aid type and target month
                    aid_type_match = re.search(r'(Medical Aid|Death Aid)', message)
                    if aid_type_match:
                        thread_template_context["payment_type"] = f"{aid_type_match.group(1)} Contribution"
                    else:
                        thread_template_context["payment_type"] = "Aid Contribution"
                    
                    # Extract amount
                    amount_match = re.search(r'₱[\d,]+\.?\d*', message)
                    if amount_match:
                        thread_template_context["amount"] = amount_match.group(0).replace('₱', '')
                    else:
                        thread_template_context["amount"] = "0.00"
                    
                    # Extract target month
                    month_match = re.search(r'target month:?\s*([A-Za-z]+\s+\d{4})', message, re.IGNORECASE)
                    if not month_match:
                        month_match = re.search(r'([A-Za-z]+\s+\d{4})', message)
                    if month_match:
                        thread_template_context["target_month"] = month_match.group(1)
                    else:
                        thread_template_context["target_month"] = "N/A"
                
                # Parse exemption request notification data
                elif notification_type == "exemption_request":
                    import re
                    # Extract month covered
                    month_match = re.search(r'for\s+([A-Za-z]+\s+\d{4})', message, re.IGNORECASE)
                    if not month_match:
                        month_match = re.search(r'([A-Za-z]+\s+\d{4})', message)
                    if month_match:
                        thread_template_context["month_covered"] = month_match.group(1)
                    else:
                        thread_template_context["month_covered"] = "N/A"
                    thread_template_context["request_date"] = timezone.now().strftime("%B %d, %Y")
                
                # Parse exemption response notification data
                elif notification_type == "exemption_response":
                    import re
                    # Extract month covered
                    month_match = re.search(r'for\s+([A-Za-z]+\s+\d{4})', message, re.IGNORECASE)
                    if not month_match:
                        month_match = re.search(r'([A-Za-z]+\s+\d{4})', message)
                    if month_match:
                        thread_template_context["month_covered"] = month_match.group(1)
                    else:
                        thread_template_context["month_covered"] = "N/A"
                    
                    # Extract status (Approved/Rejected)
                    if "approved" in message.lower():
                        thread_template_context["status"] = "Approved"
                    elif "rejected" in message.lower() or "denied" in message.lower():
                        thread_template_context["status"] = "Rejected"
                    else:
                        thread_template_context["status"] = "Reviewed"
                    
                    thread_template_context["response_date"] = timezone.now().strftime("%B %d, %Y")
                    thread_template_context["remarks"] = message  # Full message as remarks
                
                # Parse membership approved notification data
                elif notification_type == "membership_approved":
                    thread_template_context["approval_date"] = timezone.now().strftime("%B %d, %Y")

                threading.Thread(
                    target=_send_notification_email,
                    kwargs={
                        "notification_type": notification_type,
                        "recipient_contact": recipient_contact,
                        "html_template": html_template,
                        "thread_template_context": thread_template_context,
                        "message": message,
                    },
                    daemon=True,
                ).start()
            else:
                threading.Thread(
                    target=_send_notification_email,
                    kwargs={
                        "notification_type": notification_type,
                        "recipient_contact": recipient_contact,
                        "html_template": None,
                        "thread_template_context": None,
                        "message": message,
                    },
                    daemon=True,
                ).start()
            logger.info("Email dispatch queued for %s (notification: %s)", recipient_contact, notification_type)
        except Exception as e:
            logger.error("Failed to queue email for %s: %s", recipient_contact, e)

    if ws_group:
        _broadcast_ws(
            ws_group,
            ws_payload
            or {
                "type": "notification_created",
                "notification": {
                    "type": notification_type,
                    "message": message,
                    "category": category or "general",
                },
            },
        )


def notify_member(
    member,
    *,
    notification_type: str,
    message: str,
    category: str | None = None,
    url: str = "/member/",
    send_push: bool = True,
    sender_name: str = "",
    sender_role: str = "",
    receipt_number: str = "",
    extra_context: dict = None,
    create_notification: bool = True,
    send_email: bool = True,
) -> None:
    """Notify a Member instance (in-app + phone push + live bell dot + email)."""
    if member is None:
        logger.warning("notify_member called with None member")
        return
    notify(
        recipient_type="member",
        recipient_id=member.member_id_PK,
        notification_type=notification_type,
        message=message,
        recipient_name=member.full_name or "",
        recipient_contact=member.email or member.contact_number or "",
        category=category,
        url=url,
        ws_group=f"member_{member.member_id_PK}",
        ws_payload={
            "type": "notification_created",
            "notification": {
                "type": notification_type,
                "message": message,
                "category": category or "general",
                "sender_name": sender_name,
                "sender_role": sender_role,
                "receipt_number": receipt_number,
            },
        },
        send_push=send_push,
        sender_name=sender_name,
        sender_role=sender_role,
        receipt_number=receipt_number,
        extra_context=extra_context,
        create_notification=create_notification,
        send_email=send_email,
    )


def send_member_push(member=None, *, notification_type: str, message: str, url: str = "/member/", members=None) -> None:
    """Deliver ONLY a Web Push to member(s) devices (background thread).

    Used when Notification rows and emails are created separately (e.g. the
    scheduled dues-reminder engine or bulk aid-contribution notices) so every
    member still gets the phone push, keeping email == push parity for every
    member-facing message.

    `members` (optional iterable of Member) batches multiple members into a
    single background thread.
    """
    from core_system.models import PushSubscription

    member_rows = []
    if members is not None:
        member_rows = [m for m in members if m is not None]
    elif member is not None:
        member_rows = [member]
    if not member_rows:
        return

    ids = [getattr(m, "member_id_PK", None) for m in member_rows]
    ids = [i for i in ids if i is not None]
    if not ids:
        return

    subs = PushSubscription.objects.filter(
        member_id_FK_id__in=ids,
    )
    if not subs.exists():
        return

    def _push_worker(sub_list, n_type, msg, n_url):
        try:
            _send_push_subs(sub_list, n_type, msg, n_url)
        finally:
            close_old_connections()

    _push_worker(list(subs), notification_type, message, url)


def notify_officer(
    officer,
    *,
    notification_type: str,
    message: str,
    category: str | None = None,
    url: str = "/",
    send_push: bool = True,
) -> None:
    """Notify an OfficerUser instance (in-app + phone push + live bell dot)."""
    if officer is None:
        return
    notify(
        recipient_type="officer",
        recipient_id=officer.user_id_PK,
        notification_type=notification_type,
        message=message,
        recipient_name=officer.full_name or "",
        recipient_contact=getattr(officer, "email", "") or "",
        category=category,
        url=url,
        ws_group=f"{str(officer.role or '').lower()}_dashboard",
        ws_payload={
            "type": "notification_created",
            "notification": {
                "type": notification_type,
                "message": message,
                "category": category or "general",
            },
        },
        send_push=send_push,
    )
