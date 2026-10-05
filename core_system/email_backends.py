"""SMTP backend with automatic fallback to a secondary account.

Whichever account connects and authenticates first wins:

1. Primary  - ``EMAIL_*`` settings   (Gmail App Password)
2. Fallback - ``FALLBACK_SMTP_*`` settings (cPanel mailbox)

The fallback is attempted when the primary fails at ANY stage — DNS,
connection, TLS, auth (during ``open()``), or a mid-send drop inside
``send_messages()``. A primary that connects and logs in fine but then
stalls past ``EMAIL_TIMEOUT`` or has its socket reset mid-command raises
``SMTPServerDisconnected("Server not connected")`` from ``send_messages``,
so the fallback decision must cover the send itself, not just the
handshake. If both fail, the last error is raised so the existing logging
in ``email_service`` keeps working.
"""

import logging
import smtplib

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.smtp import EmailBackend

logger = logging.getLogger(__name__)


def _require_smtp_tls(which: str, use_tls: bool, use_ssl: bool) -> None:
    """Fail closed: never authenticate/send over a plaintext SMTP wire.

    OTP codes and app-password credentials traverse this connection, so a
    misconfigured EMAIL_USE_TLS=False + EMAIL_USE_SSL=False must break
    startup loudly, not silently downgrade. Disable with EMAIL_REQUIRE_TLS=False
    only for a local plaintext test relay.
    """
    if (use_tls or use_ssl) or not bool(getattr(settings, "EMAIL_REQUIRE_TLS", True)):
        return
    raise ImproperlyConfigured(
        f"{which} has neither TLS nor SSL enabled — refusing plaintext SMTP. "
        "Set EMAIL_USE_TLS=True (port 587) or EMAIL_USE_SSL=True (port 465)."
    )


class AmbiguousSMTPDelivery(smtplib.SMTPException):
    """The server disconnected while a message may already have been accepted."""


def _normalise_smtp_password(password) -> str:
    """Remove formatting spaces from an SMTP app password."""
    return "".join(str(password or "").split())


class FallbackSMTPBackend(EmailBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fell_back = False
        _require_smtp_tls("Primary SMTP (EMAIL_*)", self.use_tls, self.use_ssl)

    def _ensure_connection_usable(self):
        """Discard an idle SMTP socket before reusing it."""
        if self.connection is None:
            return

        try:
            status, _ = self.connection.noop()
            if status != 250:
                raise smtplib.SMTPServerDisconnected("Server not connected")
        except Exception:
            try:
                self.close()
            except Exception:
                pass

    def send_messages(self, email_messages):
        """Send the batch, falling back to the fallback server if the primary dies mid-send.

        Django's ``send_messages`` opens, sends, and closes in one call, so a
        server that accepts the connection and login but drops or stalls
        during MAIL/DATA surfaces here. Retry the same batch once over the
        Gmail fallback; messages that already made it through before the
        drop may arrive twice (identical OTP codes either way — losing the
        mail entirely is worse than a rare duplicate).

        The master email kill switch (Superadmin) is enforced here as the
        last line of defense so even direct ``EmailMessage.send()`` callers
        that bypass ``email_service`` cannot emit SMTP while OFF.
        """
        if not email_messages:
            return 0
        try:
            from core_system.email_killswitch import is_email_sending_enabled

            if not is_email_sending_enabled():
                logger.warning(
                    "Email kill switch is OFF — blocked %d SMTP message(s) at backend.",
                    len(email_messages),
                )
                return 0
        except Exception:
            pass
        self._ensure_connection_usable()
        try:
            return super().send_messages(email_messages)
        except smtplib.SMTPServerDisconnected as exc:
            try:
                self.close()
            except Exception:
                pass
            raise AmbiguousSMTPDelivery(
                "SMTP disconnected during message transmission; delivery status is unknown"
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            # Close any stale/half-open socket left by the failed primary so
            # the retry or fallback gets a genuinely fresh connection instead
            # of reusing a dead one from Django's connection cache.
            try:
                self.close()
            except Exception:
                pass
            if self._fell_back or not self._prepare_fallback():
                raise
            self._fell_back = True
            logger.warning(
                "Primary SMTP died mid-send (%s: %s) — retrying %d message(s) on the fallback SMTP",
                type(exc).__name__, exc, len(email_messages),
            )
            return super().send_messages(email_messages)
        finally:
            # Django only closes connections it created in this call; close
            # reused/stale sockets too so the next send gets a fresh handshake.
            try:
                self.close()
            except Exception:
                pass

    def open(self):
        try:
            result = super().open()
        except Exception:
            if not self._prepare_fallback():
                raise
            self._fell_back = True
            return super().open()

        if self.connection or self._fell_back:
            return result

        # open() failed silently (fail_silently=True) — still try fallback.
        if not self._prepare_fallback():
            return result
        self._fell_back = True
        return super().open()

    def _prepare_fallback(self) -> bool:
        """Swap connection settings to the fallback server. True if ready."""
        if self._fell_back:
            return False

        host = str(getattr(settings, "FALLBACK_SMTP_HOST", "") or "").strip()
        username = str(getattr(settings, "FALLBACK_SMTP_USER", "") or "").strip()
        password = _normalise_smtp_password(getattr(settings, "FALLBACK_SMTP_PASSWORD", ""))
        if not host or not username or not password:
            logger.warning(
                "Fallback SMTP skipped: missing FALLBACK_SMTP_HOST / "
                "FALLBACK_SMTP_USER / FALLBACK_SMTP_PASSWORD in settings."
            )
            return False

        use_tls = bool(getattr(settings, "FALLBACK_SMTP_USE_TLS", True))
        use_ssl = bool(getattr(settings, "FALLBACK_SMTP_USE_SSL", False))
        if use_ssl and use_tls:
            use_ssl = False
        _require_smtp_tls("Fallback SMTP (FALLBACK_SMTP_*)", use_tls, use_ssl)

        # Discard whatever half-open state the failed primary left behind.
        partial_connection = getattr(self, "_partial_connection", None)
        if partial_connection is not None:
            try:
                partial_connection.close()
            except Exception:
                pass
            self._partial_connection = None
        if self.connection is not None:
            try:
                self._close_connection(self.connection)
            except Exception:
                pass
            self.connection = None

        self.host = host
        self.port = int(getattr(settings, "FALLBACK_SMTP_PORT", 587) or 587)
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.use_ssl = use_ssl
        return True
