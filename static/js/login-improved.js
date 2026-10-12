/**
 * CAUFA Login Page - Improved JavaScript
 * Handles password toggle, form validation, and interactions
 */

(function () {
  // ===== Cloudflare Turnstile gating =====
  // The Login button stays disabled until the Turnstile check succeeds, so the
  // security check can never be silently skipped. The widget is rendered
  // EXPLICITLY once api.js arrives (no onload race), with auto-retry for
  // transient failures plus a manual "Try again" button so a failed widget
  // never dead-ends the login form.
  var turnstileWidget = document.querySelector(".cf-turnstile");
  var turnstileStatus = document.getElementById("turnstileStatus");
  var turnstileRetryBtn = document.getElementById("turnstileRetryBtn");
  var loginSubmitBtn = document.getElementById("loginSubmitBtn");
  var turnstileEnabled = !!turnstileWidget;
  var turnstileWidgetId = null;
  var turnstileApiWaited = 0;
  var turnstileApiTimer = null;

  function setTurnstileState(state, message) {
    if (turnstileStatus) {
      turnstileStatus.textContent = message || "";
      turnstileStatus.style.display = message ? "block" : "none";
      if (state === "ok") turnstileStatus.style.color = "#1b5e20";
      else if (state === "error") turnstileStatus.style.color = "#c62828";
      else turnstileStatus.style.color = "#f57c00";
    }
    if (loginSubmitBtn) loginSubmitBtn.disabled = state !== "ok";
  }

  function showTurnstileRetry() {
    if (turnstileRetryBtn) turnstileRetryBtn.style.display = "";
  }

  function hideTurnstileRetry() {
    if (turnstileRetryBtn) turnstileRetryBtn.style.display = "none";
  }

  function turnstileToken() {
    var input = document.querySelector('[name="cf-turnstile-response"]');
    return input && input.value ? input.value : "";
  }

  function onTurnstileApiMissing() {
    // api.js itself never arrived (offline, blocked by an extension, or a
    // filtered network) — distinct from a widget error, so say so.
    setTurnstileState("error", "Security check couldn't load — this device can't reach Cloudflare. Check your connection or ad-blocker, then try again.");
    showTurnstileRetry();
    showOfflineOption();
  }

  function onTurnstileError(code) {
    try { console.warn("Turnstile widget error:", code); } catch (e) {}
    // 300xxx/600xxx = the widget crashed inside this browser (NOT a bad site
    // key or domain — those report as 110xxx). Usual culprits: ad-blocker /
    // privacy extension, VPN/proxy, or a browser that blocks the challenge
    // scripts. Give that checklist instead of a dead-end message.
    var codeText = code ? String(code) : "";
    var isCrash = codeText.charAt(0) === "3" || codeText.charAt(0) === "6";
    var message = isCrash
      ? "Security check crashed in this browser (code " + codeText + "). Turn off any ad-blocker or VPN for this site, or try Chrome/Edge, then press Try again."
      : "Security check failed to load" + (codeText ? " (code " + codeText + ")" : "") + ". You can try again — no need to refresh.";
    setTurnstileState("error", message);
    showTurnstileRetry();
    showOfflineOption();
  }

  function renderTurnstileWidget() {
    if (turnstileWidgetId !== null) return true;
    if (!turnstileWidget || !window.turnstile || typeof window.turnstile.render !== "function") return false;
    try {
      turnstileWidgetId = window.turnstile.render(turnstileWidget, {
        sitekey: turnstileWidget.getAttribute("data-sitekey"),
        theme: "auto",
        size: "normal",
        appearance: "always",
        retry: "auto",
        "retry-interval": 8000,
        callback: function () {
          setTurnstileState("ok", "✓ Security check passed. You can log in now.");
          hideTurnstileRetry();
        },
        "expired-callback": function () {
          setTurnstileState("pending", "Security check expired — please verify again.");
        },
        "error-callback": function (code) {
          onTurnstileError(code);
        }
      });
      return true;
    } catch (e) {
      return false;
    }
  }

  function watchTurnstileApi() {
    turnstileApiWaited = 0;
    if (turnstileApiTimer) clearInterval(turnstileApiTimer);
    turnstileApiTimer = setInterval(function () {
      if (renderTurnstileWidget()) {
        clearInterval(turnstileApiTimer);
        turnstileApiTimer = null;
        hideTurnstileRetry();
        return;
      }
      turnstileApiWaited += 500;
      if (turnstileApiWaited >= 15000) {
        clearInterval(turnstileApiTimer);
        turnstileApiTimer = null;
        onTurnstileApiMissing();
      }
    }, 500);
  }

  function retryTurnstile() {
    hideTurnstileRetry();
    setTurnstileState("pending", "Retrying the security check…");
    if (window.turnstile && turnstileWidgetId !== null) {
      try {
        window.turnstile.reset(turnstileWidgetId);
        return;
      } catch (e) {
        turnstileWidgetId = null;
      }
    }
    if (renderTurnstileWidget()) return;
    // api.js itself is missing — inject it again, then watch for arrival.
    if (!document.querySelector('script[data-turnstile-api="1"]')) {
      var s = document.createElement("script");
      s.setAttribute("data-turnstile-api", "1");
      s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      s.async = true;
      s.defer = true;
      s.onerror = function () {
        onTurnstileApiMissing();
      };
      document.head.appendChild(s);
    }
    watchTurnstileApi();
  }

  if (turnstileEnabled) {
    setTurnstileState("pending", "Please complete the security check to enable login.");
    watchTurnstileApi();
    if (turnstileRetryBtn) {
      turnstileRetryBtn.addEventListener("click", retryTurnstile);
    }
  }

  // Legacy global callbacks (kept harmless in case any cached markup still
  // references them by name; the widget is now rendered explicitly above).
  window.caufaTurnstileSuccess = function () {
    setTurnstileState("ok", "✓ Security check passed. You can log in now.");
    hideTurnstileRetry();
  };
  window.caufaTurnstileExpired = function () {
    setTurnstileState("pending", "Security check expired — please verify again.");
  };
  window.caufaTurnstileError = function (code) {
    onTurnstileError(code);
  };

  // ===== Offline bot check: 2nd option when Cloudflare is unreachable =====
  // Proof-of-work — find nonce so SHA-256("<salt>:<nonce>") has `difficulty`
  // leading zero bits (server re-hashes once, challenge burns on use).
  // Pure-JS hash on purpose: no WebCrypto needed, works on plain-http LAN
  // too. Solved in slices so the page stays responsive with live progress.
  var offlineCheckBtn = document.getElementById("offlineCheckBtn");
  var offlineInfoWrap = document.getElementById("offlineInfoWrap");
  var offlineCheckBox = document.getElementById("offlineCheckBox");
  var offlineCheckStatus = document.getElementById("offlineCheckStatus");
  var offlineCheckFill = document.getElementById("offlineCheckFill");
  var offlineProofInput = document.getElementById("offlineBotProof");
  var offlineSolving = false;
  var offlineSolvedFor = "";

  function offlineProofValid() {
    return !!(offlineProofInput && offlineProofInput.value);
  }

  function showOfflineOption() {
    if (offlineCheckBtn && !offlineProofValid()) offlineCheckBtn.style.display = "";
    if (offlineInfoWrap && !offlineProofValid()) offlineInfoWrap.style.display = "";
  }

  function hideOfflineOption() {
    if (offlineCheckBtn) offlineCheckBtn.style.display = "none";
    if (offlineInfoWrap) offlineInfoWrap.style.display = "none";
    hideOfflineInfoCard();
  }

  // ===== Offline info card: dynamic placement (fits viewport) =====
  // Picks below / above / right / left — whichever fits the card fully —
  // and clamps + points the arrow at the "i" dot. Fixed positioning keeps
  // it out of any clipped ancestor.
  var offlineInfoCard = document.getElementById("offlineInfoCard");
  var offlineInfoDot = document.querySelector("#offlineInfoWrap .offline-info-dot");

  function offlineInfoVisible() {
    return !!(offlineInfoCard && offlineInfoCard.classList.contains("offline-show"));
  }

  function hideOfflineInfoCard() {
    if (offlineInfoCard) offlineInfoCard.classList.remove("offline-show");
  }

  function positionOfflineInfoCard() {
    if (!offlineInfoWrap || !offlineInfoCard || !offlineInfoDot) return;
    if (offlineInfoWrap.style.display === "none") return;
    var MARGIN = 8, GAP = 9;
    var vw = window.innerWidth, vh = window.innerHeight;
    var dotR = offlineInfoDot.getBoundingClientRect();
    if (!dotR || (dotR.width === 0 && dotR.height === 0)) return;
    // Show (hidden) to measure natural size, constrained to viewport width.
    offlineInfoCard.classList.add("offline-show");
    offlineInfoCard.style.visibility = "hidden";
    offlineInfoCard.style.left = "0px";
    offlineInfoCard.style.top = "0px";
    offlineInfoCard.style.maxHeight = "";
    offlineInfoCard.style.overflowY = "";
    offlineInfoCard.style.width = Math.min(264, vw - MARGIN * 2) + "px";
    var cw = offlineInfoCard.offsetWidth || Math.min(264, vw - MARGIN * 2);
    var ch = offlineInfoCard.offsetHeight || 120;
    var spaceBelow = vh - dotR.bottom - GAP - MARGIN;
    var spaceAbove = dotR.top - GAP - MARGIN;
    var spaceRight = vw - dotR.right - GAP - MARGIN;
    var spaceLeft = dotR.left - GAP - MARGIN;
    var fitsBelow = spaceBelow >= ch;
    var fitsAbove = spaceAbove >= ch;
    var fitsRight = spaceRight >= cw && vh >= ch + MARGIN * 2;
    var fitsLeft = spaceLeft >= cw && vh >= ch + MARGIN * 2;
    var place;
    if (fitsBelow) place = "bottom";
    else if (fitsAbove) place = "top";
    else if (fitsRight) place = "right";
    else if (fitsLeft) place = "left";
    else if (spaceBelow >= spaceAbove && spaceBelow >= spaceRight && spaceBelow >= spaceLeft) place = "bottom";
    else if (spaceAbove >= spaceRight && spaceAbove >= spaceLeft) place = "top";
    else if (spaceRight >= spaceLeft) place = "right";
    else place = "left";
    var left = MARGIN, top = MARGIN;
    offlineInfoCard.classList.remove("place-bottom", "place-top", "place-left", "place-right");
    if (place === "bottom" || place === "top") {
      var maxH = place === "bottom" ? (vh - dotR.bottom - GAP - MARGIN) : (dotR.top - GAP - MARGIN);
      if (ch > maxH && maxH > 60) {
        offlineInfoCard.style.maxHeight = Math.floor(maxH) + "px";
        offlineInfoCard.style.overflowY = "auto";
        ch = offlineInfoCard.offsetHeight || ch;
      }
      top = place === "bottom" ? (dotR.bottom + GAP) : (dotR.top - GAP - ch);
      top = Math.max(MARGIN, Math.min(top, vh - ch - MARGIN));
      left = dotR.left + dotR.width / 2 - cw / 2;
      left = Math.max(MARGIN, Math.min(left, vw - cw - MARGIN));
      var dotCX = dotR.left + dotR.width / 2;
      var arrowX = Math.max(14, Math.min(cw - 14, dotCX - left));
      offlineInfoCard.style.setProperty("--arrow-left", arrowX + "px");
      offlineInfoCard.style.removeProperty("--arrow-top");
    } else {
      var maxSideH = vh - MARGIN * 2;
      if (ch > maxSideH && maxSideH > 60) {
        offlineInfoCard.style.maxHeight = Math.floor(maxSideH) + "px";
        offlineInfoCard.style.overflowY = "auto";
        ch = offlineInfoCard.offsetHeight || ch;
      }
      left = place === "right" ? (dotR.right + GAP) : (dotR.left - GAP - cw);
      left = Math.max(MARGIN, Math.min(left, vw - cw - MARGIN));
      top = dotR.top + dotR.height / 2 - ch / 2;
      top = Math.max(MARGIN, Math.min(top, vh - ch - MARGIN));
      var dotCY = dotR.top + dotR.height / 2;
      var arrowY = Math.max(14, Math.min(ch - 14, dotCY - top));
      offlineInfoCard.style.setProperty("--arrow-top", arrowY + "px");
      offlineInfoCard.style.removeProperty("--arrow-left");
    }
    offlineInfoCard.style.left = Math.round(left) + "px";
    offlineInfoCard.style.top = Math.round(top) + "px";
    offlineInfoCard.classList.add(place === "bottom" ? "place-bottom" : place === "top" ? "place-top" : place === "right" ? "place-right" : "place-left");
    offlineInfoCard.dataset.placement = place;
    offlineInfoCard.style.visibility = "";
  }

  function showOfflineInfoCard() {
    if (!offlineInfoCard) return;
    positionOfflineInfoCard();
  }

  if (offlineInfoWrap && offlineInfoDot && offlineInfoCard) {
    offlineInfoWrap.addEventListener("mouseenter", showOfflineInfoCard);
    offlineInfoWrap.addEventListener("mouseleave", hideOfflineInfoCard);
    offlineInfoDot.addEventListener("focus", showOfflineInfoCard);
    offlineInfoWrap.addEventListener("focusout", function (e) {
      if (!offlineInfoWrap.contains(e.relatedTarget)) hideOfflineInfoCard();
    });
    // Touch / pen: tap toggles; outside tap or Esc dismisses.
    // On hover-capable mice the card already shows on hover, so a click
    // there just re-pins the position instead of hiding it from under
    // the cursor.
    offlineInfoDot.addEventListener("click", function (e) {
      e.stopPropagation();
      var canHover = window.matchMedia && window.matchMedia("(hover: hover)").matches;
      if (canHover) { showOfflineInfoCard(); return; }
      if (offlineInfoVisible()) hideOfflineInfoCard();
      else showOfflineInfoCard();
    });
    document.addEventListener("click", function (e) {
      if (offlineInfoVisible() && !offlineInfoWrap.contains(e.target)) hideOfflineInfoCard();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") hideOfflineInfoCard();
    });
    window.addEventListener("resize", function () { if (offlineInfoVisible()) positionOfflineInfoCard(); });
    window.addEventListener("scroll", function () { if (offlineInfoVisible()) positionOfflineInfoCard(); }, true);
  }

  function offlineSetProgress(pct, text) {
    if (offlineCheckStatus) offlineCheckStatus.textContent = text || "";
    if (offlineCheckFill) offlineCheckFill.style.width = Math.max(0, Math.min(100, pct || 0)) + "%";
  }

  // Compact SHA-256 over ASCII (our preimage is hex salt + ":" + digits).
  function sha256Bytes(ascii) {
    var K = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
      0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
      0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
    ];
    var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var bytes = [];
    for (var i = 0; i < ascii.length; i++) bytes.push(ascii.charCodeAt(i) & 0xff);
    var bitLen = bytes.length * 8;
    bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    var hi = Math.floor(bitLen / 4294967296), lo = bitLen >>> 0;
    bytes.push((hi >>> 24) & 0xff, (hi >>> 16) & 0xff, (hi >>> 8) & 0xff, hi & 0xff,
               (lo >>> 24) & 0xff, (lo >>> 16) & 0xff, (lo >>> 8) & 0xff, lo & 0xff);
    var w = new Array(64);
    function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }
    for (var b = 0; b < bytes.length; b += 64) {
      for (var t = 0; t < 16; t++) {
        w[t] = ((bytes[b + t * 4] << 24) | (bytes[b + t * 4 + 1] << 16) | (bytes[b + t * 4 + 2] << 8) | bytes[b + t * 4 + 3]) >>> 0;
      }
      for (t = 16; t < 64; t++) {
        var s0 = (rotr(w[t - 15], 7) ^ rotr(w[t - 15], 18) ^ (w[t - 15] >>> 3)) >>> 0;
        var s1 = (rotr(w[t - 2], 17) ^ rotr(w[t - 2], 19) ^ (w[t - 2] >>> 10)) >>> 0;
        w[t] = (w[t - 16] + s0 + w[t - 7] + s1) >>> 0;
      }
      var a = H[0], bb = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (t = 0; t < 64; t++) {
        var S1 = (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) >>> 0;
        var ch = ((e & f) ^ ((~e) & g)) >>> 0;
        var t1 = (h + S1 + ch + K[t] + w[t]) >>> 0;
        var S0 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) >>> 0;
        var maj = ((a & bb) ^ (a & c) ^ (bb & c)) >>> 0;
        var t2 = (S0 + maj) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = bb; bb = a; a = (t1 + t2) >>> 0;
      }
      H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + bb) >>> 0; H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
      H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0; H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
    }
    var out = new Uint8Array(32);
    for (var j = 0; j < 8; j++) {
      out[j * 4] = (H[j] >>> 24) & 0xff; out[j * 4 + 1] = (H[j] >>> 16) & 0xff;
      out[j * 4 + 2] = (H[j] >>> 8) & 0xff; out[j * 4 + 3] = H[j] & 0xff;
    }
    return out;
  }

  function offlineSolveChallenge(ch, done) {
    var salt = ch.salt, bits = ch.difficulty;
    var fullZero = Math.floor(bits / 8), rest = bits % 8;
    var expected = Math.pow(2, bits);
    var nonce = 0, hashes = 0, found = null;
    var BATCH = 3000;
    function meets(d) {
      for (var i = 0; i < fullZero; i++) if (d[i] !== 0) return false;
      if (rest && ((d[fullZero] >> (8 - rest)) !== 0)) return false;
      return true;
    }
    function slice() {
      var end = nonce + BATCH;
      for (; nonce < end; nonce++, hashes++) {
        if (meets(sha256Bytes(salt + ":" + nonce))) { found = nonce; break; }
      }
      if (found !== null || hashes > expected * 32) { done(found, hashes); return; }
      offlineSetProgress(Math.min(99, Math.floor(hashes / expected * 100)),
        "Solving offline check… " + Math.min(99, Math.floor(hashes / expected * 100)) + "%");
      setTimeout(slice, 0);
    }
    slice();
  }

  function startOfflineCheck() {
    if (offlineSolving) return;
    var userEl = document.getElementById("username");
    var username = userEl ? userEl.value.trim() : "";
    if (!username) {
      setTurnstileState("error", "Type your username first, then use the offline check.");
      return;
    }
    offlineSolving = true;
    hideOfflineOption();
    if (offlineCheckBox) offlineCheckBox.style.display = "block";
    offlineSetProgress(0, "Getting challenge from this server…");
    fetch("/api/auth/bot-check/challenge/?username=" + encodeURIComponent(username), {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" }
    }).then(function (r) {
      return r.json().then(function (d) { return { s: r.status, d: d }; });
    }).then(function (out) {
      if (!out.d || !out.d.ok) {
        offlineSolving = false;
        setTurnstileState("error", (out.d && out.d.error) || "Offline check unavailable.");
        showOfflineOption();
        return;
      }
      var ch = out.d;
      offlineSetProgress(1, "Solving… this takes a few seconds on this device.");
      offlineSolveChallenge(ch, function (found) {
        offlineSolving = false;
        if (found === null || found === undefined) {
          setTurnstileState("error", "Offline check took too long — try again.");
          showOfflineOption();
          return;
        }
        if (offlineProofInput) offlineProofInput.value = JSON.stringify({ id: ch.id, nonce: String(found) });
        offlineSolvedFor = username.toLowerCase();
        if (offlineCheckBox) offlineCheckBox.style.display = "none";
        setTurnstileState("ok", "✓ Offline check passed. You can log in now.");
        hideTurnstileRetry();
      });
    }).catch(function () {
      offlineSolving = false;
      setTurnstileState("error", "Network error reaching this server.");
      showOfflineOption();
    });
  }

  if (offlineCheckBtn) offlineCheckBtn.addEventListener("click", startOfflineCheck);

  // A proof is bound to one username — typing a different name voids it.
  var usernameEl = document.getElementById("username");
  if (usernameEl) usernameEl.addEventListener("input", function () {
    if (offlineProofValid() && usernameEl.value.trim().toLowerCase() !== offlineSolvedFor) {
      offlineProofInput.value = "";
      offlineSolvedFor = "";
      if (turnstileEnabled && !turnstileToken()) {
        setTurnstileState("error", "Username changed — run the offline check again.");
        showOfflineOption();
      }
    }
  });

  // Password Toggle Functionality
  const passwordToggleBtn = document.getElementById('passwordToggle');
  const passwordInput = document.getElementById('password');
  const passwordToggleIcon = document.getElementById('passwordToggleIcon');

  if (passwordToggleBtn && passwordInput) {
    passwordToggleBtn.addEventListener('click', function (e) {
      e.preventDefault();

      const isPassword = passwordInput.type === 'password';
      passwordInput.type = isPassword ? 'text' : 'password';

      // Update icon
      if (isPassword) {
        passwordToggleIcon.classList.remove('fa-eye');
        passwordToggleIcon.classList.add('fa-eye-slash');
        passwordToggleBtn.setAttribute('aria-label', 'Hide password');
      } else {
        passwordToggleIcon.classList.remove('fa-eye-slash');
        passwordToggleIcon.classList.add('fa-eye');
        passwordToggleBtn.setAttribute('aria-label', 'Show password');
      }
    });
  }

  // Form Validation & Error Handling
  const loginForm = document.getElementById('loginForm');

  if (loginForm) {
    loginForm.addEventListener('submit', function (e) {
      const username = document.getElementById('username').value.trim();
      const password = document.getElementById('password').value;
      const loginError = document.getElementById('loginError');

      // Clear previous error
      if (loginError) {
        loginError.style.display = 'none';
      }

      // Cloudflare security check must be completed before submitting
      // (a solved offline check counts too).
      if (turnstileEnabled && !turnstileToken() && !offlineProofValid()) {
        e.preventDefault();
        setTurnstileState("pending", "Please complete the security check before logging in.");
        return;
      }

      // Basic validation
      if (!username || !password) {
        e.preventDefault();
        if (loginError) {
          loginError.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> <span>Please enter both username and password.</span>';
          loginError.style.display = 'block';
          loginError.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      } else {
        // Stash the typed password tab-locally so the member onboarding gate
        // can pre-fill the temporary-password field after a first sign-in.
        // sessionStorage dies with the tab; the gate clears it on activation
        // and logout clears it too — it is never sent anywhere by this code.
        try {
          sessionStorage.setItem('caufaObTemp', password);
        } catch (err) { /* private mode: gate simply stays empty */ }
      }
    });

    // Clear error on input focus
    const inputs = loginForm.querySelectorAll('input[type="text"], input[type="password"]');
    inputs.forEach(input => {
      input.addEventListener('focus', function () {
        const loginError = document.getElementById('loginError');
        if (loginError) {
          loginError.style.display = 'none';
        }
      });
    });
  }

  // OTP Input Formatting
  const otpInput = document.getElementById('otp');
  if (otpInput) {
    otpInput.addEventListener('input', function (e) {
      // Remove any non-numeric characters
      this.value = this.value.replace(/[^0-9]/g, '');

      // Limit to 6 digits
      if (this.value.length > 6) {
        this.value = this.value.slice(0, 6);
      }

      // Auto-submit if 6 digits entered
      if (this.value.length === 6) {
        // Optional: Auto-submit MFA form
        // document.getElementById('mfaForm').submit();
      }
    });

    // Prevent copy-paste of non-numeric
    otpInput.addEventListener('paste', function (e) {
      e.preventDefault();
      const pastedText = (e.clipboardData || window.clipboardData).getData('text');
      const numericOnly = pastedText.replace(/[^0-9]/g, '');
      this.value = numericOnly.slice(0, 6);
    });
  }

  // Smooth scroll to errors
  function scrollToElement(element) {
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  // Add focus styles for accessibility
  const formInputs = document.querySelectorAll('.form-input');
  formInputs.forEach(input => {
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && this.id === 'username') {
        document.getElementById('password').focus();
      }
      if (e.key === 'Enter' && this.id === 'password') {
        if (typeof loginForm.requestSubmit === 'function') {
          loginForm.requestSubmit();
        } else {
          loginForm.submit();
        }
      }
    });
  });

  // Prevent multiple form submissions
  if (loginForm) {
    let isSubmitting = false;

    loginForm.addEventListener('submit', function (e) {
      if (e.defaultPrevented) return;
      if (isSubmitting) {
        e.preventDefault();
        return;
      }
      isSubmitting = true;

      // Re-enable after 3 seconds in case of network error
      setTimeout(() => {
        isSubmitting = false;
      }, 3000);
    });
  }

  // Fade in animation on load
  window.addEventListener('load', function () {
    const container = document.querySelector('.login-container');
    if (container) {
      container.style.opacity = '1';
    }
  });

  // Detect caps lock
  const passwordInputElement = document.getElementById('password');
  if (passwordInputElement) {
    let capsLockWarning = document.createElement('div');
    capsLockWarning.id = 'capsLockWarning';
    capsLockWarning.style.cssText = `
      display: none;
      font-size: 12px;
      color: #f57c00;
      margin-top: 6px;
      padding: 6px 8px;
      background: #fff8f0;
      border-left: 2px solid #f57c00;
      border-radius: 4px;
    `;
    capsLockWarning.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Caps Lock is ON';

    passwordInputElement.parentElement.insertAdjacentElement('afterend', capsLockWarning);

    passwordInputElement.addEventListener('keydown', function (e) {
      const isCapsLockOn = e.getModifierState && e.getModifierState('CapsLock');
      if (isCapsLockOn) {
        capsLockWarning.style.display = 'block';
      } else {
        capsLockWarning.style.display = 'none';
      }
    });

    passwordInputElement.addEventListener('keyup', function (e) {
      const isCapsLockOn = e.getModifierState && e.getModifierState('CapsLock');
      if (isCapsLockOn) {
        capsLockWarning.style.display = 'block';
      } else {
        capsLockWarning.style.display = 'none';
      }
    });
  }

  // Console message
  console.log('%cCAUFA System Portal', 'font-size: 20px; font-weight: bold; color: #1b5e3f;');
  console.log('%cUniting faculty and administrators through collaboration, service, and excellence.', 'color: #666;');
})();
