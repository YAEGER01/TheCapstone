"""Reliable Gmail-only delivery for short-lived OTP and MFA messages.

This path deliberately bypasses the general fallback SMTP backend.  MFA codes
need one predictable sender, a fresh SMTP connection per delivery, and a safe
retry policy.  Reusing the same Message-ID means clients group an occasional
duplicate retry instead of showing two unrelated security messages.
"""

from __future__ import annotations

import logging
import smtplib
import time
from email.mime.image import MIMEImage
from email.utils import make_msgid
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _retry_delay() -> float:
    try:
        return max(0.0, float(getattr(settings, "OTP_SMTP_RETRY_DELAY_SECONDS", 1.5)))
    except (TypeError, ValueError):
        return 1.5


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return False
    if isinstance(exc, smtplib.SMTPResponseException):
        # 4xx responses are temporary; 5xx responses require operator action.
        return 400 <= exc.smtp_code < 500
    if isinstance(exc, (smtplib.SMTPServerDisconnected, ConnectionError, TimeoutError, OSError)):
        return True
    # FallbackSMTPBackend converts mid-DATA drops into AmbiguousSMTPDelivery
    # (a plain SMTPException). Retry those too for OTP — a duplicate code is
    # safe, locking the user out is not.
    if isinstance(exc, smtplib.SMTPException):
        text = f"{type(exc).__name__}: {exc}".lower()
        return any(
            marker in text
            for marker in ("disconnect", "not connected", "connection", "timed out", "timeout")
        )
    return False


def _build_message(subject: str, recipients: list[str], context: dict, message_id: str):
    message = EmailMultiAlternatives(
        subject=subject,
        body=(
            f"{subject}\n\n"
            "This is an automated verification message from ISUCauFA, Inc."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
        headers={
            "Message-ID": message_id,
            "Auto-Submitted": "auto-generated",
        },
    )
    message.attach_alternative(render_to_string("emails/mfa_challenge.html", context), "text/html")

    logo_path = Path(settings.BASE_DIR) / "static" / "img" / "isu_caufa_official.png"
    if logo_path.exists():
        try:
            # Downscale the 276KB source logo before attaching. Uploading the
            # full-size PNG inside DATA is what stalled past the socket
            # timeout and got the connection dropped mid-send; a ~160px
            # file is a few KB and matches the 160px render width.
            # Transparency is preserved (RGBA PNG): flattening onto a
            # solid fill would paint a clashing box behind the seal on
            # the gradient header.
            raw = logo_path.read_bytes()
            payload = raw
            subtype = "png"
            try:
                from io import BytesIO

                from PIL import Image

                img = Image.open(BytesIO(raw))
                w_percent = 160 / float(img.size[0])
                img = img.resize((120, int(float(img.size[1]) * w_percent)), Image.LANCZOS)
                buf = BytesIO()
                if img.mode == "RGBA":
                    img.save(buf, format="PNG", optimize=True)
                    subtype = "png"
                else:
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    img.save(buf, format="JPEG", quality=75, optimize=True)
                    subtype = "jpeg"
                payload = buf.getvalue()
            except Exception:
                pass
            logo = MIMEImage(payload, _subtype=subtype)
            logo.add_header("Content-ID", "<logo_cid>")
            logo.add_header("Content-Disposition", "inline", filename="isu_caufa_official.png")
            message.attach(logo)
        except OSError:
            logger.warning("Could not attach OTP email logo", exc_info=True)
    return message


def send_gmail_otp_email(
    *,
    subject: str,
    recipients: list[str],
    context: dict,
    delivery_key: int | str | None = None,
) -> bool:
    """Send an MFA email through Gmail with one retry on transient failure.

    Returns ``True`` only after Gmail confirms acceptance.  It does not send
    through the cPanel fallback provider, so every OTP has the Gmail sender
    the user expects.
    """
    try:
        from core_system.email_killswitch import is_email_sending_enabled

        if not is_email_sending_enabled():
            logger.warning(
                "Email kill switch is OFF — blocked OTP email to %s",
                ", ".join(recipients or []),
            )
            return False
    except Exception:
        pass
    recipients = [str(item).strip() for item in recipients if str(item).strip()]
    if not recipients:
        return False

    message_id = make_msgid(idstring=f"caufa-otp-{delivery_key or 'direct'}")
    for attempt in range(2):
        connection = get_connection(
            backend="django.core.mail.backends.smtp.EmailBackend",
            host=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            username=settings.EMAIL_HOST_USER,
            password=settings.EMAIL_HOST_PASSWORD,
            use_tls=settings.EMAIL_USE_TLS,
            use_ssl=settings.EMAIL_USE_SSL,
            timeout=settings.EMAIL_TIMEOUT,
            fail_silently=False,
        )
        try:
            message = _build_message(subject, recipients, context, message_id)
            accepted = connection.send_messages([message])
            if accepted == 1:
                logger.info("Gmail accepted OTP email to %s", ", ".join(recipients))
                return True
            raise smtplib.SMTPException("Gmail did not accept the OTP message")
        except Exception as exc:
            if attempt == 0 and _is_retryable(exc):
                logger.warning(
                    "Gmail OTP attempt failed (%s: %s); retrying once with a fresh connection",
                    type(exc).__name__, exc,
                )
                delay = _retry_delay()
                if delay:
                    time.sleep(delay)
                continue
            logger.error("Gmail OTP delivery failed for %s: %s", ", ".join(recipients), exc)
            return False
        finally:
            try:
                connection.close()
            except Exception:
                pass
    return False
