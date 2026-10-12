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

  // Singleton: dashboards re-execute this file on every Turbo navigation.
  // A second instance would arm duplicate idle timers and alarm elements,
  // so only the first loaded instance runs (document-level listeners and
  // timers survive Turbo body swaps).
  if (window.__caufaZeroTrustLoaded) return;
  window.__caufaZeroTrustLoaded = true;

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
  var WARN_BEFORE_LOCK_MS = 15000;  // independent warning overlay countdown before the lock overlay
  // Audio URL is injected per-page via {% static %} so it respects
  // STATIC_URL / subpaths / collectstatic. Hardcoded /static/ is only the
  // fallback when the template forgot the inline snippet.
  var WARN_AUDIO_FALLBACK_URL = "/static/audio/friendlyAlarm/loopAlarm.mp3";
  function getWarnAudioUrl() {
    try {
      if (typeof window.CAUFA_WARN_AUDIO_URL === "string" && window.CAUFA_WARN_AUDIO_URL) {
        return window.CAUFA_WARN_AUDIO_URL;
      }
    } catch (e) { /* best-effort */ }
    return WARN_AUDIO_FALLBACK_URL;
  }

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

  // Flash-on-change visibility: the badge only appears when its meaning
  // changes, stays for 3s, then hides. Actionable states (hard-check,
  // locked) stay visible so the officer can always tap through.
  var lastBadgeSig = null;
  var badgeHideTimer = null;
  function setBadge(cls, icon, label, detail, title) {
    var badge = document.getElementById("zt-badge");
    var container = document.getElementById("zt-badge-container");
    if (!badge) return;
    badge.className = "zt-badge " + cls;
    badge.innerHTML = '<span class="zt-icon">' + icon + '</span><span class="zt-label">' + label + "</span>" +
      (detail ? '<span class="zt-detail"></span>' : "");
    if (detail) badge.querySelector(".zt-detail").textContent = detail;
    badge.title = title || "Zero Trust status";
    badge.onclick = cls === "zt-badge-hard" ? function () { runHardCheck(); } : null;
    if (!container) return;
    // Signature excludes the ticking "Xm / Xh Ym" age so the minute counter
    // alone never counts as a change.
    var sig = cls + "|" + icon + "|" + label + "|" +
      String(title || "").replace(/ · \d+m$| · \d+h \d+m$/, "");
    var sticky = (cls === "zt-badge-hard" || cls === "zt-badge-locked");
    if (sticky) {
      if (badgeHideTimer) { clearTimeout(badgeHideTimer); badgeHideTimer = null; }
      lastBadgeSig = sig;
      if (container.hidden) container.hidden = false;
      return;
    }
    if (sig === lastBadgeSig) {
      if (!container.hidden) container.hidden = true;
      return;
    }
    lastBadgeSig = sig;
    container.hidden = false; // reveal on change...
    if (badgeHideTimer) clearTimeout(badgeHideTimer);
    badgeHideTimer = setTimeout(function () {
      var c = document.getElementById("zt-badge-container");
      if (c) c.hidden = true; // ...and hide again after 3s
    }, 3000);
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
      // Superadmin-editable: adopt a CHANGED setting without re-arming the
      // countdown on every poll. Re-arming here pushed the idle lock out
      // forever while the dashboard kept polling (30s poll vs 2-min lock),
      // so an open dashboard could never lock. Input events still re-arm.
      var idleMs = data.lock_idle_seconds * 1000;
      if (idleMs !== IDLE_LOCK_MS) {
        IDLE_LOCK_MS = idleMs;
        resetIdleTimer();
      }
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
    channel: null,
    warnTimer: null,
    warnDeadline: 0,
    warnAudio: null
  };

  // ------------------------------------------------------------------
  // Pre-lock warning: independent lockout-style overlay with a 15s
  // countdown and a looping alarm. NOT part of the toast/banner system —
  // it owns its overlay (#zt-lock-warn-overlay) the way the lock screen
  // owns #zt-lock-overlay. Any activity cancels it (via resetIdleTimer);
  // expiry engages the lock and the alarm stops the moment it shows.
  // ------------------------------------------------------------------

  function ensureWarnOverlay() {
    // Styles live in zt_badge.css (guaranteed paint); visibility is forced
    // inline here so no page stylesheet can keep the overlay hidden.
    var overlay = document.getElementById("zt-lock-warn-overlay");
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.id = "zt-lock-warn-overlay";
    overlay.hidden = true;
    overlay.setAttribute("role", "alertdialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Session locking soon");
    overlay.innerHTML =
      '<div class="zt-warn-card">' +
      '  <div class="zt-warn-kicker">Zero Trust · idle session</div>' +
      '  <div class="zt-warn-title">Still there?</div>' +
      '  <div class="zt-warn-count" id="zt-lock-warn-count">15</div>' +
      '  <div class="zt-warn-bar"><div id="zt-lock-warn-fill"></div></div>' +
      '  <p class="zt-warn-sub">Your screen locks when the timer ends. Move the mouse, press any key, or stay signed in.</p>' +
      '  <button type="button" class="zt-warn-btn" id="zt-lock-warn-stay">Stay signed in</button>' +
      "</div>";
    document.body.appendChild(overlay);
    overlay.querySelector("#zt-lock-warn-stay").addEventListener("click", function () {
      resetIdleTimer();  // cancels the warning and re-arms the idle timer
    });
    return overlay;
  }

  function showWarnOverlay() {
    var overlay = ensureWarnOverlay();
    try {
      // Re-parent to the end of <body> so no DOM shuffling can bury it,
      // then force visibility inline (beats any page stylesheet).
      document.body.appendChild(overlay);
      overlay.removeAttribute("hidden");
      overlay.hidden = false;
      overlay.style.display = "flex";
      overlay.style.visibility = "visible";
      overlay.style.opacity = "1";
      var stay = document.getElementById("zt-lock-warn-stay");
      if (stay) setTimeout(function () { try { stay.focus(); } catch (e) {} }, 60);
    } catch (e) { overlay.hidden = false; }
    return overlay;
  }

  function hideWarnOverlay() {
    var overlay = document.getElementById("zt-lock-warn-overlay");
    if (!overlay) return;
    try {
      overlay.setAttribute("hidden", "");
      overlay.hidden = true;
      overlay.style.display = "none";
    } catch (e) { overlay.hidden = true; }
  }

  // The alarm fires from an idle timer — long after the last user gesture —
  // so browsers with a strict autoplay policy reject play() with
  // NotAllowedError, and that rejection used to be swallowed silently (no
  // alarm, no error). Fix: (1) preload the element at startup, (2) prime it
  // on the first real user gesture (a muted play+pause grants later
  // playback rights), (3) fall back to WebAudio beeps when the mp3 still
  // cannot play.
  function ensureWarnAudio() {
    var audio = lockState.warnAudio;
    if (!audio) {
      audio = new Audio();
      audio.loop = true;
      audio.preload = "auto";
      audio.volume = 1.0;
      try { audio.setAttribute("data-zt-warn", "1"); } catch (e) {}
      lockState.warnAudio = audio;
    }
    try {
      // Keep src cached across warnings (stop only pauses) so repeat
      // warnings never re-download; re-point only when missing or stale
      // (e.g. template injected a different STATIC_URL build).
      var want = getWarnAudioUrl();
      var cur = "";
      try { cur = audio.getAttribute("src") || audio.src || ""; } catch (e) { cur = ""; }
      if (!cur || cur.indexOf("loopAlarm.mp3") === -1) {
        audio.src = want;
        try { audio.load(); } catch (e) { /* older engines */ }
      }
    } catch (e) { /* best-effort */ }
    return audio;
  }

  var warnAudioPrimed = false;
  function primeWarnAudio() {
    // Must run inside a real user gesture; a muted play+pause unlocks later
    // unmuted playback from timers.
    if (warnAudioPrimed) return;
    warnAudioPrimed = true;
    var audio = null;
    try { audio = ensureWarnAudio(); } catch (e) { return; }
    try {
      var prevMuted = audio.muted;
      audio.muted = true;
      var p = null;
      try { p = audio.play(); } catch (e) { audio.muted = prevMuted; return; }
      if (p && typeof p.then === "function") {
        p.then(function () {
          try { audio.pause(); } catch (e) {}
          try { audio.currentTime = 0; } catch (e) {}
          audio.muted = prevMuted;
        }, function () { audio.muted = prevMuted; });
      } else {
        try { audio.pause(); } catch (e) {}
        audio.muted = prevMuted;
      }
    } catch (e) { /* best-effort */ }
  }
  ["pointerdown", "keydown", "touchstart", "mousedown"].forEach(function (evt) {
    document.addEventListener(evt, primeWarnAudio, { passive: true });
  });

  var fallbackBeepTimer = null;
  var fallbackAudioCtx = null;
  function stopFallbackBeeps() {
    if (fallbackBeepTimer) { clearInterval(fallbackBeepTimer); fallbackBeepTimer = null; }
    try {
      if (fallbackAudioCtx && typeof fallbackAudioCtx.close === "function") fallbackAudioCtx.close();
    } catch (e) { /* best-effort */ }
    fallbackAudioCtx = null;
  }
  function startFallbackBeeps() {
    // Last resort when the mp3 element cannot play (strict autoplay block
    // or a missing/corrupt file): synthesize the alarm with WebAudio.
    stopFallbackBeeps();
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      var ctx = new AC();
      fallbackAudioCtx = ctx;
      try { if (typeof ctx.resume === "function") ctx.resume(); } catch (e) { /* best-effort */ }
      var beep = function () {
        try {
          var osc = ctx.createOscillator();
          var gain = ctx.createGain();
          osc.type = "sine";
          osc.frequency.value = 880;
          gain.gain.setValueAtTime(0.0001, ctx.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.4, ctx.currentTime + 0.02);
          gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.45);
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start();
          osc.stop(ctx.currentTime + 0.5);
        } catch (e) { /* one missed beep is fine */ }
      };
      beep();
      fallbackBeepTimer = setInterval(beep, 900);
    } catch (e) { /* best-effort */ }
  }

  var warnAudioGen = 0;  // guards late-resolving play() after a stop
  function startWarnAudio() {
    // Pause anything lingering first (same element is reused with src cached).
    stopWarnAudio();
    warnAudioGen += 1;
    var myGen = warnAudioGen;
    try {
      var audio = ensureWarnAudio();
      try { audio.muted = false; audio.volume = 1.0; } catch (e) { /* best-effort */ }
      try { audio.currentTime = 0; } catch (e) { /* best-effort */ }
      // A missing/corrupt file fires 'error' with no play() rejection —
      // catch that too, once per warning.
      try {
        audio.onerror = function () {
          try { if (window.console && console.warn) console.warn("[ZT] lock-warning audio file failed; using fallback beeps."); } catch (e) {}
          startFallbackBeeps();
        };
      } catch (e) { /* best-effort */ }
      var p = audio.play();
      if (p && typeof p.then === "function") {
        p.then(function () {
          // A stop() that landed while play() was pending means this start
          // is stale — silence it so no orphan loop survives.
          try { if (myGen !== warnAudioGen) audio.pause(); } catch (e) {}
        });
      }
      if (p && typeof p.catch === "function") {
        p.catch(function (err) {
          try {
            var name = (err && err.name) || "error";
            if (window.console && console.warn) console.warn("[ZT] lock-warning alarm blocked (" + name + "); using fallback beeps.");
          } catch (e) { /* best-effort */ }
          startFallbackBeeps();
        });
      }
    } catch (e) {
      startFallbackBeeps();
    }
  }

  function stopWarnAudio() {
    // Pause + rewind only — keep src cached so the NEXT warning replays
    // instantly. (The old removeAttribute("src")+load() forced a re-download
    // every cycle and raced with pending play() promises, which is how the
    // alarm silently went missing "again".)
    warnAudioGen += 1;
    stopFallbackBeeps();
    try {
      var audio = lockState.warnAudio;
      if (audio) {
        try { audio.onerror = null; } catch (e) { /* best-effort */ }
        try { audio.pause(); } catch (e) { /* best-effort */ }
        try { audio.currentTime = 0; } catch (e) { /* best-effort */ }
      }
    } catch (e) { /* best-effort */ }
    try {
      var stray = document.querySelectorAll("audio[data-zt-warn]");
      for (var i = 0; i < stray.length; i++) {
        try { stray[i].pause(); } catch (e) {}
      }
    } catch (e) { /* best-effort */ }
  }

  // On-demand sound check, wired to the "Test sound" button on the warning
  // overlay. A click IS a user gesture, so playback here is always allowed
  // by autoplay policy — if this stays silent, the problem is the file, the
  // URL, or the device (not permissions).
  function testWarnAudio() {
    var msgEl = document.getElementById("zt-lock-warn-testmsg");
    var say = function (t) {
      if (msgEl) msgEl.textContent = t;
      try { if (window.console && console.log) console.log("[ZT] alarm test: " + t); } catch (e) {}
    };
    say("Playing test sound…");
    var a = null;
    try {
      a = new Audio(getWarnAudioUrl());
      try { a.setAttribute("data-zt-warn", "1"); } catch (e) { /* best-effort */ }
    } catch (e) {
      say("Could not create audio. (" + e + ")");
      return;
    }
    var done = false;
    var okTimer = setTimeout(function () {
      if (done) return;
      done = true;
      try { a.pause(); } catch (e) { /* best-effort */ }
      say("Test finished. Heard nothing? Check speakers/volume and the file URL below.");
      ztAlarmDiag();
    }, 3000);
    try {
      a.onerror = function () {
        if (done) return;
        done = true;
        clearTimeout(okTimer);
        say("Audio FILE failed to load (" + (a.currentSrc || getWarnAudioUrl()) + "). Check that the URL returns the mp3.");
        ztAlarmDiag();
      };
      var p = a.play();
      if (p && typeof p.then === "function") {
        p.then(function () {
          if (done) return;
          say("Playing… (test stops in 3s)");
        }, function (err) {
          if (done) return;
          done = true;
          clearTimeout(okTimer);
          say("Playback rejected (" + ((err && err.name) || "error") + ") even from a click — check browser sound permissions for this site.");
          ztAlarmDiag();
        });
      }
    } catch (e) {
      if (!done) { done = true; clearTimeout(okTimer); say("Playback threw (" + e + ")."); }
    }
  }

  // Diagnostics for "no sound" reports: run ztAlarmDiag() in the console
  // while the warning shows (or after) and send the table.
  function ztAlarmDiag() {
    var audio = null;
    try { audio = ensureWarnAudio(); } catch (e) { /* best-effort */ }
    var ua = "n/a";
    try {
      if (navigator.userActivation) {
        ua = "isActive=" + navigator.userActivation.isActive +
          " hasBeenActive=" + navigator.userActivation.hasBeenActive;
      }
    } catch (e) { /* best-effort */ }
    var info = {
      primedOnGesture: warnAudioPrimed,
      hasElement: !!audio,
      src: audio ? (audio.currentSrc || audio.src || "") : "",
      muted: audio ? !!audio.muted : null,
      volume: audio ? audio.volume : null,
      loop: audio ? !!audio.loop : null,
      paused: audio ? !!audio.paused : null,
      readyState: audio ? audio.readyState : null,
      networkState: audio ? audio.networkState : null,
      docHidden: document.hidden,
      userActivation: ua,
      warnActive: !!lockState.warnTimer,
      fallbackBeeps: !!fallbackBeepTimer
    };
    try {
      if (window.console) {
        if (console.table) console.table(info);
        else console.log(info);
      }
    } catch (e) { /* best-effort */ }
    return info;
  }

  function warnTick() {
    var left = Math.max(0, lockState.warnDeadline - Date.now());
    var secs = Math.ceil(left / 1000);
    var count = document.getElementById("zt-lock-warn-count");
    if (count) count.textContent = String(secs);
    var fill = document.getElementById("zt-lock-warn-fill");
    if (fill) fill.style.width = (WARN_BEFORE_LOCK_MS > 0 ? (left / WARN_BEFORE_LOCK_MS) * 100 : 0) + "%";
    if (left <= 0) {
      cancelLockWarning();
      engageLock(true);
    }
  }

  function startLockWarning() {
    if (lockState.engaged || lockState.warnTimer) return;
    showWarnOverlay();
    lockState.warnDeadline = Date.now() + WARN_BEFORE_LOCK_MS;
    warnTick();
    lockState.warnTimer = setInterval(warnTick, 250);
    startWarnAudio();
  }

  function cancelLockWarning() {
    if (lockState.warnTimer) { clearInterval(lockState.warnTimer); lockState.warnTimer = null; }
    lockState.warnDeadline = 0;
    stopWarnAudio();
    hideWarnOverlay();
  }

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
    cancelLockWarning();  // alarm off the moment the lock screen shows
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

  // Idle detection: any real input resets the timer; quiet first raises
  // the 15s warning (any further input cancels it), then the lock engages.
  function resetIdleTimer() {
    lockState.lastActivity = Date.now();
    if (lockState.engaged) return;
    if (lockState.warnTimer) cancelLockWarning();
    if (lockState.idleTimer) clearTimeout(lockState.idleTimer);
    lockState.idleTimer = setTimeout(function () {
      startLockWarning();
    }, IDLE_LOCK_MS);
  }

  ["mousemove", "mousedown", "keydown", "touchstart", "scroll", "wheel"].forEach(function (evt) {
    document.addEventListener(evt, resetIdleTimer, { passive: true });
  });
  // Capture-phase twin: even if page scripts stop propagation, any input
  // during the warning still kills the countdown AND the alarm.
  ["pointerdown", "keydown"].forEach(function (evt) {
    document.addEventListener(evt, function () {
      if (lockState.warnTimer) cancelLockWarning();
    }, { capture: true, passive: true });
  });
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { stopWarnAudio(); return; }  // never alarm a background tab
    if (lockState.engaged) return;
    if (lockState.warnTimer) { startWarnAudio(); return; }  // warning survived: resume the alarm
    if (Date.now() - lockState.lastActivity >= IDLE_LOCK_MS) {
      // Back from a long absence: ask the server first (it may have locked
      // already), otherwise raise the 15s warning — never lock instantly.
      try {
        pollStatus().then(function () {
          if (!lockState.engaged && Date.now() - lockState.lastActivity >= IDLE_LOCK_MS) startLockWarning();
        }).catch(function () { /* poll failed: timers cope */ });
      } catch (e) { /* best-effort */ }
    }
    else resetIdleTimer();
  });
  try {
    window.addEventListener("pagehide", function () { stopWarnAudio(); });
  } catch (e) { /* best-effort */ }

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
  window.ztTestWarning = function () { startLockWarning(); };  // on-demand 15s warning (no idling needed)
  window.ztTestAlarm = testWarnAudio;  // on-demand alarm sound check (best from a click)
  window.ztAlarmDiag = ztAlarmDiag;  // console diagnostics for "no sound" reports
  window.ztCancelWarning = function () { cancelLockWarning(); resetIdleTimer(); };

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
