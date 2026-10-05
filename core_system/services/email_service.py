from __future__ import annotations

import base64
import logging
import secrets
import string
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from email.mime.image import MIMEImage
from io import BytesIO
from pathlib import Path
from uuid import UUID
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import connection, transaction
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)

from core_system.constants.policy_constants import (
    get_membership_fee_amount,
    get_monthly_dues_amount,
)
from core_system.models import (
    DEATH_AID_CONTRIBUTION_MAPPING,
    MEDICAL_AID_CONTRIBUTION_AMOUNT,
    Member,
)

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

logger = logging.getLogger(__name__)


# Set when Gmail rejects our SMTP login (dead/rotated App Password). Queued
# retries are pointless until the operator fixes the credential, so the queue
# worker checks this flag and fails fast instead of re-attempting a dead
# login over and over. Cleared automatically on the next successful send.
SMTP_AUTH_FAILED = False
SMTP_DELIVERY_AMBIGUOUS = False

# Serialize all outbound SMTP handshakes. Concurrent EHLO/MAIL/RCPT from the
# queue worker + notification threads can make cPanel drop sockets mid-send
# ("Server not connected" from smtplib when sendall raises OSError).
_SMTP_SEND_LOCK = threading.Lock()
SMTP_RETRY_DELAY_SECONDS = 1.0
SMTP_BULK_BATCH_SIZE = 25


def _get_smtp_retry_delay() -> float:
    try:
        return max(0.0, float(getattr(settings, "SMTP_RETRY_DELAY_SECONDS", SMTP_RETRY_DELAY_SECONDS)))
    except (TypeError, ValueError):
        return SMTP_RETRY_DELAY_SECONDS


def _is_transient_smtp_error(exc: Exception) -> bool:
    """True for dropped-socket / mid-send disconnects worth one retry."""
    import smtplib
    # SMTPException inherits OSError on py3.10 — auth failures are OSError
    # too, but retrying a dead credential only spams the log.
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return False
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return True
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    return False


def _is_smtp_auth_error(exc: Exception) -> bool:
    """True when Gmail refused our login (534 WebLoginRequired / 535)."""
    try:
        import smtplib
        if isinstance(exc, smtplib.SMTPAuthenticationError):
            return True
    except Exception:
        pass
    text = str(exc)
    return ("534" in text and "WebLoginRequired" in text) or (
        "535" in text and "Username and Password not accepted" in text
    )


def _is_otp_email_subject(subject: str) -> bool:
    """Whether a duplicate delivery is safe for this short-lived code."""
    normalized = str(subject or "").lower()
    return any(marker in normalized for marker in _OTP_SUBJECT_MARKERS)


def generate_secure_password(length: int = 12) -> str:
    """Generate a secure random password with mixed case, numbers, and special characters."""
    if length < 8:
        length = 8
    
    # Ensure at least one of each required character type
    chars = []
    chars.append(secrets.choice(string.ascii_lowercase))
    chars.append(secrets.choice(string.ascii_uppercase))
    chars.append(secrets.choice(string.digits))
    chars.append(secrets.choice("!@#$%^&*()_+-=[]{}|;:,.<>?"))
    
    # Fill the rest with random characters from all sets
    all_chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
    chars.extend(secrets.choice(all_chars) for _ in range(length - 4))
    
    # Shuffle to avoid predictable patterns (secrets-based Fisher-Yates)
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return ''.join(chars)


def generate_member_password(join_date=None) -> str:
    """Simple initial password for new member dashboard accounts.

    Format: ISUCauFA_YYMMDD (e.g. ISUCauFA_260519), stamped from the
    member's join date so it is easy to dictate over the phone. The
    account is created with must_change_password=True, so this is only
    a first-login credential delivered to the member's email.
    """
    day = join_date or timezone.now().date()
    return "ISUCauFA_" + day.strftime("%y%m%d")


