/* Backup-fallback nudge via the shared top-center banner system.
 *
 * Shows only when the signed-in account has NO fallback at all
 * (no push device, no authenticator app, no unused backup codes).
 * Uses window.showTopActionBanner (top_center_banner.js) when present —
 * auto-dismisses on the admin-configured timer and carries a "Set up" action.
 * Falls back to an equivalent self-built top-center card otherwise.
 * Showing once snoozes for 7 days (per browser).
 */
(function () {
  "use strict";

  var SNOOZE_KEY = "caufa_backup_nudge_snoozed";
  var SNOOZE_MS = 7 * 24 * 60 * 60 * 1000;
  var TITLE = "Add a backup sign-in method";
  var MESSAGE = "If email codes can't reach you, you'll be locked out — set one up (2 min).";
  var ACTION_LABEL = "Set up";

  function snoozed() {
    try {
      var raw = localStorage.getItem(SNOOZE_KEY);
      return !!raw && Date.now() - parseInt(raw, 10) < SNOOZE_MS;
    } catch (e) {
      return false;
    }
  }

  function snooze() {
    try {
      localStorage.setItem(SNOOZE_KEY, String(Date.now()));
    } catch (e) {}
  }

  function goSetup() {
    window.location.href = "/settings/security/";
  }

  function fallbackCard() {
    // Same look/position contract as the shared system: top-center card,
    // click action or X to dismiss, auto-gone after 8s.
    if (document.querySelector('[data-nudge-key="backup-fallback"]')) return;
    var host = document.getElementById("toastContainer");
    if (!host) {
      host = document.createElement("div");
      host.id = "toastContainer";
      host.className = "notification-host";
      host.style.cssText = [
        "position:fixed", "top:16px", "left:50%", "transform:translateX(-50%)",
        "z-index:12000", "width:min(580px,calc(100vw - 32px))",
      ].join(";");
      document.body.appendChild(host);
    }
    var card = document.createElement("div");
    card.setAttribute("data-nudge-key", "backup-fallback");
    card.style.cssText = [
      "background:#fff", "color:#1f2937", "border:1px solid #e2e8e2",
      "border-left:6px solid #1b5e20", "border-radius:12px", "padding:12px 14px",
      "box-shadow:0 12px 32px rgba(0,0,0,.18)", "display:flex",
      "align-items:center", "gap:10px", "font-size:13px", "cursor:pointer",
    ].join(";");
    card.innerHTML =
      '<span style="flex:1"><strong>' + TITLE + '</strong><br>' + MESSAGE + '</span>' +
      '<span style="background:#1b5e20;color:#fff;border-radius:9px;padding:7px 14px;font-weight:700;white-space:nowrap">' +
      ACTION_LABEL + "</span>";
    card.addEventListener("click", function () {
      card.remove();
      goSetup();
    });
    host.appendChild(card);
    setTimeout(function () {
      if (card.parentNode) card.remove();
    }, 8000);
  }

  function nudge() {
    snooze();
    if (typeof window.showTopActionBanner === "function") {
      window.showTopActionBanner({
        key: "backup-fallback",
        title: TITLE,
        message: MESSAGE,
        actionLabel: ACTION_LABEL,
        onAction: goSetup,
      });
    } else {
      fallbackCard();
    }
  }

  if (snoozed()) return;

  fetch("/api/auth/backup-status/", { method: "GET", credentials: "same-origin" })
    .then(function (r) {
      if (!r.ok) return null;
      return r.json().catch(function () { return null; });
    })
    .then(function (d) {
      if (d && d.ok && d.needs_fallback) nudge();
    })
    .catch(function () {});
})();
