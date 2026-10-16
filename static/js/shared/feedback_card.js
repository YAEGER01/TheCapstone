/* Officer + member feedback prompt + modal.
 *
 * Fetches the Superadmin-authored instrument from /api/feedback/card/ and
 * mounts it wherever `{% include "website/shared/feedback_card.html" %}` put a
 * root. Loaded on the President, Treasurer, Auditor and Member dashboards.
 *
 * Performance notes (the popup used to feel laggy on heavy dashboards):
 *  - The card fetch is deferred to browser idle so the dashboard paints and
 *    becomes interactive first; feedback is never on the critical path.
 *  - No backdrop-filter blur and no CSS :has() selectors: both force costly
 *    full-page style/paint work. Checked options use an .is-checked class
 *    toggled by one delegated change listener below.
 *  - Open/enter animations use requestAnimationFrame instead of forced
 *    synchronous reflows, and focus() uses preventScroll.
 *
 * Behaviour contract:
 *  - The endpoint renders nothing unless there is an open form the viewer's
 *    role may see AND the viewer has not already responded. Normal surveys
 *    are one-shot per form without any extra client state; a Post-Survey
 *    additionally requires its paired Pre-Survey to be completed first.
 *  - Pre/Post surveys are persistent: the toast reads PRE-SURVEY /
 *    POST-SURVEY with an "Answer Now" button, has no dismiss control, and
 *    any logout attempt is intercepted - the toast is re-shown with
 *    emphasis and the modal opens. Logout resumes automatically after
 *    a successful submit.
 *  - The modal is intentionally non-dismissible: no close button, no backdrop
 *    click, no ESC. It stays up until the form is submitted.
 *  - One question per page, with Back / Next and a progress bar.
 *  - After a successful submit the shell is torn down and replaced by a
 *    thank-you toast, so nothing can re-open the same form again.
 *
 * Server-side validation is the real check; the per-page "required" gate here
 * only avoids pointless round-trips.
 */