def _get_logo_data_uri(max_width: int = 120) -> str | None:
    logo_path = Path(settings.BASE_DIR) / "static" / "img" / "isu_caufa_official.png"
    if not logo_path.exists():
        logger.warning("Logo file not found at %s", logo_path)
        return None
    if HAS_PIL:
        try:
            img = Image.open(logo_path)
            if img.mode == "RGBA":
                bg = Image.new("RGB", img.size, (27, 94, 32))
                bg.paste(img, mask=img.split()[3])
                img = bg
            w_percent = max_width / float(img.size[0])
            new_h = int(float(img.size[1]) * float(w_percent))
            img = img.resize((max_width, new_h), Image.LANCZOS)
            buf = BytesIO()
            img.save(buf, format="JPEG", quality=75, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            logger.info("Email logo embedded as data URI (%d bytes)", len(buf.getvalue()))
            return f"data:image/jpeg;base64,{b64}"
        except Exception as exc:
            logger.warning("PIL logo resize failed: %s", exc)
    try:
        with open(logo_path, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode("ascii")
        logger.warning("Email logo embedded as raw base64 PNG (%d bytes)", len(data))
        return f"data:image/png;base64,{b64}"
    except Exception as exc:
        logger.error("Failed to read logo file: %s", exc)
        return None


def send_html_email(
    subject: str,
    recipient_list: list[str],
    html_template: str,
    context: dict | None = None,
    from_email: str | None = None,
) -> bool:
    if not recipient_list:
        return False

    # Master kill switch (Superadmin): refuse ALL SMTP when OFF so a
    # runaway fan-out can never burn the Gmail quota.
    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            logger.warning(
                "Email kill switch is OFF — blocked SMTP send: %s to %s",
                subject, ", ".join(recipient_list),
            )
            return False
    except Exception:
        pass

    msg = _build_html_email_message(
        subject,
        recipient_list,
        html_template,
        context,
        from_email=from_email,
    )

    global SMTP_AUTH_FAILED, SMTP_DELIVERY_AMBIGUOUS
    SMTP_DELIVERY_AMBIGUOUS = False

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            with _SMTP_SEND_LOCK:
                msg.send(fail_silently=False)
            logger.info("Email sent to %s: %s", ", ".join(recipient_list), subject)
            SMTP_AUTH_FAILED = False
            return True
        except Exception as exc:
            last_exc = exc
            if type(exc).__name__ == "AmbiguousSMTPDelivery":
                # A disconnect after DATA has no definitive SMTP outcome.  For
                # normal notifications, do not replay: the first submission
                # may already have been accepted.  MFA/OTP messages are the
                # exception: the same short-lived code remains valid and a
                # duplicate is preferable to locking the officer out.
                if attempt == 0 and _is_otp_email_subject(subject):
                    logger.warning(
                        "SMTP delivery was ambiguous for OTP email to %s; "
                        "retrying once on a fresh Gmail connection",
                        ", ".join(recipient_list),
                    )
                    delay = _get_smtp_retry_delay()
                    if delay:
                        time.sleep(delay)
                    msg = _build_html_email_message(
                        subject, recipient_list, html_template, context, from_email=from_email
                    )
                    continue
                SMTP_DELIVERY_AMBIGUOUS = True
                break
            if attempt == 0 and _is_transient_smtp_error(exc) and not _is_smtp_auth_error(exc):
                logger.warning(
                    "Transient SMTP drop for %s (%s: %s) — retrying once on a fresh connection",
                    ", ".join(recipient_list), type(exc).__name__, exc,
                )
                delay = _get_smtp_retry_delay()
                if delay:
                    time.sleep(delay)
                msg = _build_html_email_message(
                    subject, recipient_list, html_template, context, from_email=from_email
                )
                continue
            break

    exc = last_exc
    if exc is None:
        return False
    if _is_smtp_auth_error(exc):
        SMTP_AUTH_FAILED = True
        primary_user = getattr(settings, "EMAIL_HOST_USER", "")
        fallback_user = getattr(settings, "FALLBACK_SMTP_USER", "") or ""
        logger.error(
            "SMTP login rejected — a password is dead or revoked, so NO email can "
            "go out. Check both accounts in the .env file: primary %s "
            "(EMAIL_HOST_PASSWORD — for Gmail, generate a new App Password in the "
            "account's Security → 2-Step Verification → App passwords settings) and "
            "fallback %s (FALLBACK_SMTP_PASSWORD). Then restart the server. "
            "Original error: %s",
            primary_user, fallback_user, exc,
        )
    else:
        logger.error(
            "Failed to send email to %s: %s: %s",
            ", ".join(recipient_list), type(exc).__name__, exc,
        )
    return False


def _json_safe(value):
    """Coerce values that Django's JSONField cannot serialize."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, UUID):
        return str(value)
    return value


def send_html_email_async(
    subject: str,
    recipient_list: list[str],
    html_template: str,
    context: dict | None = None,
    *,
    defer_worker: bool = False,
) -> bool:
    """Queue an email for background delivery so HTTP requests return instantly.

    The OutgoingEmail row is written synchronously (fast DB insert) and the
    actual SMTP send happens in a daemon thread after the current transaction
    commits. Safe to call inside transaction.atomic() blocks.

    Pass ``defer_worker=True`` when queueing a fan-out loop (e.g. 120+
    collection notices): the row is still written immediately, but no worker
    thread is spawned per recipient. The caller must invoke
    :func:`flush_email_queue_async` once after the loop so a SINGLE worker
    drains the whole batch sequentially instead of 120 threads contending on
    one SMTP connection.
    """
    if not recipient_list:
        return False
    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            logger.warning(
                "Email kill switch is OFF — refused to queue: %s to %s",
                subject, ", ".join(recipient_list),
            )
            return False
    except Exception:
        pass
    try:
        queue_and_process_email(
            subject, recipient_list, html_template, _json_safe(context or {}),
            defer_worker=defer_worker,
        )
        logger.info("Email queued for background delivery to %s: %s", ", ".join(recipient_list), subject)
        return True
    except Exception as exc:
        logger.error("Failed to queue email to %s: %s", ", ".join(recipient_list), exc)
        return False


def _build_html_email_message(subject, recipient_list, html_template, context, from_email=None):
    """Build a branded EmailMultiAlternatives message (no send)."""
    html_content = render_to_string(html_template, context or {})

    text_content = f"""
{subject}

---
This email was sent by ISUCauFA, Inc..
"""

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=from_email or settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
    )
    msg.attach_alternative(html_content, "text/html")

    logo_path = Path(settings.BASE_DIR) / "static" / "img" / "isu_caufa_official.png"
    if logo_path.exists():
        try:
            with open(logo_path, "rb") as f:
                logo_data = f.read()
            image = MIMEImage(logo_data)
            image.add_header("Content-ID", "<logo_cid>")
            image.add_header("Content-Disposition", "inline", filename="isu_caufa_official.png")
            msg.attach(image)
        except Exception:
            pass

    return msg


def _send_bulk_batch(messages):
    from django.core.mail import get_connection

    connection = get_connection()
    try:
        with _SMTP_SEND_LOCK:
            return connection.send_messages(messages) or 0
    finally:
        try:
            connection.close()
        except Exception:
            pass


def send_html_emails_bulk(email_tasks):
    """Send HTML emails in bounded SMTP batches.

    email_tasks: list of dicts with keys subject, recipient_list, html_template,
    context (and optional from_email). Returns the number of messages sent.
    """
    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            logger.warning("Email kill switch is OFF — bulk send refused; nothing sent.")
            return 0
    except Exception:
        pass
    tasks = [
        task
        for task in email_tasks
        if task.get("recipient_list")
    ]
    if not tasks:
        return 0

    try:
        batch_size = max(1, int(getattr(settings, "SMTP_BULK_BATCH_SIZE", SMTP_BULK_BATCH_SIZE)))
    except (TypeError, ValueError):
        batch_size = SMTP_BULK_BATCH_SIZE

    sent = 0
    for start in range(0, len(tasks), batch_size):
        batch_tasks = tasks[start:start + batch_size]
        messages = [
            _build_html_email_message(
                task["subject"],
                task["recipient_list"],
                task["html_template"],
                task.get("context") or {},
                task.get("from_email"),
            )
            for task in batch_tasks
        ]
        for attempt in range(2):
            try:
                sent += _send_bulk_batch(messages)
                break
            except Exception as exc:
                if attempt == 0 and _is_transient_smtp_error(exc) and not _is_smtp_auth_error(exc):
                    logger.warning(
                        "Transient SMTP drop during bulk send (%s: %s) — retrying batch on a fresh connection",
                        type(exc).__name__, exc,
                    )
                    delay = _get_smtp_retry_delay()
                    if delay:
                        time.sleep(delay)
                    continue
                logger.error("Bulk email send failed: %s: %s", type(exc).__name__, exc)
                break

    logger.info("Bulk email: sent %d of %d messages", sent, len(tasks))
    return sent


def send_welcome_member_email(member, officer_contact: str | None = None, treasurer_name: str = "") -> bool:
    """Welcome email for a NEW member created instantly by the Treasurer.

    Uses the canonical member_added template with the standard credentials
    context (ISU email, username, department) so every welcome is consistent.
    """
    return send_member_added_email(member, officer_contact=officer_contact)


def send_member_added_email(member, officer_contact: str | None = None) -> bool:
    if not member.email:
        return False

    officer_user = getattr(member, "officer_user_id_FK", None)
    context = {
        "full_name": member.full_name,
        "email": member.email or "",
        "username": officer_user.username if officer_user else (member.employee_id or "N/A"),
        "old_member": False,
        "date_joined": member.date_joined.strftime("%B %d, %Y") if member.date_joined else str(timezone.now().date()),
        "department": member.department or "",
        "monthly_dues_amount": get_monthly_dues_amount(),
        "membership_fee_amount": get_membership_fee_amount(),
        "officer_contact": officer_contact or "",
        "generated_password": "",
    }

    email_sent = send_html_email_async(
        subject="Welcome to ISUCauFA, Inc. – Membership Registration Confirmed",
        recipient_list=[member.email],
        html_template="emails/member_added.html",
        context=context,
    )
    
    # Create notification for member about their membership
    try:
        from core_system.services.notifications import notify_member
        notify_member(
            member,
            notification_type="Membership Approved",
            message="Welcome to ISUCauFA, Inc.! Your membership has been approved. You can now access all member benefits and services.",
            category="membership",
            sender_name="System",
            sender_role="System",
            # Branded welcome email sent above via send_html_email_async;
            # suppress notify's plain-text fallback so the member gets one email.
            send_email=False,
        )
    except Exception as e:
        logger.warning("Failed to send membership notification to member %s: %s", member.member_id_PK, e)
    
    return email_sent


def send_registration_received_email(
    email: str,
    full_name: str,
    employee_id: str = None,
    include_employee_id: bool = True,
) -> bool:
    if not email:
        return False
    email_sent = send_html_email_async(
        subject="Registration Received – ISUCauFA, Inc. Membership",
        recipient_list=[email],
        html_template="emails/registration_received.html",
        context={
            "full_name": full_name,
            "employee_id": employee_id or "N/A",
            "include_employee_id": include_employee_id,
        },
    )
    
    # Note: This is for public registration before member exists in system
    # Notifications will be created when member is added to system
    
    return email_sent


def send_registration_status_update_email(email: str, full_name: str, new_status: str, next_stage: str) -> bool:
    if not email:
        return False
    return send_html_email_async(
        subject="Registration Update – ISUCauFA, Inc.",
        recipient_list=[email],
        html_template="emails/registration_status_update.html",
        context={
            "full_name": full_name,
            "new_status": new_status,
            "next_stage": next_stage,
        },
    )


def send_registration_returned_email(email: str, full_name: str, reason: str) -> bool:
    if not email:
        return False
    return send_html_email_async(
        subject="Registration Returned for Revision – ISUCauFA, Inc.",
        recipient_list=[email],
        html_template="emails/registration_returned.html",
        context={
            "full_name": full_name,
            "reason": reason,
        },
    )


def send_registration_rejected_email(email: str, full_name: str, reason: str = "") -> bool:
    if not email:
        return False
    return send_html_email_async(
        subject="Registration Status – ISUCauFA, Inc.",
        recipient_list=[email],
        html_template="emails/registration_rejected.html",
        context={
            "full_name": full_name,
            "reason": reason,
        },
    )


# --- Create Member (officer-submitted profile, no login account) ---

def send_create_member_received_email(
    email: str,
    full_name: str,
    department: str = "",
    position: str = "",
    membership_type: str = "",
) -> bool:
    if not email:
        return False
    return send_html_email_async(
        subject="Member Profile Submitted – ISUCauFA, Inc.",
        recipient_list=[email],
        html_template="emails/create_member_received.html",
        context={
            "full_name": full_name,
            "department": department,
            "position": position,
            "membership_type": membership_type,
        },
    )


def send_create_member_status_update_email(
    email: str,
    full_name: str,
    new_status: str,
    next_stage: str,
    department: str = "",
    position: str = "",
    membership_type: str = "",
) -> bool:
    if not email:
        return False
    return send_html_email_async(
        subject="Membership Profile Update – ISUCauFA, Inc.",
        recipient_list=[email],
        html_template="emails/create_member_status_update.html",
        context={
            "full_name": full_name,
            "new_status": new_status,
            "next_stage": next_stage,
            "department": department,
            "position": position,
            "membership_type": membership_type,
        },
    )


def send_create_member_returned_email(email: str, full_name: str, reason: str) -> bool:
    if not email:
        return False
    return send_html_email_async(
        subject="Membership Profile Returned for Revision – ISUCauFA, Inc.",
        recipient_list=[email],
        html_template="emails/create_member_returned.html",
        context={
            "full_name": full_name,
            "reason": reason,
        },
    )


def send_create_member_rejected_email(email: str, full_name: str, reason: str = "") -> bool:
    if not email:
        return False
    return send_html_email_async(
        subject="Membership Profile Status – ISUCauFA, Inc.",
        recipient_list=[email],
        html_template="emails/create_member_rejected.html",
        context={
            "full_name": full_name,
            "reason": reason,
        },
    )


def send_create_member_approved_email(
    email: str,
    full_name: str,
    department: str = "",
    position: str = "",
    membership_type: str = "",
    date_joined: str = "",
) -> bool:
    if not email:
        return False

    # Death Aid contribution depends on the deceased's relationship to the
    # requesting member (mirrors DEATH_AID_CONTRIBUTION_MAPPING groups).
    death_aid_table = [
        ["Member (the member themselves)", DEATH_AID_CONTRIBUTION_MAPPING["member"]],
        ["Spouse (Husband / Wife)", DEATH_AID_CONTRIBUTION_MAPPING["spouse"]],
        ["Parent / Child", DEATH_AID_CONTRIBUTION_MAPPING["parent"]],
        ["Brother / Sister (Sibling)", DEATH_AID_CONTRIBUTION_MAPPING["sibling"]],
    ]

    return send_html_email_async(
        subject="Membership Approved – ISUCauFA, Inc.",
        recipient_list=[email],
        html_template="emails/create_member_approved.html",
        context={
            "full_name": full_name,
            "department": department,
            "position": position,
            "membership_type": membership_type,
            "date_joined": date_joined,
            "medical_aid_contribution": MEDICAL_AID_CONTRIBUTION_AMOUNT,
            "death_aid_table": death_aid_table,
        },
    )


def send_aid_processing_notice(member, aid_type: str) -> bool:
    if not member or not member.email:
        return False

    context = {
        "member_name": member.full_name,
    }

    return send_html_email_async(
        subject="Notice of Aid Processing",
        recipient_list=[member.email],
        html_template="emails/aid_processing_notice.html",
        context=context,
    )


def send_aid_bulk_contribution_notice(contribution_amount: float, aid_type: str, requesting_member_name: str = "A Fellow Member", exclude_member=None) -> bool:
    members = Member.objects.exclude(membership_status__iexact="Retired")
    if exclude_member:
        members = members.exclude(member_id_PK=exclude_member.member_id_PK)

    recipient_emails = list(
        members.exclude(email__isnull=True).exclude(email__exact="").values_list("email", flat=True)
    )
    if not recipient_emails:
        return False

    context = {
        "contribution_amount": f"{contribution_amount:,.2f}",
        "aid_type": aid_type,
        "requesting_member_name": requesting_member_name,
    }

    return send_html_email_async(
        subject="Notice of Active Member Contribution",
        recipient_list=recipient_emails,
        html_template="emails/aid_bulk_contribution_notice.html",
        context=context,
    )


def send_finance_item_returned_email(member, item_label: str = "", details: str = "", remarks: str = "", is_rejected: bool = False) -> bool:
    """Send a member an email when a finance item is returned for revision or rejected."""
    if not member or not member.email:
        return False

    context = {
        "full_name": member.full_name,
        "item_label": item_label or "Payment Item",
        "details": details or "",
        "remarks": remarks or "",
        "is_rejected": is_rejected,
    }

    subject = (
        "Payment Item Rejected – ISUCauFA, Inc."
        if is_rejected
        else "Returned for Revision – ISUCauFA, Inc."
    )

    return send_html_email_async(
        subject=subject,
        recipient_list=[member.email],
        html_template="emails/finance_item_returned.html",
        context=context,
    )


def send_member_finance_status_email(member, item_label: str = "", details: str = "", remarks: str = "", is_rejected: bool = False, sender_name: str = "", sender_role: str = "", receipt_number: str = "") -> bool:
    """Create an in-dashboard notification and send the finance item returned/rejected email.

    This is the single entry point used by every finance reject/return path
    (president, treasurer, auditor) so members receive both channels.
    """
    if member:
        from core_system.services.notifications import notify_member

        notify_member(
            member,
            notification_type="Payment Rejected" if is_rejected else "Payment Returned",
            message=(
                f"Your {item_label or 'payment item'} was rejected."
                + (f" Reason: {remarks}" if remarks else "")
            )
            if is_rejected
            else (
                f"Your {item_label or 'payment item'} was returned for revision."
                + (f" Remarks: {remarks}" if remarks else "")
            ),
            category="payment",
            sender_name=sender_name or "",
            sender_role=sender_role or "",
            receipt_number=receipt_number or "",
            # Branded email sent below via send_finance_item_returned_email;
            # suppress notify's plain-text fallback so the member gets one email.
            send_email=False,
        )

    return send_finance_item_returned_email(
        member,
        item_label=item_label,
        details=details,
        remarks=remarks,
        is_rejected=is_rejected,
    )


def send_contribution_thank_you_email(
    member,
    aid_type: str,
    amount: float,
    target_month: str = "",
    requesting_member_name: str = "A Fellow Member",
) -> bool:
    """Thank a member for a recorded aid contribution (Medical or Death Aid)."""
    if not member or not member.email:
        return False

    context = {
        "member_name": member.full_name,
        "aid_type": aid_type,
        "amount": f"{float(amount):,.2f}",
        "target_month": target_month or "N/A",
        "requesting_member_name": requesting_member_name,
    }

    return send_html_email_async(
        subject=f"Thank You for Your {aid_type} Contribution – ISUCauFA, Inc.",
        recipient_list=[member.email],
        html_template="emails/contribution_thank_you.html",
        context=context,
    )


def send_member_deduction_email(member, deduction_amount: float, deduction_type: str, requesting_member_name: str = "A Fellow Member", aid_type: str = "Aid") -> bool:
    """Send email to a specific member about a deduction from their account."""
    if not member or not member.email:
        return False

    context = {
        "member_name": member.full_name,
        "deduction_amount": f"{deduction_amount:,.2f}",
        "deduction_type": deduction_type,
        "requesting_member_name": requesting_member_name,
        "aid_type": aid_type,
    }

    return send_html_email_async(
        subject=f"Account Deduction Notice - {deduction_type}",
        recipient_list=[member.email],
        html_template="emails/member_deduction_notice.html",
        context=context,
    )


# ---------------------------------------------------------------------------
# Email Queue (fast, non-blocking — replaces threading.Thread)
# ---------------------------------------------------------------------------


def queue_email(subject, recipient_list, html_template, context=None):
    from core_system.models import OutgoingEmail

    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            logger.warning(
                "Email kill switch is OFF — refused to queue: %s", subject,
            )
            return None
    except Exception:
        pass

    _supersede_pending_otp_emails(subject, recipient_list)
    return OutgoingEmail.objects.create(
        recipient_list=recipient_list,
        subject=subject,
        html_template=html_template,
        context=context or {},
    )


def flush_email_queue_async(batch_size=None) -> bool:
    """Spawn ONE daemon thread that drains the queue sequentially.

    Use after a deferred fan-out loop (see ``defer_worker``) so 120 queued
    collection notices are sent one-by-one over a single serialized SMTP
    stream instead of 120 threads fighting over ``_SMTP_SEND_LOCK`` and
    tripping Gmail/cPanel throttling.
    """
    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            logger.warning("Email kill switch is OFF — flush refused; queue left pending.")
            return False
    except Exception:
        pass
    def _run_worker():
        from django.db import close_old_connections
        worker_started = timezone.now()
        try:
            close_old_connections()
            process_email_queue(batch_size=batch_size)
        except Exception:
            logger.exception("Email queue worker crashed")
            try:
                from core_system.models import OutgoingEmail
                OutgoingEmail.objects.filter(
                    status="sending",
                    claimed_at__gte=worker_started,
                ).update(status=OutgoingEmail.PENDING, claimed_at=None)
            except Exception:
                logger.exception("Failed to recover stuck email rows after crash")
        finally:
            try:
                close_old_connections()
            except Exception:
                pass

    def _start_queue_processor():
        thread = threading.Thread(
            target=_run_worker, daemon=True, name="email-queue-flush",
        )
        thread.start()

    try:
        transaction.on_commit(_start_queue_processor)
    except Exception:
        logger.exception("on_commit hook failed; starting email worker directly")
        _start_queue_processor()
    return True


def queue_and_process_email(subject, recipient_list, html_template, context=None, batch_size=None, defer_worker=False):
    """Queue an email and flush the queue after the current transaction commits.

    Fire-and-forget by design: the OutgoingEmail row is the durable record,
    so delivery never depends on the page staying open. Three independent
    nets flush it even if this request's worker dies with the page close:

    1. Immediate daemon thread below (fast path — OTP in seconds).
    2. EmailQueueKickMiddleware piggyback on ANY later traffic.
    3. In-process scheduler (every ~30s OTP drain) + cPanel cron
       ``manage.py process_emails`` when the web process is asleep.

    When ``defer_worker`` is True, only the row is written; no worker is
    spawned. The caller must call :func:`flush_email_queue_async` once after
    queueing the whole batch (bulk collection fan-out for 120+ members).
    """
    from core_system.models import OutgoingEmail

    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            logger.warning(
                "Email kill switch is OFF — refused to queue: %s", subject,
            )
            return None
    except Exception:
        pass

    _supersede_pending_otp_emails(subject, recipient_list)
    email_record = OutgoingEmail.objects.create(
        recipient_list=recipient_list,
        subject=subject,
        html_template=html_template,
        context=context or {},
    )

    if defer_worker:
        # Bulk fan-out: row is durable; the caller flushes once afterwards.
        return email_record

    def _run_worker():
        # Never let a worker-thread exception vanish silently — that is how
        # rows got stuck in "sending" with no OTP ever delivered.
        # close_old_connections: threads must not reuse the request's DB
        # handle (SQLite "database is locked" / MySQL "gone away"), and must
        # not poison it for later requests either.
        from django.db import close_old_connections
        worker_started = timezone.now()
        try:
            close_old_connections()
            process_email_queue(batch_size=batch_size)
        except Exception:
            logger.exception("Email queue worker crashed")
            try:
                # Release rows THIS worker claimed so the next worker retries them.
                OutgoingEmail.objects.filter(
                    status="sending",
                    claimed_at__gte=worker_started,
                ).update(status=OutgoingEmail.PENDING, claimed_at=None)
            except Exception:
                logger.exception("Failed to recover stuck email rows after crash")
        finally:
            try:
                close_old_connections()
            except Exception:
                pass

    def _start_queue_processor():
        thread = threading.Thread(
            target=_run_worker, daemon=True, name="email-queue-flush",
        )
        thread.start()

    try:
        transaction.on_commit(_start_queue_processor)
    except Exception:
        # No transaction active (autocommit) or on_commit unavailable (e.g.
        # TestCase without atomic) — still fire the worker; the row is
        # already committed so the worker can see it.
        logger.exception("on_commit hook failed; starting email worker directly")
        _start_queue_processor()
    return email_record


def _supersede_pending_otp_emails(subject, recipient_list):
    """Prevent an undelivered older OTP from jumping ahead of a resend."""
    from core_system.models import OutgoingEmail

    if not any(marker in str(subject or "").lower() for marker in _OTP_SUBJECT_MARKERS):
        return

    targets = {str(address or "").strip().lower() for address in recipient_list or []}
    if not targets:
        return

    candidates = OutgoingEmail.objects.filter(
        status=OutgoingEmail.PENDING,
        subject__in=[subject],
    )
    for row in candidates.only("outgoing_email_id", "recipient_list"):
        row_targets = {str(address or "").strip().lower() for address in (row.recipient_list or [])}
        if not targets.intersection(row_targets):
            continue
        OutgoingEmail.objects.filter(
            outgoing_email_id=row.outgoing_email_id,
            status=OutgoingEmail.PENDING,
        ).update(
            status=OutgoingEmail.FAILED,
            error_message="Superseded by a newer OTP request",
            claimed_at=None,
            sent_at=timezone.now(),
        )


# Piggyback kick: coalesce bursts so 50 concurrent requests don't spawn 50
# SMTP threads (which is what gets cPanel/Gmail to drop sockets), while
# guaranteeing a drain is never more than KICK_COOLDOWN old.
_KICK_LOCK = threading.Lock()
_LAST_KICK_MONO = 0.0
KICK_COOLDOWN_SECONDS = 10.0


def kick_email_worker(*, batch_size: int = 10) -> bool:
    """Opportunistically flush pending mail in a background thread.

    Safe to call from middleware on every request: cheap timestamp gate,
    never blocks the response, never raises. Returns True when a drain
    thread was started.
    """
    import time as _time

    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            return False
    except Exception:
        pass

    global _LAST_KICK_MONO
    now_mono = _time.monotonic()
    with _KICK_LOCK:
        if now_mono - _LAST_KICK_MONO < KICK_COOLDOWN_SECONDS:
            return False
        _LAST_KICK_MONO = now_mono

    def _kick():
        from django.db import close_old_connections
        try:
            close_old_connections()
            process_email_queue(batch_size=batch_size)
        except Exception:
            logger.exception("Piggyback email drain failed")
        finally:
            try:
                close_old_connections()
            except Exception:
                pass

    try:
        threading.Thread(target=_kick, daemon=True, name="email-queue-kick").start()
        return True
    except Exception:
        logger.exception("Failed to start piggyback email worker")
        return False


def send_aid_emails(record, table_name, per_member_amount):
    """Send aid emails to eligible contributors and notify the requester of exclusion."""
    from core_system.models import Member, Notification, Contribution
    from core_system.services.notifications import send_member_push

    # Determine requesting member name and aid type
    requesting_member_name = "A Fellow Member"
    requester = getattr(record, "member_id_FK", None) if record else None
    if requester:
        requesting_member_name = requester.full_name
    
    # Map table name to human-readable aid type
    aid_type_map = {
        "medical_aid": "Medical Aid",
        "death_aid": "Death Aid",
    }
    aid_type = aid_type_map.get(table_name, "Aid")

    # Notify the requester that they are NOT INCLUDED in the contribution obligation
    if requester and requester.email:
        send_html_email_async(
            subject="Aid Request Approved – You Are Not Included in Contribution",
            recipient_list=[requester.email],
            html_template="emails/aid_processing_notice.html",
            context={
                "member_name": requester.full_name,
                "aid_type": aid_type,
                "excluded": True,
            },
        )
        Notification.objects.create(
            recipient_type="member",
            recipient_id=requester.member_id_PK,
            recipient_name=requester.full_name,
            recipient_contact=requester.email or "",
            notification_type="Aid Approved – Not Included in Contribution",
            message=(
                f"Your {aid_type} request has been approved. "
                f"As the requesting member, you are NOT INCLUDED in the ₱{per_member_amount:,.2f} contribution "
                f"for this aid case. Other eligible members will be notified."
            ),
            category="contribution",
            delivery_status="sent",
        )
    elif requester:
        Notification.objects.create(
            recipient_type="member",
            recipient_id=requester.member_id_PK,
            recipient_name=requester.full_name,
            recipient_contact=requester.email or "",
            notification_type="Aid Approved – Not Included in Contribution",
            message=(
                f"Your {aid_type} request has been approved. "
                f"As the requesting member, you are NOT INCLUDED in the ₱{per_member_amount:,.2f} contribution "
                f"for this aid case. Other eligible members will be notified."
            ),
            category="contribution",
            delivery_status="sent",
        )

    if requester:
        # Email == push parity for the requester's exclusion notice.
        send_member_push(
            requester,
            notification_type="Aid Approved – Not Included in Contribution",
            message=(
                f"Your {aid_type} request has been approved. "
                f"As the requesting member, you are NOT INCLUDED in the ₱{per_member_amount:,.2f} contribution "
                f"for this aid case. Other eligible members will be notified."
            ),
            url="/member/",
        )

    send_aid_bulk_contribution_notice(
        contribution_amount=per_member_amount,
        aid_type=aid_type,
        requesting_member_name=requesting_member_name,
        exclude_member=requester if requester else None,
    )

    # Dashboard notifications for each contributing member (requester excluded)
    members = Member.objects.exclude(membership_status__iexact="Retired")
    if requester:
        members = members.exclude(member_id_PK=requester.member_id_PK)
    if members.exists():
        members_list = list(members)
        for m in members_list:
            Notification.objects.create(
                recipient_type="member",
                recipient_id=m.member_id_PK,
                recipient_name=m.full_name,
                recipient_contact=m.email or "",
                notification_type="Aid Contribution Required",
                message=(
                    f"A {aid_type} request by {requesting_member_name} has been approved. "
                    f"Your contribution of ₱{per_member_amount:,.2f} is requested."
                ),
                category="contribution",
                delivery_status="sent",
            )
        # Email == push parity for the bulk contribution notice to contributors.
        send_member_push(
            members=members_list,
            notification_type="Aid Contribution Required",
            message=(
                f"A {aid_type} request by {requesting_member_name} has been approved. "
                f"Your contribution of ₱{per_member_amount:,.2f} is requested."
            ),
            url="/member/",
        )


def send_attendance_completed_email(member, event_title, event_date, certificate_number, issue_date) -> bool:
    """Send attendance completion email with certificate details."""
    try:
        send_html_email_async(
            subject=f"Your Certificate of Attendance - {event_title}",
            recipient_list=[member.email],
            html_template="emails/attendance_completed.html",
            context={
                "member_name": member.full_name,
                "event_title": event_title,
                "event_date": event_date,
                "certificate_number": certificate_number,
                "issue_date": issue_date,
            },
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send attendance completion email to {member.email}: {e}")
        return False


def send_announcement_notification_email(member, announcement_title, announcement_category, announcement_description, posted_date, expiry_date=None) -> bool:
    """Send announcement notification email to member."""
    try:
        send_html_email_async(
            subject=f"New Announcement: {announcement_title}",
            recipient_list=[member.email],
            html_template="emails/announcement_notification.html",
            context={
                "member_name": member.full_name,
                "announcement_title": announcement_title,
                "announcement_category": announcement_category,
                "announcement_description": announcement_description,
                "posted_date": posted_date,
                "expiry_date": expiry_date,
            },
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send announcement notification email to {member.email}: {e}")
        return False


def _send_queued_email(email_record):
    from core_system.models import OutgoingEmail, Member

    # Master kill switch: never SMTP-send a queued row while OFF. The row
    # is parked back to PENDING so it resumes after re-enable (unless an
    # operator purges the queue explicitly).
    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            logger.warning(
                "Email kill switch is OFF — parked queued email %s as pending",
                getattr(email_record, "outgoing_email_id", "?"),
            )
            try:
                email_record.status = OutgoingEmail.PENDING
                email_record.claimed_at = None
                email_record.save(update_fields=["status", "claimed_at"])
            except Exception:
                pass
            return False
    except Exception:
        pass

    # NOTE: Do NOT recompute recipient_list here. The caller (e.g.
    # send_aid_bulk_contribution_notice) already built the correct list at
    # queue time — including exclusions such as the requesting member of an
    # aid case. Overriding it here sent the "Notice of Active Member
    # Contribution" to the requester, who is explicitly excluded from
    # contributing to their own aid.
    if email_record.html_template == "emails/aid_bulk_contribution_notice.html":
        recipients = set(email_record.recipient_list or [])
        fresh_emails = set(
            Member.objects.exclude(membership_status__iexact="Retired")
            .exclude(email__isnull=True)
            .exclude(email__exact="")
            .values_list("email", flat=True)
        )
        # Keep only recipients that are still active members (drops the
        # requester and anyone who left), preserving queue-time exclusions.
        email_record.recipient_list = sorted(recipients & fresh_emails)

    if email_record.retry_count:
        delay = min(_get_smtp_retry_delay() * email_record.retry_count, 10.0)
        if delay:
            time.sleep(delay)

    if email_record.html_template == "emails/mfa_challenge.html":
        # MFA/Zero Trust codes use Gmail only.  The specialist mailer opens a
        # fresh connection for each request and safely retries short network
        # failures without involving the general cPanel fallback backend.
        from core_system.services.gmail_otp_emailer import send_gmail_otp_email

        ok = send_gmail_otp_email(
            subject=email_record.subject,
            recipients=email_record.recipient_list,
            context=email_record.context,
            delivery_key=email_record.outgoing_email_id,
        )
    else:
        ok = send_html_email(
            subject=email_record.subject,
            recipient_list=email_record.recipient_list,
            html_template=email_record.html_template,
            context=email_record.context,
        )
    if not ok and email_record.retry_count < 2 and not SMTP_AUTH_FAILED and not SMTP_DELIVERY_AMBIGUOUS:
        # Transient SMTP failure (e.g. connection contention between worker
        # threads): put the row back in the queue for another attempt.
        # Skipped when SMTP rejected our login — retrying a dead credential
        # only spams the log until the operator fixes EMAIL_HOST_PASSWORD /
        # FALLBACK_SMTP_PASSWORD.
        email_record.retry_count += 1
        email_record.status = OutgoingEmail.PENDING
        email_record.claimed_at = None
        email_record.save(update_fields=["status", "retry_count", "claimed_at"])
        return False

    email_record.status = OutgoingEmail.SENT if ok else OutgoingEmail.FAILED
    if not ok:
        email_record.error_message = (
            "SMTP login rejected — check EMAIL_HOST_PASSWORD / FALLBACK_SMTP_PASSWORD in .env"
            if SMTP_AUTH_FAILED
            else "SMTP send failed after retries"
        )
    email_record.sent_at = timezone.now()
    email_record.claimed_at = None
    email_record.save(update_fields=["status", "sent_at", "error_message", "claimed_at"])
    return ok


def _get_daily_sent_count():
    """Count emails sent today to enforce daily rate limit."""
    from core_system.models import OutgoingEmail
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return OutgoingEmail.objects.filter(
        status=OutgoingEmail.SENT, sent_at__gte=today_start
    ).count()


_OTP_SUBJECT_MARKERS = ("otp", "verification", "mfa", "zero trust")


def get_latest_otp_status(email: str):
    """Return the delivery status of the newest OTP-ish email to `email`.

    Scanned in Python (not a JSONField lookup) because key lookups are
    unreliable on this MySQL server. Returns a dict with
    ``{"status", "retry_count", "created_at", "sent_at", "subject"}``
    or ``None`` when no OTP mail exists.
    Used by the MFA status poll and the row-based resend gate: a FAILED or
    long-stalled code never arrived, so Resend must stay available instead
    of hitting a blind time-based rate limit.
    """
    from core_system.models import OutgoingEmail

    target = (email or "").strip().lower()
    if not target:
        return None
    try:
        candidates = list(
            OutgoingEmail.objects.order_by("-outgoing_email_id")[:25]
        )
    except Exception:
        logger.exception("get_latest_otp_status query failed")
        return None
    for row in candidates:
        subject = str(getattr(row, "subject", "") or "")
        if not any(m in subject.lower() for m in _OTP_SUBJECT_MARKERS):
            continue
        recipients = [str(r or "").lower() for r in (row.recipient_list or [])]
        if target not in recipients:
            continue
        return {
            "status": row.status,
            "retry_count": row.retry_count,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            "subject": subject,
        }
    return None


def process_email_queue(batch_size=None, daily_limit=None):
    """Send pending emails sequentially with daily rate limiting.

    Atomically claims each row (pending -> sending) via a conditional UPDATE
    so concurrent worker threads never send the same email twice.

    OTP/verification emails are claimed first so a bulk batch ahead of them
    in the queue can never delay a login code.

    Args:
        batch_size: Optional max emails to send per call. If omitted, process
            all pending emails up to the daily limit.
        daily_limit: Max emails to send per day (default from EMAIL_DAILY_LIMIT setting, fallback 450)
    """
    from django.db.models import Case, When, Value, IntegerField

    from core_system.models import OutgoingEmail

    # Master kill switch: refuse to drain; PENDING rows are left untouched
    # so they resume normally once email is re-enabled.
    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            logger.warning("Email kill switch is OFF — queue drain skipped.")
            return 0
    except Exception:
        pass

    if daily_limit is None:
        daily_limit = getattr(settings, "EMAIL_DAILY_LIMIT", 450)

    try:
        daily_limit = int(daily_limit)
    except (TypeError, ValueError):
        logger.warning("Invalid EMAIL_DAILY_LIMIT value %r; falling back to 450.", daily_limit)
        daily_limit = 450

    # Check daily limit before processing
    sent_today = _get_daily_sent_count()
    if sent_today >= daily_limit:
        logger.warning("Daily email limit reached (%d/%d). Queue paused.", sent_today, daily_limit)
        return 0

    # Recover rows stuck in "sending" (worker thread died mid-send).
    # claimed_at records when the row was claimed; created_at alone wrongly
    # treats an old pending row that was *just* claimed as already stale.
    stale_cutoff = timezone.now() - timedelta(minutes=3)
    stuck_q = OutgoingEmail.objects.filter(status="sending")
    stuck_q.filter(claimed_at__isnull=False, claimed_at__lt=stale_cutoff).update(
        status=OutgoingEmail.PENDING, claimed_at=None
    )
    stuck_q.filter(claimed_at__isnull=True, created_at__lt=stale_cutoff).update(
        status=OutgoingEmail.PENDING
    )

    sent_count = 0
    remaining_today = daily_limit - sent_today
    effective_batch = remaining_today if batch_size is None else min(batch_size, remaining_today)

    for _ in range(effective_batch):
        candidate_ids = list(
            OutgoingEmail.objects.filter(status=OutgoingEmail.PENDING)
            .annotate(
                otp_priority=Case(
                    When(subject__icontains="verification", then=Value(0)),
                    When(subject__icontains="OTP", then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            )
            .order_by("otp_priority", "created_at")
            .values_list("outgoing_email_id", flat=True)[:1]
        )
        if not candidate_ids:
            break
        # Atomic claim: only ONE concurrent worker can flip this row to
        # "sending"; everyone else sees 0 rows updated and moves on.
        claimed_count = OutgoingEmail.objects.filter(
            outgoing_email_id=candidate_ids[0],
            status=OutgoingEmail.PENDING,
        ).update(status="sending", claimed_at=timezone.now())
        if claimed_count == 0:
            continue
        claimed = OutgoingEmail.objects.get(outgoing_email_id=candidate_ids[0])

        try:
            if _send_queued_email(claimed):
                sent_count += 1
        except Exception as exc:
            claimed.status = OutgoingEmail.FAILED
            claimed.error_message = str(exc)[:500]
            claimed.retry_count += 1
            claimed.save(update_fields=["status", "error_message", "retry_count"])
            logger.error("Failed to send queued email %s: %s", claimed.outgoing_email_id, exc)

    connection.close()
    return sent_count
