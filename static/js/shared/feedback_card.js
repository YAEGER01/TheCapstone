/* Officer feedback prompt + modal.
 *
 * Fetches the Superadmin-authored instrument from /api/feedback/card/ and
 * mounts it wherever `{% include "website/shared/feedback_card.html" %}` put a
 * root. Loaded on the President, Treasurer and Auditor dashboards.
 *
 * Behaviour contract:
 *  - The endpoint renders nothing unless there is an open form the officer's
 *    role may see AND the officer has not already responded, so this is
 *    one-shot per form without any extra client state.
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
    // Force a reflow so the entry transition actually runs.
    void toast.offsetWidth;
    toast.classList.add("is-visible");
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
      if (focusTarget) focusTarget.focus();
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
      void overlay.offsetWidth;
      overlay.classList.add("is-open");
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
            // Tear the whole shell down so the form can never re-open.
            close();
            shell.remove();
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

    // Clear the inline error as soon as the officer starts fixing it.
    form.addEventListener("input", function () { showError(""); });
    form.addEventListener("change", function () { showError(""); });

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

    return { open: open, pages: pages.length };
  }
  // ---------------------------------------------------------------- boot

  function init() {
    if (loaded) return;
    loaded = true;

    var root = document.getElementById("fb-card-root");
    if (!root) return;

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
