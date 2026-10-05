/*
 * Shared top-center notification banner — Treasurer / Auditor / President.
 *
 * Every dashboard module renders its toasts as `.custom-toast` divs inside
 * `#toastContainer` (bottom-right by default). This override repositions that
 * exact same host to the top center of the screen and restyles every toast
 * as a banner modal card, so all existing toast() / showToast() call sites —
 * pending approvals, verification results, errors — pop up top-center with
 * zero changes to the callers.
 */
(function () {
  "use strict";

  if (document.getElementById("top-center-banner-override")) return;

  var css = [
    "#toastContainer.notification-host,",
    "#toastContainer {",
    "  position:fixed !important;",
    "  display:flex !important; flex-direction:column !important;",
    "  top:16px !important; bottom:auto !important;",
    "  left:50% !important; right:auto !important;",
    "  transform:translateX(-50%) !important;",
    "  align-items:center !important;",
    "  margin:0 !important;",
    "  width:min(580px, calc(100vw - 32px)) !important;",
    "  z-index:12000 !important;",
    "  pointer-events:none !important;",
    "}",
    "#toastContainer .custom-toast {",
    "  pointer-events:none !important;",
    "  width:100% !important; max-width:100% !important; min-width:0 !important;",
    "  background:#ffffff !important; color:#1f2937 !important;",
    "  border:1px solid #e2e8e2 !important; border-left:6px solid #2e7d32 !important;",
    "  border-radius:12px !important; padding:12px 14px !important;",
    "  box-shadow:0 12px 32px rgba(0,0,0,0.18) !important;",
    "  backdrop-filter:none !important; -webkit-backdrop-filter:none !important;",
    "  display:flex !important; align-items:center !important; gap:10px !important;",
    "  font-size:0.85rem !important;",
    "  transform:translateY(-18px) !important; opacity:0 !important;",
    "  transition:transform 0.25s ease, opacity 0.25s ease !important;",
    "}",
    "#toastContainer .custom-toast.show {",
    "  transform:translateY(0) !important; opacity:1 !important;",
    "}",
    "#toastContainer .custom-toast.toast-error {",
    "  border-left-color:#e53935 !important;",
    "}",
    "#toastContainer .custom-toast::before {",
    '  content:"\\2713" !important;',
    "  flex:0 0 26px !important; width:26px !important; height:26px !important;",
    "  border-radius:50% !important; background:#e8f5e9 !important; color:#1b5e20 !important;",
    "  display:inline-flex !important; align-items:center !important; justify-content:center !important;",
    "  font-size:0.8rem !important; font-weight:800 !important;",
    "}",
    "#toastContainer .custom-toast.toast-error::before {",
    '  content:"!" !important;',
    "  background:#ffebee !important; color:#c62828 !important;",
    "}",
    "#toastContainer .custom-toast p {",
    "  margin:0 !important; font-weight:600 !important; color:#1f2937 !important;",
    "}",
  ].join("\n");

  var style = document.createElement("style");
  style.id = "top-center-banner-override";
  style.type = "text/css";
  style.appendChild(document.createTextNode(css));
  document.head.appendChild(style);

  var actionCss = [
    "#toastContainer .top-action-card {",
    "  pointer-events:auto !important;",
    "  width:100% !important; max-width:100% !important;",
    "  background:#ffffff !important; color:#1f2937 !important;",
    "  border:1px solid #e2e8e2 !important; border-left:6px solid #1b5e20 !important;",
    "  border-radius:12px !important; padding:12px 14px !important;",
    "  box-shadow:0 12px 32px rgba(0,0,0,0.18) !important;",
    "  display:flex !important; align-items:center !important; gap:10px !important;",
    "  font-size:0.85rem !important;",
    "  transform:translateY(-18px) !important; opacity:0 !important;",
    "  transition:transform 0.25s ease, opacity 0.25s ease !important;",
    "}",
    "#toastContainer .top-action-card.show {",
    "  transform:translateY(0) !important; opacity:1 !important;",
    "}",
    "#toastContainer .top-action-card .top-action-icon {",
    "  flex:0 0 26px !important; width:26px !important; height:26px !important;",
    "  border-radius:50% !important; background:#e8f5e9 !important; color:#1b5e20 !important;",
    "  display:inline-flex !important; align-items:center !important; justify-content:center !important;",
    "  font-size:0.8rem !important; font-weight:800 !important;",
    "}",
    "#toastContainer .top-action-card .top-action-body { flex:1 1 auto !important; min-width:0 !important; }",
    "#toastContainer .top-action-card .top-action-title { font-weight:800 !important; color:#1b5e20 !important; font-size:0.85rem !important; }",
    "#toastContainer .top-action-card .top-action-msg { color:#4b5a50 !important; font-size:0.78rem !important; margin-top:1px !important; }",
    "#toastContainer .top-action-card .top-action-btn {",
    "  flex:0 0 auto !important; cursor:pointer !important; font-family:inherit !important;",
    "  background:#1b5e20 !important; border:1px solid #1b5e20 !important; color:#fff !important;",
    "  border-radius:9px !important; padding:7px 14px !important; font-size:0.78rem !important; font-weight:700 !important;",
    "  white-space:nowrap !important;",
    "}",
    "#toastContainer .top-action-card .top-action-btn:hover { background:#256b29 !important; }",
    "#toastContainer .top-action-card .top-action-x {",
    "  flex:0 0 auto !important; cursor:pointer !important; border:none !important; background:transparent !important;",
    "  color:#8a949e !important; font-size:0.95rem !important; line-height:1 !important; padding:4px !important;",
    "}",
  ].join("\n");

  var actionStyle = document.createElement("style");
  actionStyle.id = "top-action-banner-style";
  actionStyle.type = "text/css";
  actionStyle.appendChild(document.createTextNode(actionCss));
  document.head.appendChild(actionStyle);

  function escAction(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  /*
   * Banner display time (ms), admin-configurable via System Admin →
   * Notification Banner Timer. Default 6000ms. Fetched once per page load.
   */
  var bannerDurationCache = null;
  function bannerDurationMs() {
    if (bannerDurationCache !== null) return Promise.resolve(bannerDurationCache);
    bannerDurationCache = 6000;
    try {
      return fetch("/api/settings/banner-duration/", { cache: "no-store", credentials: "same-origin" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          var s = d && Number(d.value);
          if (s >= 2 && s <= 60) bannerDurationCache = s * 1000;
          return bannerDurationCache;
        })
        .catch(function () { return bannerDurationCache; });
    } catch (e) {
      return Promise.resolve(bannerDurationCache);
    }
  }
  window.bannerDurationMs = bannerDurationMs;

  /*
   * Persistent top-center action banner with a button.
   * opts: { key, title, message, actionLabel, onAction }
   * One card per key per page load; stays until dismissed or acted on.
   */
  window.showTopActionBanner = function showTopActionBanner(opts) {
    try {
      opts = opts || {};
      var key = String(opts.key || "default");
      var host = document.getElementById("toastContainer");
      if (!host) return;
      if (host.querySelector('[data-action-key="' + key + '"]')) return;
      var card = document.createElement("div");
      card.className = "top-action-card";
      card.setAttribute("data-action-key", key);
      card.innerHTML =
        '<span class="top-action-icon">!</span>' +
        '<span class="top-action-body"><span class="top-action-title">' + escAction(opts.title || "Action needed") + "</span>" +
        '<span class="top-action-msg" style="display:block;">' + escAction(opts.message || "") + "</span></span>" +
        '<button type="button" class="top-action-btn">' + escAction(opts.actionLabel || "Open") + "</button>" +
        '<button type="button" class="top-action-x" aria-label="Dismiss">&times;</button>';
      var done = false;
      var timer = null;
      var dismiss = function () {
        if (done) return;
        done = true;
        if (timer) clearTimeout(timer);
        card.classList.remove("show");
        setTimeout(function () { card.remove(); }, 300);
      };
      card.querySelector(".top-action-btn").addEventListener("click", function () {
        try { if (typeof opts.onAction === "function") opts.onAction(); } catch (e) {}
        dismiss();
      });
      card.querySelector(".top-action-x").addEventListener("click", dismiss);
      host.appendChild(card);
      setTimeout(function () { card.classList.add("show"); }, 10);
      // Auto fade-out after the admin-configured display time (default 6s).
      bannerDurationMs().then(function (ms) {
        if (!done) timer = setTimeout(dismiss, ms);
      });
    } catch (e) {}
  };

  var alertCss = [
    "#toastContainer .top-action-card.top-action-alert { border-left-color:#c62828 !important; }",
    "#toastContainer .top-action-card.top-action-alert .top-action-icon { background:#ffebee !important; color:#c62828 !important; }",
    "#toastContainer .top-action-card.top-action-alert .top-action-title { color:#c62828 !important; }",
    "#toastContainer .top-action-card.top-action-alert .top-action-btn { background:#c62828 !important; border-color:#c62828 !important; }",
    "#toastContainer .top-action-card.top-action-alert .top-action-btn:hover { background:#a92323 !important; }",
  ].join("\n");

  var alertStyle = document.createElement("style");
  alertStyle.id = "top-alert-banner-style";
  alertStyle.type = "text/css";
  alertStyle.appendChild(document.createTextNode(alertCss));
  document.head.appendChild(alertStyle);

  /*
   * Blocking top-center alert card. Unlike showTopActionBanner() this one
   * NEVER auto-dismisses — the user has to click the acknowledgement button
   * (or the X) before it goes away. Re-triggering the same key refreshes the
   * message instead of stacking a duplicate card.
   * opts: { key, title, message, confirmLabel }
   * Returns true once the card is on screen.
   */
  window.showTopCenterAlert = function showTopCenterAlert(opts) {
    try {
      opts = opts || {};
      var key = String(opts.key || "alert");
      var host = document.getElementById("toastContainer");
      if (!host) return false;

      var msg = escAction(opts.message || "");
      var title = escAction(opts.title || "Please review this entry");
      var label = escAction(opts.confirmLabel || "Got it");

      var card = host.querySelector('[data-alert-key="' + key + '"]');
      if (card) {
        card.querySelector(".top-action-title").innerHTML = title;
        card.querySelector(".top-action-msg").innerHTML = msg;
        card.querySelector(".top-action-btn").innerHTML = label;
        if (!card.classList.contains("show")) card.classList.add("show");
        return true;
      }

      card = document.createElement("div");
      card.className = "top-action-card top-action-alert";
      card.setAttribute("data-alert-key", key);
      card.innerHTML =
        '<span class="top-action-icon">!</span>' +
        '<span class="top-action-body"><span class="top-action-title">' + title + "</span>" +
        '<span class="top-action-msg" style="display:block;">' + msg + "</span></span>" +
        '<button type="button" class="top-action-btn">' + label + "</button>" +
        '<button type="button" class="top-action-x" aria-label="Dismiss">&times;</button>';
      var closed = false;
      var close = function () {
        if (closed) return;
        closed = true;
        card.classList.remove("show");
        setTimeout(function () { card.remove(); }, 300);
      };
      card.querySelector(".top-action-btn").addEventListener("click", close);
      card.querySelector(".top-action-x").addEventListener("click", close);
      host.appendChild(card);
      setTimeout(function () { card.classList.add("show"); }, 10);
      return true;
    } catch (e) {
      return false;
    }
  };

  function friendlyDateLabel(iso) {
    var p = String(iso || "").split("-");
    if (p.length !== 3) return String(iso || "");
    var d = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
    if (isNaN(d.getTime())) return String(iso || "");
    try {
      return d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
    } catch (e) {
      return String(iso || "");
    }
  }
  window.friendlyDateLabel = friendlyDateLabel;

  function todayISO() {
    var d = new Date();
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + m + "-" + day;
  }

  /*
   * Signed-in officer identity, read from the sidebar rendered by the view.
   */
  function operatorIdentity() {
    var role = "";
    var name = "";
    try {
      role = (document.querySelector(".user-role") || {}).textContent || "";
      name = (document.querySelector(".user-name") || {}).textContent || "";
    } catch (e) {}
    role = String(role).trim() || "Officer";
    name = String(name).trim() || role;
    return { role: role, name: name };
  }
  window.operatorIdentity = operatorIdentity;

  /*
   * Future-date trap. If the bound date input holds a date after today the
   * value is cleared, a blocking top-center alert is shown, and true is
   * returned so the caller can abort its submit.
   * opts: { input, key, phrase } — `phrase` fully describes the problem and
   * already includes the subject and the formatted date.
   * Returns true when the submission/entry must be blocked.
   */
  window.guardFutureDate = function guardFutureDate(opts) {
    try {
      opts = opts || {};
      var el = typeof opts.input === "string" ? document.getElementById(opts.input) : opts.input;
      if (!el || !el.value) return false;
      if (el.value <= todayISO()) return false;

      var operator = operatorIdentity();
      var message = String(opts.phrase || "The selected date is in the future.")
        + " " + operator.role + ": " + operator.name + ". This action is logged in the audit logs.";
      try { el.value = ""; } catch (e) {}
      if (typeof el.dispatchEvent === "function") {
        try { el.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
      }
      window.showTopCenterAlert({
        key: opts.key || "future-date",
        title: opts.title || "Hmm... something isn't right",
        message: message,
        confirmLabel: opts.confirmLabel || "Review the date",
      });
      return true;
    } catch (e) {
      return false;
    }
  };
})();
