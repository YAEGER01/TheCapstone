/* PWA install / "Download App" helper for standalone dashboard pages.
 *
 * Suppresses the browser's automatic install mini-infobar, surfaces our own
 * one-time banner, and hides it permanently once the app is installed.
 *
 * Requires the host page to link manifest.json and register a service worker.
 * Works with the markup:
 *   <div id="installBanner" hidden>
 *     ...
 *     <button id="installBannerBtn" type="button">Download App</button>
 *   </div>
 */
(function () {
  "use strict";

  var BANNER_ID = "installBanner";
  var BUTTON_ID = "installBannerBtn";
  var STORAGE_KEY = "caufa_pwa_installed";

  var banner = document.getElementById(BANNER_ID);
  var button = document.getElementById(BUTTON_ID);
  if (!banner || !button) return;

  var deferredPrompt = null;

  function readFlag() {
    try { return window.localStorage.getItem(STORAGE_KEY) === "1"; }
    catch (e) { return false; }
  }

  function writeFlag() {
    try { window.localStorage.setItem(STORAGE_KEY, "1"); } catch (e) {}
  }

  function isStandalone() {
    try {
      if (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) return true;
      if (window.matchMedia && window.matchMedia("(display-mode: window-controls-overlay)").matches) return true;
    } catch (e) {}
    return window.navigator.standalone === true;
  }

  function isIos() {
    var ua = window.navigator.userAgent || "";
    if (/iphone|ipad|ipod/i.test(ua)) return true;
    // iPadOS 13+ reports itself as "Macintosh" but exposes touch points.
    return window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1;
  }

  function showBanner() { banner.hidden = false; }
  function hideBanner() { banner.hidden = true; }

  // Already installed on this device/browser -> never show the banner.
  if (isStandalone() || readFlag()) {
    writeFlag();
    hideBanner();
  } else {
    showBanner();
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    // Suppress the default browser mini-infobar; our banner is the entry point.
    event.preventDefault();
    deferredPrompt = event;
    if (!readFlag() && !isStandalone()) showBanner();
  });

  window.addEventListener("appinstalled", function () {
    deferredPrompt = null;
    writeFlag();
    hideBanner();
  });

  /* ---------- "How to install" modal (self-contained styles) ---------- */

  var modal = null;

  function buildModal() {
    if (modal) return modal;

    var overlay = document.createElement("div");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.style.cssText =
      "position:fixed;inset:0;background:rgba(15,23,42,.45);display:flex;" +
      "align-items:center;justify-content:center;padding:20px;z-index:9999;" +
      "opacity:0;visibility:hidden;transition:opacity .2s,visibility .2s;";

    var box = document.createElement("div");
    box.style.cssText =
      "width:100%;max-width:360px;background:#fff;border-radius:16px;padding:24px;" +
      "box-shadow:0 20px 50px rgba(0,0,0,.25);font-family:inherit;color:#1b5e20;" +
      "transform:translateY(10px) scale(.98);transition:transform .2s;";

    var title = document.createElement("div");
    title.style.cssText = "font-size:17px;font-weight:700;margin-bottom:8px;";

    var text = document.createElement("p");
    text.style.cssText = "font-size:13.5px;color:#64748b;line-height:1.6;margin-bottom:20px;";

    var actions = document.createElement("div");
    actions.style.cssText = "display:flex;";

    var ok = document.createElement("button");
    ok.type = "button";
    ok.textContent = "Got it";
    ok.style.cssText =
      "flex:1;border:none;background:#1b5e20;color:#fff;font-size:13px;font-weight:600;" +
      "padding:10px 18px;border-radius:10px;cursor:pointer;font-family:inherit;";

    actions.appendChild(ok);
    box.appendChild(title);
    box.appendChild(text);
    box.appendChild(actions);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    function close() {
      overlay.style.opacity = "0";
      overlay.style.visibility = "hidden";
      box.style.transform = "translateY(10px) scale(.98)";
    }

    ok.addEventListener("click", close);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) close(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && overlay.style.visibility === "visible") close();
    });

    modal = { overlay: overlay, box: box, title: title, text: text, ok: ok, close: close };
    return modal;
  }

  function openModal(title, html) {
    var m = buildModal();
    m.title.textContent = title;
    m.text.innerHTML = html;
    m.overlay.style.visibility = "visible";
    m.overlay.style.opacity = "1";
    m.box.style.transform = "translateY(0) scale(1)";
    m.ok.focus();
  }

  function showInstallInstructions() {
    var steps = isIos()
      ? "Tap the <strong>Share</strong> icon, then choose <strong>Add to Home Screen</strong>."
      : "Open your browser menu (&#8942;), then choose <strong>Install app</strong> or <strong>Add to Home screen</strong>.";
    openModal("How to install the app", steps);
  }

  button.addEventListener("click", function () {
    if (deferredPrompt) {
      var prompt = deferredPrompt;
      deferredPrompt = null;
      button.disabled = true;
      prompt.prompt();
      var choice = prompt.userChoice;
      if (choice && typeof choice.then === "function") {
        choice.then(function (result) {
          button.disabled = false;
          if (result && result.outcome === "accepted") {
            writeFlag();
            hideBanner();
          }
          // Declined -> keep the banner so the member can try again.
        }).catch(function () { button.disabled = false; });
      } else {
        button.disabled = false;
      }
      return;
    }
    showInstallInstructions();
  });
})();
