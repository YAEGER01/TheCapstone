/**
 * ZERO TRUST - client companion (officer dashboards).
 *
 * The server enforces everything; this file only:
 *   1. Polls /api/auth/zero-trust/status/ and renders the badge + level.
 *   2. Reports client-attested environment (timezone, screen) as SOFT signals.
 *   3. Shows a toast when the server flags a medium check.
 *   4. Intercepts 403 hard-check challenges (fetch + XHR) and runs the
 *      email-OTP modal, retrying the original request after success.
 *   5. Keeps window.ensureZeroTrust() working for existing call sites - it
 *      now genuinely blocks until the hard check passes (or returns false).
 */
(function () {
  "use strict";

  var STATUS_URL = "/api/auth/zero-trust/status/";
  var CHALLENGE_URL = "/api/auth/zero-trust/challenge/";
  var VERIFY_URL = "/api/auth/zero-trust/verify/";
  var LOCK_URL = "/api/auth/zt/lock/";
  var HEARTBEAT_URL = "/api/auth/zt/heartbeat/";
  var UNLOCK_URL = "/api/auth/zt/unlock/";
  var POLL_MS = 30000;
  // Session-death navigation goes through the obfuscated landing link
  // (UrlObf, when loaded) so the address bar never shows a plain flag.
  function goSessionExpired() {
    try {
      if (window.UrlObf && typeof window.UrlObf.goSessionExpired === "function") {
        window.UrlObf.goSessionExpired();
        return;
      }
    } catch (e) {}
    window.location.href = "/?session_expired=1";
  }
  var HEARTBEAT_MS = 45000;
  var IDLE_LOCK_MS = 2 * 60 * 1000;  // screen lock after idle (superadmin-editable via status poll)
  var AUTO_SIGNOUT_MS = 5 * 60 * 1000;  // auto sign-out once locked (superadmin-editable via status poll)

  var state = {
    checked: false,
    stopped: false,
    level: "none",
    reasons: [],
    fingerprint: {},
    locked: false,
    officerName: "",
    officerRole: "",
    maskedEmail: "",
    lockNote: "",
    lastEnv: null,
    lastMediumKey: "",
    hardCheck: null
  };

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  function getCookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : "";
  }

  function csrfToken() {
    var el = document.querySelector("[name=csrfmiddlewaretoken]");
    return (el && el.value) || getCookie("csrftoken") || "";
  }

  function getClientEnv() {
    var env = {};
    try {
      env.tz = (Intl && Intl.DateTimeFormat && Intl.DateTimeFormat().resolvedOptions().timeZone) || "";
      env.screen = window.screen ? screen.width + "x" + screen.height : "";
      env.plat = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
      if (navigator.hardwareConcurrency) env.cores = String(navigator.hardwareConcurrency);
    } catch (e) { /* soft signals only */ }
    return env;
  }

  function envQuery(env) {
    var parts = [];
    for (var k in env) {
      if (Object.prototype.hasOwnProperty.call(env, k) && env[k]) {
        parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(env[k]));
      }
    }
    return parts.length ? "?" + parts.join("&") : "";
  }

  // ------------------------------------------------------------------
  // Badge
  // ------------------------------------------------------------------

  function sinceLabel(iso) {
    if (!iso) return "";
    var mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
    if (isNaN(mins) || mins < 0) return "";
    if (mins < 60) return mins + "m";
    return Math.floor(mins / 60) + "h " + (mins % 60) + "m";
  }

  function setBadge(cls, icon, label, detail, title) {
    var badge = document.getElementById("zt-badge");
    var container = document.getElementById("zt-badge-container");
    if (!badge) return;
    badge.className = "zt-badge " + cls;
    badge.innerHTML = '<span class="zt-icon">' + icon + '</span><span class="zt-label">' + label + "</span>" +
      (detail ? '<span class="zt-detail"></span>' : "");
    if (detail) badge.querySelector(".zt-detail").textContent = detail;
    badge.title = title || "Zero Trust status";
    if (container && container.hidden) container.hidden = false; // reveal only after the first real check
    badge.onclick = cls === "zt-badge-hard" ? function () { runHardCheck(); } : null;
  }

  function renderStatus(data) {
    state.level = data.level || "none";
    state.reasons = data.reasons || [];
    state.fingerprint = data.fingerprint || {};
    if (typeof data.officer_name === "string") state.officerName = data.officer_name;
    if (typeof data.officer_role === "string") state.officerRole = data.officer_role;
    if (typeof data.masked_email === "string") state.maskedEmail = data.masked_email;
    if (typeof data.lock_note === "string") state.lockNote = data.lock_note;
    if (data.lock_idle_seconds > 0) {
      // Superadmin-editable: rearm the idle timer with the current setting.
      IDLE_LOCK_MS = data.lock_idle_seconds * 1000;
      resetIdleTimer();
    }
    if (data.lock_auto_signout_seconds > 0) {
      // Superadmin-editable: how long a locked screen gets before sign-out.
      AUTO_SIGNOUT_MS = data.lock_auto_signout_seconds * 1000;
    }
    var fp = state.fingerprint;
    var since = sinceLabel(fp.logged_in_since);

    // Another tab (or the server backstop) locked the session - engage here too.
    if (data.locked) {
      engageLock(false);
      if (typeof data.lock_expires_in_seconds === "number") syncSignoutDeadline(data.lock_expires_in_seconds);
      return;
    }
    if (state.locked) dismissLock(true);

    if (state.level === "hard") {
      setBadge("zt-badge-hard", "!", "ZT", "Verify now", "Verification required: " + state.reasons.join("; "));
    } else if (state.level === "medium") {
      setBadge("zt-badge-unverified", "🛡", "ZT", "Checked", "Security notice: " + state.reasons.join("; "));
    } else if (data.verified) {
      setBadge("zt-badge-verified", "🛡", "ZT", fp.ip + " · " + since, "ZT Verified · IP: " + fp.ip + " · " + since);
    } else {
      setBadge("zt-badge-unverified", "?", "ZT", "Needs confirmation", "Awaiting first confirmation");
    }
  }

  function renderError() {
    setBadge("zt-badge-error", "✗", "ZT Error", "", "Zero Trust status unavailable");
  }

  // ------------------------------------------------------------------
  // Status polling (also reports the client env as soft signals)
  // ------------------------------------------------------------------

  async function pollStatus() {
    if (state.stopped) return;
    var env = getClientEnv();
    var qs = envQuery(env);
    state.lastEnv = JSON.stringify(env);
    try {
      var resp = await fetch(STATUS_URL + qs, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin"
      });
      if (resp.status === 401) {
        state.stopped = true;
        // Locked screens poll until the auto sign-out kills the session -
        // a 401 here means that happened: leave for the login page.
        if (state.locked) { goSessionExpired(); return; }
        renderError();
        return;
      }
      var data = await resp.json();
      if (!data.ok) { renderError(); return; }
      renderStatus(data);
      state.checked = true;
    } catch (e) {
      if (state.checked) renderError();
    }
  }

  function startPolling() {
    pollStatus();
    setInterval(function () {
      // Re-send env only when it changed; otherwise a bare poll.
      var env = getClientEnv();
      if (JSON.stringify(env) !== state.lastEnv) { pollStatus(); return; }
      fetch(STATUS_URL, { headers: { "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin" })
        .then(function (r) {
          if (r.status === 401 && state.locked) { goSessionExpired(); return null; }
          return r.ok ? r.json() : null;
        })
        .then(function (data) { if (data && data.ok) { renderStatus(data); state.checked = true; } })
        .catch(function () { if (state.checked) renderError(); });
    }, POLL_MS);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) pollStatus();
    });
  }

  // ------------------------------------------------------------------
  // Toasts (medium check notifications)
  // ------------------------------------------------------------------

  function toast(message, kind) {
    var wrap = document.getElementById("zt-toast-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.id = "zt-toast-wrap";
      document.body.appendChild(wrap);
    }
    var t = document.createElement("div");
    t.className = "zt-toast zt-toast-" + (kind || "info");
    t.textContent = message;
    t.onclick = function () { t.remove(); };
    wrap.appendChild(t);
    setTimeout(function () { t.remove(); }, 8000);
  }

  function handleResponseSignals(resp) {
    var level = resp.headers.get("X-Zero-Trust-Level");
    if (!level) return;
    var reasons = "";
    try { reasons = decodeURIComponent(resp.headers.get("X-Zero-Trust-Reasons") || ""); } catch (e) { /* no reason */ }
    if (level === "medium") {
      var key = reasons || "medium";
      if (state.lastMediumKey !== key) {
        state.lastMediumKey = key;
        toast("Security notice: " + (reasons || "your session environment changed.") + " If this wasn't you, change your password.", "warn");
        pollStatus();
      }
    } else if (level === "soft") {
      pollStatus();
    }
  }

  // ------------------------------------------------------------------
  // Hard check modal (email OTP)
  // ------------------------------------------------------------------

  function ensureModal() {
    var backdrop = document.getElementById("zt-modal-backdrop");
    if (backdrop) return backdrop;
    backdrop = document.createElement("div");
    backdrop.id = "zt-modal-backdrop";
    backdrop.innerHTML =
      '<div class="zt-modal" role="dialog" aria-modal="true" aria-label="Additional verification">' +
      '  <div class="zt-modal-icon">🛡</div>' +
      '  <h3>Additional verification required</h3>' +
      '  <p class="zt-modal-reason"></p>' +
      '  <p class="zt-modal-sent">We sent a 6-digit code to your email. Enter it below to continue.</p>' +
      '  <input id="zt-otp-input" class="zt-otp-input" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="••••••" />' +
      '  <div class="zt-modal-error" hidden></div>' +
      '  <div class="zt-modal-actions">' +
      '    <button type="button" id="zt-verify-btn" class="zt-btn zt-btn-primary">Verify</button>' +
      '    <button type="button" id="zt-resend-btn" class="zt-btn zt-btn-link">Resend code</button>' +
      '    <button type="button" id="zt-cancel-btn" class="zt-btn zt-btn-link">Cancel</button>' +
      "  </div>" +
      "</div>";
    document.body.appendChild(backdrop);

    backdrop.querySelector("#zt-verify-btn").addEventListener("click", submitOtp);
    backdrop.querySelector("#zt-resend-btn").addEventListener("click", requestChallenge);
    backdrop.querySelector("#zt-cancel-btn").addEventListener("click", function () { finishHardCheck(false); });
    backdrop.querySelector("#zt-otp-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") submitOtp();
    });
    return backdrop;
  }

  function showModal(reason) {
    var backdrop = ensureModal();
    backdrop.hidden = false;
    backdrop.querySelector(".zt-modal-reason").textContent = reason || "";
    backdrop.querySelector(".zt-modal-error").hidden = true;
    var input = backdrop.querySelector("#zt-otp-input");
    input.value = "";
    setTimeout(function () { input.focus(); }, 50);
  }

  function hideModal() {
    var backdrop = document.getElementById("zt-modal-backdrop");
    if (backdrop) backdrop.hidden = true;
  }

  function modalError(msg, errorElId) {
    if (errorElId) {
      var el = document.getElementById(errorElId);
      if (el) { el.textContent = msg || ""; }
      return;
    }
    var backdrop = ensureModal();
    var el = backdrop.querySelector(".zt-modal-error");
    el.textContent = msg;
    el.hidden = false;
  }

  function startResendCooldown(seconds) {
    var btn = document.getElementById("zt-resend-btn");
    if (!btn) return;
    var left = seconds || 0;
    var timer = setInterval(function () {
      if (left <= 0) { btn.disabled = false; btn.textContent = "Resend code"; clearInterval(timer); return; }
      btn.disabled = true;
      btn.textContent = "Resend in " + left + "s";
      left -= 1;
    }, 1000);
    if (left <= 0) { btn.disabled = false; } else { btn.disabled = true; }
  }

  async function requestChallenge(errorElId) {
    try {
      var resp = await fetch(CHALLENGE_URL, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin"
      });
      var data = await resp.json();
      if (data.ok) {
        startResendCooldown(data.cooldown || 60);
        if (!data.sent) modalError(data.message || "A code was already sent - please check your inbox.", errorElId);
      } else {
        modalError(data.error || "Could not send the verification email.", errorElId);
      }
    } catch (e) {
      modalError("Network error while requesting the code.", errorElId);
    }
  }

  async function submitOtp() {
    var input = document.getElementById("zt-otp-input");
    var code = (input && input.value || "").trim();
    if (!code) { modalError("Enter the 6-digit code from your email."); return; }
    var btn = document.getElementById("zt-verify-btn");
    if (btn) { btn.disabled = true; btn.textContent = "Verifying…"; }
    try {
      var body = new URLSearchParams({ otp: code });
      var resp = await fetch(VERIFY_URL, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
          "Content-Type": "application/x-www-form-urlencoded"
        },
        body: body.toString(),
        credentials: "same-origin"
      });
      var data = await resp.json();
      if (data.ok) {
        toast("Identity re-verified. Continuing…", "info");
        finishHardCheck(true);
        return;
      }
      if (data.session_revoked) {
        modalError(data.error || "Session revoked.");
        setTimeout(goSessionExpired, 1500);
        return;
      }
      modalError(data.error || "Invalid verification code.");
      if (input) { input.value = ""; input.focus(); }
    } catch (e) {
      modalError("Network error while verifying the code.");
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Verify"; }
    }
  }

  function finishHardCheck(ok) {
    hideModal();
    var pending = state.hardCheck;
    state.hardCheck = null;
    if (pending) pending.resolve(!!ok);
    if (ok) pollStatus();
  }

  function runHardCheck() {
    if (state.hardCheck) return state.hardCheck.promise;
    var resolveFn;
    var promise = new Promise(function (resolve) { resolveFn = resolve; });
    state.hardCheck = { promise: promise, resolve: resolveFn };
    showModal((state.reasons || []).join("; "));
    requestChallenge();
    return promise;
  }

  // ------------------------------------------------------------------
  // Interceptors: fetch + XHR
  // ------------------------------------------------------------------

  function isZtChallenge(resp) {
    return resp.status === 403 && resp.headers.get("X-Zero-Trust-Challenge") === "true";
  }

  if (window.fetch) {
    var _origFetch = window.fetch;
    window.fetch = function () {
      var self = this, args = arguments;
      return _origFetch.apply(self, args).then(function (resp) {
        if (resp.headers.get("X-ZT-Session-Locked") === "true") {
          engageLock(false);
          return resp;
        }
        if (isZtChallenge(resp)) {
          return runHardCheck().then(function (ok) {
            if (!ok) return resp;
            return _origFetch.apply(self, args).then(function (retry) {
              handleResponseSignals(retry);
              return retry;
            });
          });
        }
        handleResponseSignals(resp);
        return resp;
      });
    };
  }

  var _origXhrOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.addEventListener("load", function () {
      try {
        if (this.getResponseHeader("X-ZT-Session-Locked") === "true") {
          engageLock(false);
          return;
        }
        if (this.status === 403 && this.getResponseHeader("X-Zero-Trust-Challenge") === "true") {
          runHardCheck();
        } else if (this.getResponseHeader("X-Zero-Trust-Level")) {
          // Reuse the fetch path's toast logic via a real Headers shim.
          var signals = new Headers({
            "X-Zero-Trust-Level": this.getResponseHeader("X-Zero-Trust-Level"),
            "X-Zero-Trust-Reasons": this.getResponseHeader("X-Zero-Trust-Reasons") || ""
          });
          handleResponseSignals({ headers: signals });
        }
      } catch (e) { /* never break the caller */ }
    });
    return _origXhrOpen.apply(this, arguments);
  };

  // ------------------------------------------------------------------
  // Screen lock (bathroom-break protection)
  //
  // The opaque overlay is only the visual. The authoritative lock is the
  // server-side zt_locked flag: every API call 403s until an unlock
  // succeeds, so deleting the overlay from the DOM achieves nothing.
  // ------------------------------------------------------------------

  var lockState = {
    engaged: false,
    idleTimer: null,
    lastActivity: Date.now(),
    heartbeatTimer: null,
    clockTimer: null,
    signoutTimer: null,
    signoutDeadline: 0,
    channel: null
  };

  function ensureLockOverlay() {
    var overlay = document.getElementById("zt-lock-overlay");
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.id = "zt-lock-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Session locked");
    overlay.innerHTML =
      '<div class="zt-lock-card">' +
      '  <h1 class="zt-lock-title">Session locked</h1>' +
      '  <p class="zt-lock-who" id="zt-lock-who"></p>' +
      '  <p class="zt-lock-role" id="zt-lock-role"></p>' +
      '  <div class="zt-lock-time" id="zt-lock-clock"></div>' +
      '  <div class="zt-lock-date" id="zt-lock-date"></div>' +
      '  <div class="zt-lock-divider" aria-hidden="true"></div>' +
      '  <p class="zt-lock-note" id="zt-lock-note"></p>' +
      '  <div class="zt-lock-countdown" id="zt-lock-countdown" aria-live="polite"></div>' +
      '  <div class="zt-lock-panel" id="zt-lock-password-panel">' +
      '    <p class="zt-lock-hint">Enter your password to pick up where you left off.</p>' +
      '    <input type="password" id="zt-lock-password" autocomplete="current-password" placeholder="Password" />' +
      '    <div class="zt-lock-error" id="zt-lock-error-password"></div>' +
      '    <button type="button" id="zt-lock-unlock-btn" class="zt-lock-btn">Unlock</button>' +
      "  </div>" +
      '  <div class="zt-lock-panel" id="zt-lock-otp-panel" hidden>' +
      '    <p class="zt-lock-hint" id="zt-lock-otp-hint"></p>' +
      '    <input class="zt-lock-otp" id="zt-lock-otp" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="••••••" />' +
      '    <div class="zt-lock-error" id="zt-lock-error-otp"></div>' +
      '    <button type="button" id="zt-lock-otp-btn" class="zt-lock-btn">Unlock</button>' +
      '    <button type="button" id="zt-lock-resend-btn" class="zt-lock-linkbtn">Resend code</button>' +
      "  </div>" +
      '  <p class="zt-lock-alt">Wrong account? <a href="/logout/">Sign out</a></p>' +
      '  <p class="zt-lock-footer">CAUFA System · Zero Trust session security</p>' +
      "</div>";
    document.body.appendChild(overlay);

    overlay.querySelector("#zt-lock-unlock-btn").addEventListener("click", submitLockPassword);
    overlay.querySelector("#zt-lock-password").addEventListener("keydown", function (e) {
      if (e.key === "Enter") submitLockPassword();
    });
    overlay.querySelector("#zt-lock-otp-btn").addEventListener("click", submitLockOtp);
    overlay.querySelector("#zt-lock-otp").addEventListener("keydown", function (e) {
      if (e.key === "Enter") submitLockOtp();
    });
    overlay.querySelector("#zt-lock-resend-btn").addEventListener("click", function () {
      requestChallenge("zt-lock-error-otp");
      startLockResendCooldown(60);
    });
    return overlay;
  }

  function lockNoteText() {
    if (state.lockNote) return state.lockNote;
    var minutes = Math.max(1, Math.round(IDLE_LOCK_MS / 60000));
    return "The system locked this session automatically because it idled for " +
      minutes + " minute" + (minutes !== 1 ? "s" : "") + " after your last activity.";
  }

  function otpHintText() {
    var email = state.maskedEmail ? state.maskedEmail : "your registered ISU email";
    return "A 6-digit code is sent to your registered ISU email " + email +
      ". Enter the code to unlock this page.";
  }

  function lockError(id, msg) {
    var el = document.getElementById(id);
    if (el) el.textContent = msg || "";
  }

  function startLockResendCooldown(seconds) {
    var btn = document.getElementById("zt-lock-resend-btn");
    if (!btn) return;
    var left = seconds || 60;
    var timer = setInterval(function () {
      if (left <= 0) { btn.disabled = false; btn.textContent = "Resend code"; clearInterval(timer); return; }
      btn.disabled = true;
      btn.textContent = "Resend in " + left + "s";
      left -= 1;
    }, 1000);
  }

  function lockClockTick() {
    var el = document.getElementById("zt-lock-clock");
    if (!el) return;
    var d = new Date();
    function p(n) { return (n < 10 ? "0" : "") + n; }
    el.textContent = p(d.getHours()) + ":" + p(d.getMinutes());
    var dateEl = document.getElementById("zt-lock-date");
    if (dateEl) {
      dateEl.textContent = d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
    }
    updateSignoutCountdown();
  }

  // Auto sign-out: a locked screen that is never unlocked signs the session
  // out entirely (server enforces it too - this is only the visible UX).
  function updateSignoutCountdown() {
    var el = document.getElementById("zt-lock-countdown");
    if (!el || !lockState.signoutDeadline) return;
    var left = Math.max(0, Math.round((lockState.signoutDeadline - Date.now()) / 1000));
    var m = Math.floor(left / 60), s = left % 60;
    el.textContent = "Auto sign-out in " + m + ":" + (s < 10 ? "0" : "") + s;
  }

  function startAutoSignout() {
    stopAutoSignout();
    lockState.signoutDeadline = Date.now() + AUTO_SIGNOUT_MS;
    lockState.signoutTimer = setTimeout(function () {
      window.location.href = "/logout/";
    }, AUTO_SIGNOUT_MS);
    updateSignoutCountdown();
  }

  // Another tab (or a status poll) knows the exact server-side remaining
  // time - adopt it so every tab signs out together.
  function syncSignoutDeadline(expiresInSeconds) {
    if (!lockState.engaged) return;
    var ms = Math.max(0, (typeof expiresInSeconds === "number" ? expiresInSeconds : AUTO_SIGNOUT_MS / 1000) * 1000);
    if (lockState.signoutTimer) clearTimeout(lockState.signoutTimer);
    lockState.signoutDeadline = Date.now() + ms;
    lockState.signoutTimer = setTimeout(function () {
      window.location.href = "/logout/";
    }, ms);
    updateSignoutCountdown();
  }

  function stopAutoSignout() {
    if (lockState.signoutTimer) { clearTimeout(lockState.signoutTimer); lockState.signoutTimer = null; }
    lockState.signoutDeadline = 0;
    var el = document.getElementById("zt-lock-countdown");
    if (el) el.textContent = "";
  }

  function engageLock(callServer) {
    if (lockState.engaged) return;
    lockState.engaged = true;
    state.locked = true;
    var overlay = ensureLockOverlay();
    overlay.hidden = false;
    var whoEl = document.getElementById("zt-lock-who");
    var roleEl = document.getElementById("zt-lock-role");
    if (whoEl) whoEl.textContent = state.officerName ? "Signed in as " + state.officerName : "";
    if (roleEl) roleEl.textContent = state.officerRole || "";
    var noteEl = document.getElementById("zt-lock-note");
    if (noteEl) noteEl.textContent = lockNoteText();
    lockError("zt-lock-error-password", "");
    lockError("zt-lock-error-otp", "");
    document.getElementById("zt-lock-password-panel").hidden = false;
    document.getElementById("zt-lock-otp-panel").hidden = true;
    lockClockTick();
    lockState.clockTimer = setInterval(lockClockTick, 1000);
    startAutoSignout();
    setBadge("zt-badge-locked", "🔒", "ZT", "Locked", "Session locked - unlock to continue");

    if (callServer) {
      fetch(LOCK_URL, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin"
      }).catch(function () { /* server flag may already be set */ });
    }
    broadcastLock("lock");
    document.body.classList.add("zt-locked");
    var pw = document.getElementById("zt-lock-password");
    if (pw) setTimeout(function () { pw.focus(); }, 60);
  }

  function dismissLock(skipBroadcast) {
    if (!lockState.engaged) return;
    lockState.engaged = false;
    state.locked = false;
    stopAutoSignout();
    var overlay = document.getElementById("zt-lock-overlay");
    if (overlay) overlay.hidden = true;
    if (lockState.clockTimer) { clearInterval(lockState.clockTimer); lockState.clockTimer = null; }
    document.body.classList.remove("zt-locked");
    setBadge("zt-badge-verified", "🛡", "ZT", "Unlocked", "Session unlocked");
    if (!skipBroadcast) broadcastLock("unlock");
    pollStatus();
  }

  function switchLockToOtp(reasons) {
    document.getElementById("zt-lock-password-panel").hidden = true;
    document.getElementById("zt-lock-otp-panel").hidden = false;
    var hintEl = document.getElementById("zt-lock-otp-hint");
    if (hintEl) hintEl.textContent = otpHintText();
    requestChallenge("zt-lock-error-otp");
    startLockResendCooldown(60);
    var otp = document.getElementById("zt-lock-otp");
    setTimeout(function () { otp.focus(); }, 60);
  }

  async function submitLockPassword() {
    var pw = document.getElementById("zt-lock-password").value;
    if (!pw) { lockError("zt-lock-error-password", "Enter your password to unlock."); return; }
    await submitLockUnlock({ password: pw }, "zt-lock-error-password", false);
  }

  async function submitLockOtp() {
    var code = document.getElementById("zt-lock-otp").value.trim();
    if (!code) { lockError("zt-lock-error-otp", "Enter the 6-digit code from your email."); return; }
    await submitLockUnlock({ otp: code }, "zt-lock-error-otp", true);
  }

  async function submitLockUnlock(fields, errorId, fromOtpPanel) {
    lockError(errorId, "");
    var btnId = fromOtpPanel ? "zt-lock-otp-btn" : "zt-lock-unlock-btn";
    var btn = document.getElementById(btnId);
    btn.disabled = true;
    var oldLabel = btn.textContent;
    btn.textContent = "Checking…";
    try {
      var body = new URLSearchParams();
      for (var k in fields) body.append(k, fields[k]);
      var resp = await fetch(UNLOCK_URL, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
          "Content-Type": "application/x-www-form-urlencoded"
        },
        body: body.toString(),
        credentials: "same-origin"
      });
      var data = await resp.json();
      if (data.ok) {
        document.getElementById("zt-lock-password").value = "";
        document.getElementById("zt-lock-otp").value = "";
        dismissLock(false);
        toast("Session unlocked.", "info");
        return;
      }
      if (data.session_revoked) {
        lockError(errorId, data.error || "Session revoked.");
        setTimeout(goSessionExpired, 1500);
        return;
      }
      if (data.otp_required && !fromOtpPanel) {
        switchLockToOtp(data.reasons || []);
        return;
      }
      lockError(errorId, data.error || "Unlock failed.");
    } catch (e) {
      lockError(errorId, "Network error while unlocking.");
    } finally {
      btn.disabled = false;
      btn.textContent = oldLabel;
    }
  }

  // Heartbeat: proves the lock UI is alive. Silence (while requests keep
  // flowing) is the server's trigger to auto-lock.
  function startHeartbeat() {
    if (lockState.heartbeatTimer) return;
    lockState.heartbeatTimer = setInterval(async function () {
      if (lockState.engaged) return;
      try {
        var resp = await fetch(HEARTBEAT_URL, {
          method: "POST",
          headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin"
        });
        if (resp.status === 403) engageLock(false);
      } catch (e) { /* transient network trouble - the server backstop copes */ }
    }, HEARTBEAT_MS);
  }

  // Idle detection: any real input resets the timer; 2 quiet minutes locks.
  function resetIdleTimer() {
    lockState.lastActivity = Date.now();
    if (lockState.engaged) return;
    if (lockState.idleTimer) clearTimeout(lockState.idleTimer);
    lockState.idleTimer = setTimeout(function () {
      engageLock(true);
    }, IDLE_LOCK_MS);
  }

  ["mousemove", "mousedown", "keydown", "touchstart", "scroll", "wheel"].forEach(function (evt) {
    document.addEventListener(evt, resetIdleTimer, { passive: true });
  });
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && !lockState.engaged) {
      // Returning to a tab that idled in the background: lock immediately
      // if the quiet period already elapsed.
      if (Date.now() - lockState.lastActivity >= IDLE_LOCK_MS) engageLock(true);
      else resetIdleTimer();
    }
  });

  // Keep every open dashboard tab in sync - locking one locks them all.
  try {
    if ("BroadcastChannel" in window) {
      lockState.channel = new BroadcastChannel("caufa-zt-lock");
      lockState.channel.onmessage = function (ev) {
        if (!ev || !ev.data) return;
        if (ev.data.type === "lock") engageLock(false);
        else if (ev.data.type === "unlock") dismissLock(true);
      };
    }
  } catch (e) { /* channel is best-effort */ }

  function broadcastLock(type) {
    try {
      if (lockState.channel) lockState.channel.postMessage({ type: type });
    } catch (e) { /* best-effort */ }
  }

  // ------------------------------------------------------------------
  // Public API (backward compatible with existing call sites)
  // ------------------------------------------------------------------

  window.ensureZeroTrust = async function (action) {
    if (lockState.engaged) return false;  // locked: nothing proceeds until unlocked
    await pollStatus();
    if (state.level === "hard") {
      var ok = await runHardCheck();
      if (!ok) return false;
      await pollStatus();
      return state.level !== "hard";
    }
    return true;
  };

  window.ztRefreshBadge = pollStatus;
  window.ztLockNow = function () { engageLock(true); };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      resetIdleTimer();
      startHeartbeat();
      startPolling();
    });
  } else {
    resetIdleTimer();
    startHeartbeat();
    startPolling();
  }
})();
