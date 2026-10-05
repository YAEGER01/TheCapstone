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

      // Cloudflare security check must be completed before submitting.
      if (turnstileEnabled && !turnstileToken()) {
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