(function () {
  "use strict";

  var SUBMIT_URL = "/api/feedback/submit/";
  var TOAST_MS = 12000;
  var loaded = false;
  var activeController = null;

  // Any in-dashboard logout affordance: sidebar links, tab links,
  // data-hn-logout menu buttons, and the member logout-confirm button.
  function findLogoutTarget(node) {
    if (!node || !node.closest) return null;
    return node.closest(
      'a[href="/logout/"], a[href$="/logout/"],' +
      "#logoutConfirm, #logoutTabLink, #logoutLink, [data-hn-logout]"
    );
  }

  // Capture-phase so this runs before each dashboard's own logout handler;
  // stopPropagation keeps the dashboard from navigating away first.
  // Registered at parse time so no logout click can slip through early.
  document.addEventListener("click", function (event) {
    if (!activeController || !activeController.hasPendingSurvey()) return;
    var t = event.target ? findLogoutTarget(event.target) : null;
    if (!t) return;
    event.preventDefault();
    event.stopPropagation();
    var url = (t.getAttribute && t.getAttribute("href")) || "/logout/";
    activeController.demandAttention(url);
  }, true);

  // ---------------------------------------------------------------- utils

  function csrfToken(scope) {
    var el = (scope || document).querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  // ---------------------------------------------------------------- toasts

  // Top-centre stack. At most MAX_VISIBLE toasts sit on screen at once; a
  // fourth arrival evicts the oldest (FIFO) instead of overlapping it, which
  // is what used to hide notifications behind each other.
  var MAX_VISIBLE = 3;

  var stackEl = null;

  function stack() {
    if (stackEl && stackEl.isConnected) return stackEl;
    stackEl = el("div", "fb-toast-stack");
    stackEl.setAttribute("aria-live", "polite");
    document.body.appendChild(stackEl);
    return stackEl;
  }

  function animateIn(toast) {
    // Two rAFs let the browser paint the initial state first, so the entry
    // transition runs without a forced synchronous reflow (offsetWidth).
    if (typeof requestAnimationFrame === "function") {
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          toast.classList.add("is-visible");
        });
      });
    } else {
      setTimeout(function () { toast.classList.add("is-visible"); }, 20);
    }
  }

  function retire(toast, immediate) {
    if (!toast || !toast.isConnected) return;
    if (toast.dataset.fbRetiring) return;
    toast.dataset.fbRetiring = "1";
    toast.classList.remove("is-visible");
    toast.classList.add("is-leaving");

    var delay = immediate ? 0 : 380;
    setTimeout(function () {
      if (toast.isConnected) toast.remove();
    }, delay);
  }

  function trimStack() {
    var live = stack().querySelectorAll(".fb-toast:not(.is-leaving)");
    Array.prototype.slice.call(live, MAX_VISIBLE).forEach(function (toast) {
      retire(toast, true);
    });
  }

  function pushToast(toast) {
    var host = stack();
    // Strip the standalone-float positioning; the stack owns placement now.
    toast.classList.remove("fb-toast-float");
    host.appendChild(toast);
    trimStack();
    animateIn(toast);
    return toast;
  }

  function makeToast(message, kind) {
    var toast = el("div", "fb-toast is-" + (kind || "info"));
    toast.setAttribute("role", "status");

    var icon = el("span", "fb-toast-icon");
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = kind === "success"
      ? '<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>'
      : '<svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8v5M12 16h.01"/></svg>';

    toast.appendChild(icon);
    toast.appendChild(el("span", "fb-toast-text", message));
    return toast;
  }

  function showToast(message, kind) {
    var toast = pushToast(makeToast(message, kind));
    setTimeout(function () { retire(toast); }, TOAST_MS);
    return toast;
  }

  // ---------------------------------------------------------------- modal

  function createController(shell) {
    var overlay = shell.querySelector("[data-fb-overlay]");
    var form = shell.querySelector("[data-fb-form-el]");
    var pages = Array.prototype.slice.call(shell.querySelectorAll(".fb-page"));
    var backBtn = shell.querySelector("[data-fb-back]");
    var nextBtn = shell.querySelector("[data-fb-next]");
    var submitBtn = shell.querySelector("[data-fb-submit]");
    var counterEl = shell.querySelector("[data-fb-current]");
    var progressEl = shell.querySelector("[data-fb-progress-bar]");
    var errorEl = shell.querySelector("[data-fb-error]");
    var promptToast = shell.querySelector("[data-fb-toast]");

    var index = 0;
    var submitting = false;
    var done = false;
    var pendingLogoutUrl = null;

    function isPersistent() {
      return shell.getAttribute("data-fb-persistent") === "1";
    }

    function hasPendingSurvey() {
      return isPersistent() && !done && shell.isConnected;
    }

    // Logout guard for persistent surveys: pin the toast with emphasis and
    // open the modal. The saved logout destination resumes after submit.
    function demandAttention(url) {
      pendingLogoutUrl = url || "/logout/";
      if (promptToast && promptToast.isConnected) {
        promptToast.classList.add("is-emphasis");
        if (!promptToast.classList.contains("is-visible")) {
          pushToast(promptToast);
        }
      }
      // Brief beat so the highlighted popup registers before the modal
      // takes over (clicking Answer Now sooner just opens it immediately).
      setTimeout(function () {
        if (!done) open();
      }, 900);
    }

    function requiredMarker(page) {
      var legend = page.querySelector(".fb-prompt");
      return legend && legend.querySelector(".fb-required");
    }

    function isSatisfied(page) {
      if (!requiredMarker(page)) return true;

      var boxes = page.querySelectorAll("input[type=radio], input[type=checkbox]");
      if (boxes.length) {
        for (var i = 0; i < boxes.length; i++) {
          if (boxes[i].checked) return true;
        }
        return false;
      }

      var area = page.querySelector("textarea");
      return !!(area && area.value.trim());
    }

    function render() {
      pages.forEach(function (page, i) { page.hidden = i !== index; });

      var last = index === pages.length - 1;
      backBtn.disabled = index === 0;
      nextBtn.hidden = last;
      submitBtn.hidden = !last;
      counterEl.textContent = String(index + 1);

      var pct = pages.length > 1 ? ((index + 1) / pages.length) * 100 : 100;
      progressEl.style.width = pct + "%";

      var focusTarget = pageFocusTarget();
      if (focusTarget && typeof focusTarget.focus === "function") {
        try {
          focusTarget.focus({ preventScroll: true });
        } catch (err) {
          focusTarget.focus();
        }
      }
    }

    function pageFocusTarget() {
      var page = pages[index];
      return page ? page.querySelector("input, textarea") : null;
    }

    function showError(message) {
      errorEl.textContent = message || "";
      errorEl.hidden = !message;
    }

    function open() {
      overlay.hidden = false;
      overlay.scrollTop = 0;
      // rAF instead of a forced reflow: lets the browser lay out the
      // freshly unhidden overlay before starting the fade/slide.
      var show = function () { overlay.classList.add("is-open"); };
      if (typeof requestAnimationFrame === "function") {
        requestAnimationFrame(function () {
          requestAnimationFrame(show);
        });
      } else {
        setTimeout(show, 20);
      }
      if (promptToast) promptToast.classList.remove("is-visible");
      render();
    }

    function close() {
      overlay.classList.remove("is-open");
      setTimeout(function () { overlay.hidden = true; }, 200);
    }

    // The modal is deliberately not dismissible: no ESC handler, no
    // backdrop-click handler, and no close button is rendered.
    function trapFocus(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        return;
      }
      if (event.key !== "Tab") return;

      var focusables = overlay.querySelectorAll(
        "button:not([disabled]), input:not([disabled]), textarea:not([disabled])"
      );
      if (!focusables.length) return;
      var first = focusables[0];
      var lastEl = focusables[focusables.length - 1];

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && document.activeElement === lastEl) {
        event.preventDefault();
        first.focus();
      }
    }

    function wireCounters() {
      Array.prototype.forEach.call(
        shell.querySelectorAll("[data-fb-maxlength]"),
        function (area) {
          var field = area.closest(".fb-question");
          if (!field) return;
          var counter = field.querySelector("[data-fb-counter]");
          var count = field.querySelector("[data-fb-count]");
          if (!counter || !count) return;
          var max = parseInt(area.getAttribute("data-fb-maxlength"), 10) || area.maxLength;

          function sync() {
            var used = area.value.length;
            count.textContent = String(used);
            counter.hidden = false;
            counter.classList.toggle("is-near", used > max * 0.9);
          }

          area.addEventListener("input", sync);
          sync();
        }
      );
    }

    // Class-based checked styling (see CSS note): one delegated listener
    // covers every radio/checkbox instead of per-option handlers.
    function syncCheckedOptions() {
      Array.prototype.forEach.call(
        shell.querySelectorAll(".fb-option, .fb-likert-option"),
        function (label) {
          var input = label.querySelector("input");
          label.classList.toggle("is-checked", !!(input && input.checked));
        }
      );
    }

    function submit() {
      if (submitting) return;

      // Gate every required page, not just the last one, so a skipped
      // question cannot survive to the server as a confusing 400.
      for (var i = 0; i < pages.length; i++) {
        if (!isSatisfied(pages[i])) {
          index = i;
          render();
          showError("Please answer every required question before submitting.");
          return;
        }
      }

      submitting = true;
      showError("");
      submitBtn.disabled = true;
      submitBtn.textContent = "Submitting…";

      fetch(SUBMIT_URL, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(form),
          "X-Requested-With": "XMLHttpRequest"
        },
        credentials: "same-origin",
        body: new URLSearchParams(new FormData(form))
      })
        .then(function (resp) {
          return resp.json().catch(function () {
            return { ok: false, error: "Unexpected server response (" + resp.status + ")." };
          });
        })
        .then(function (data) {
          if (data && data.ok) {
            done = true;
            var goLogout = pendingLogoutUrl;
            // Tear the whole shell down so the form can never re-open.
            close();
            shell.remove();
            activeController = null;
            if (goLogout) {
              window.location.href = goLogout;
              return;
            }
            showToast(
              data.message || "Thanks for submitting your feedback",
              "success"
            );
            return;
          }
          showError((data && data.error) || "Could not submit your response.");
          submitting = false;
          submitBtn.disabled = false;
          submitBtn.textContent = "Submit Feedback";
        })
        .catch(function () {
          showError("Network error while submitting. Check your connection and try again.");
          submitting = false;
          submitBtn.disabled = false;
          submitBtn.textContent = "Submit Feedback";
        });
    }

    // ------------------------------------------------------------- wiring

    backBtn.addEventListener("click", function () {
      if (index > 0) { index -= 1; showError(""); render(); }
    });

    nextBtn.addEventListener("click", function () {
      if (!isSatisfied(pages[index])) {
        showError("Please answer this question before continuing.");
        return;
      }
      if (index < pages.length - 1) { index += 1; showError(""); render(); }
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      submit();
    });

    // Clear the inline error as soon as the officer starts fixing it,
    // and keep the class-based checked styling in sync (one listener).
    form.addEventListener("input", function () { showError(""); });
    form.addEventListener("change", function () { showError(""); syncCheckedOptions(); });

    // Key handling is bound to the overlay only. A document-level listener
    // would swallow the host dashboard's own shortcuts, and ESC must not
    // close this modal anyway.
    overlay.addEventListener("keydown", function (event) {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        submit();
        return;
      }
      trapFocus(event);
    });

    // The prompt toast hides behind the modal rather than evicting itself
    // from the stack, so the stack never jumps while the officer is typing.
    if (promptToast) {
      promptToast.addEventListener("click", function () {
        promptToast.classList.remove("is-visible");
      });
    }

    var openBtn = shell.querySelector("[data-fb-open]");
    if (openBtn) openBtn.addEventListener("click", open);

    var dismissBtn = shell.querySelector("[data-fb-dismiss-toast]");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", function (event) {
        event.stopPropagation();
        retire(promptToast);
        setTimeout(function () {
          if (promptToast && promptToast.isConnected) promptToast.hidden = true;
        }, 380);
      });
    }

    wireCounters();
    syncCheckedOptions();

    return {
      open: open,
      pages: pages.length,
      hasPendingSurvey: hasPendingSurvey,
      demandAttention: demandAttention
    };
  }
  // ---------------------------------------------------------------- boot

  function init() {
    if (loaded) return;
    loaded = true;

    var root = document.getElementById("fb-card-root");
    if (!root) return;

    // Deferred on purpose: the dashboard must paint and go interactive
    // first. Feedback is advisory, never on the critical path, and firing
    // the fetch during initial boot was a visible source of jank.
    var run = function () {
      fetchEndpoint(root);
    };
    if (typeof requestIdleCallback === "function") {
      requestIdleCallback(run, { timeout: 1500 });
    } else {
      setTimeout(run, 900);
    }
  }

  function fetchEndpoint(root) {
    var endpoint = root.getAttribute("data-fb-endpoint") || "/api/feedback/card/";
    fetch(endpoint, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin"
    })
      .then(function (resp) { return resp.ok ? resp.text() : ""; })
      .then(function (html) {
        if (!html || !html.trim()) return;

        // The toast + modal are mounted as a direct child of <body>, not into
        // the dashboard's layout tree. The officer dashboards are
        // `height:100%; overflow:hidden` flex shells, so a fixed overlay
        // nested inside them ends up in a container that cannot scroll -
        // the modal then renders but the page appears frozen.
        var host = document.createElement("div");
        host.className = "fb-host";
        host.innerHTML = html;
        document.body.appendChild(host);
        root.hidden = true;

        var shell = host.querySelector("[data-fb-shell]");
        if (!shell) { host.remove(); return; }

        var controller = createController(shell);
        if (!controller.pages) {
          shell.remove();
          return;
        }
        activeController = controller;

        // No auto-open: the prompt toast is the entry point. It re-renders on
        // every page load until the officer submits a response, and stops
        // appearing entirely once that form has been answered.
        var promptToast = shell.querySelector("[data-fb-toast]");
        if (promptToast) pushToast(promptToast);
      })
      .catch(function () { /* no form available - stay hidden */ });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
