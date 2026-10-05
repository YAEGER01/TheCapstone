/*
 * SimpleModal - plain modal dialogs (alert / confirm / prompt / custom).
 * Replaces SweetAlert2 popups with a simple card so dialogs look plain
 * and consistent with the rest of the dashboard.
 *
 * Modals are STACKED: opening a prompt/confirm while a review modal is
 * open layers it on top and restores the review modal underneath on close.
 *
 * API:
 *   SimpleModal.alert(message, title)                  -> Promise<void>
 *   SimpleModal.confirm(message, {title, okText, cancelText, danger}) -> Promise<boolean>
 *   SimpleModal.prompt(label, {title, placeholder, defaultValue, multiline,
 *                              required, okText, danger})            -> Promise<string|null>
 *   SimpleModal.open({title, html, width})             -> {el, close}  (custom content)
 *   SimpleModal.close()
 *   SimpleModal.isOpen()
 */
(function () {
  "use strict";

  var CSS = [
    ".sm-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.45);display:none;align-items:center;justify-content:center;z-index:5000;}",
    ".sm-card{background:#fff;border:1px solid #d7d7d7;border-radius:10px;width:90%;max-width:440px;max-height:85vh;overflow-y:auto;padding:22px;font-family:Arial,Helvetica,sans-serif;}",
    ".sm-title{margin:0 0 8px 0;font-size:1.05rem;color:#222;font-weight:700;}",
    ".sm-body{margin:0;font-size:0.92rem;color:#333;line-height:1.5;}",
    ".sm-body .sm-message{margin:0 0 16px 0;white-space:pre-line;}",
    ".sm-input{width:100%;box-sizing:border-box;padding:9px 11px;border:1px solid #ccc;border-radius:3px;font-family:inherit;font-size:0.9rem;resize:vertical;}",
    ".sm-error{color:#c62828;font-size:0.8rem;margin:6px 0 0 0;display:none;}",
    ".sm-buttons{display:flex;gap:10px;justify-content:flex-end;margin-top:18px;}",
    ".sm-buttons button{padding:8px 16px;border-radius:3px;border:1px solid #bbb;background:#fff;color:#333;font-size:0.9rem;cursor:pointer;font-family:inherit;}",
    ".sm-buttons button.sm-ok{background:#2e7d32;border:1px solid #2e7d32;color:#fff;}",
    ".sm-buttons button.sm-ok.sm-danger{background:#c62828;border:1px solid #c62828;}",
    /* review layout: details table on the left, proof on the right;
       both columns stretch to the same height so the proof fills the space */
    ".sm-review{display:flex;gap:16px;align-items:stretch;flex-wrap:wrap;}",
    ".sm-review-info{flex:1 1 0;min-width:260px;}",
    ".sm-review-proof{flex:1 1 0;min-width:220px;display:flex;}",
    ".sm-details{width:100%;border-collapse:collapse;font-size:0.88rem;color:#333;}",
    ".sm-details th,.sm-details td{border:1px solid #ddd;padding:7px 10px;text-align:left;vertical-align:top;}",
    ".sm-details th{background:#f5f5f5;font-weight:600;color:#333;width:40%;}",
    ".sm-proof{border:1px solid #ddd;background:#fafafa;padding:10px;box-sizing:border-box;flex:1;display:flex;flex-direction:column;}",
    ".sm-proof h4{margin:0 0 8px 0;font-size:0.92rem;color:#222;}",
    ".sm-proof img{width:100%;flex:1;min-height:0;object-fit:contain;border:1px solid #ddd;cursor:zoom-in;}",
    ".sm-proof iframe{width:100%;flex:1;min-height:220px;border:1px solid #ddd;}",
    ".sm-actions{display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap;margin-top:16px;}",
    ".sm-actions .sm-btn{padding:7px 16px;font-size:0.88rem;font-family:inherit;border:1px solid #ccc;background:#f2f2f2;color:#333;cursor:pointer;border-radius:3px;}",
    ".sm-actions .sm-btn.sm-primary{background:#2e7d32;border:1px solid #2e7d32;color:#fff;}",
    ".sm-actions .sm-btn.sm-secondary{background:#fff;border:1px solid #ccc;color:#444;}",
    ".sm-actions .sm-btn.sm-danger{background:#c62828;border:1px solid #c62828;color:#fff;}"
  ].join("");

  var styleAdded = false;
  var stack = [];

  function ensureStyles() {
    if (styleAdded) return;
    var style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
    styleAdded = true;
  }

  function buildLayer(width) {
    ensureStyles();
    var overlay = document.createElement("div");
    overlay.className = "sm-overlay";
    overlay.style.zIndex = String(5000 + stack.length * 10);
    var card = document.createElement("div");
    card.className = "sm-card";
    if (width) card.style.maxWidth = width;
    overlay.appendChild(card);
    var layer = { overlay: overlay, card: card, onBackdrop: null };
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay && typeof layer.onBackdrop === "function") layer.onBackdrop();
    });
    document.body.appendChild(overlay);
    stack.push(layer);
    overlay.style.display = "flex";
    return layer;
  }

  function closeLayer(layer) {
    var idx = stack.indexOf(layer);
    if (idx !== -1) stack.splice(idx, 1);
    if (layer.overlay && layer.overlay.parentNode) layer.overlay.parentNode.removeChild(layer.overlay);
    if (typeof layer.onClose === "function") {
      var cb = layer.onClose;
      layer.onClose = null;
      cb();
    }
  }

  function clearCard(card) {
    card.innerHTML = "";
  }

  function addButtons(row, buttons) {
    var wrap = document.createElement("div");
    wrap.className = "sm-buttons";
    buttons.forEach(function (b) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = b.text;
      if (b.ok) btn.className = b.danger ? "sm-ok sm-danger" : "sm-ok";
      btn.addEventListener("click", b.onClick);
      wrap.appendChild(btn);
    });
    row.appendChild(wrap);
  }

  function addTitleAndBody(card, title, message) {
    var h = document.createElement("h3");
    h.className = "sm-title";
    h.textContent = title || "Notice";
    var body = document.createElement("div");
    body.className = "sm-body";
    var p = document.createElement("p");
    p.className = "sm-message";
    p.textContent = message || "";
    body.appendChild(p);
    card.appendChild(h);
    card.appendChild(body);
    return body;
  }

  function alert(message, title) {
    var layer = buildLayer();
    var body = addTitleAndBody(layer.card, title, message);
    var row = document.createElement("div");
    body.appendChild(row);
    return new Promise(function (resolve) {
      layer.onBackdrop = function () { closeLayer(layer); resolve(); };
      addButtons(row, [{ text: "OK", ok: true, onClick: function () { closeLayer(layer); resolve(); } }]);
    });
  }

  function confirm(message, opts) {
    opts = opts || {};
    var layer = buildLayer();
    var body = addTitleAndBody(layer.card, opts.title || "Confirm", message);
    var row = document.createElement("div");
    body.appendChild(row);
    return new Promise(function (resolve) {
      layer.onBackdrop = function () { closeLayer(layer); resolve(false); };
      addButtons(row, [
        { text: opts.cancelText || "Cancel", onClick: function () { closeLayer(layer); resolve(false); } },
        { text: opts.okText || "Confirm", ok: true, danger: !!opts.danger, onClick: function () { closeLayer(layer); resolve(true); } }
      ]);
    });
  }

  function prompt(label, opts) {
    opts = opts || {};
    var layer = buildLayer();
    var card = layer.card;
    clearCard(card);
    var h = document.createElement("h3");
    h.className = "sm-title";
    h.textContent = opts.title || "Input";
    var body = document.createElement("div");
    body.className = "sm-body";
    var p = document.createElement("p");
    p.className = "sm-message";
    p.style.marginBottom = "8px";
    p.textContent = label || "";
    body.appendChild(p);
    var input;
    if (opts.multiline) {
      input = document.createElement("textarea");
      input.rows = 4;
    } else {
      input = document.createElement("input");
      input.type = opts.inputType || "text";
    }
    input.className = "sm-input";
    input.placeholder = opts.placeholder || "";
    input.value = opts.defaultValue || "";
    body.appendChild(input);
    var err = document.createElement("p");
    err.className = "sm-error";
    err.textContent = opts.requiredMessage || (label ? label.replace(/[:.]$/, "") + " is required." : "This field is required.");
    body.appendChild(err);
    card.appendChild(h);
    card.appendChild(body);
    var row = document.createElement("div");
    body.appendChild(row);

    return new Promise(function (resolve) {
      function submit() {
        var value = input.value.trim();
        if (opts.required && !value) {
          err.style.display = "block";
          return;
        }
        closeLayer(layer);
        resolve(value);
      }
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !opts.multiline) submit();
      });
      layer.onBackdrop = function () { closeLayer(layer); resolve(null); };
      addButtons(row, [
        { text: opts.cancelText || "Cancel", onClick: function () { closeLayer(layer); resolve(null); } },
        { text: opts.okText || "Confirm", ok: true, danger: !!opts.danger, onClick: submit }
      ]);
      input.focus();
    });
  }

  /*
   * Custom content modal. Returns { el, close }.
   * `el` is a div already attached to the DOM; callers build their own
   * inner HTML and wire up their own buttons, then call close().
   *
   * opts.dismissible === false  → backdrop click does nothing (buttons only).
   * opts.radius                 → card border-radius override (e.g. "14px").
   */
  function open(opts) {
    opts = opts || {};
    var layer = buildLayer(opts.width);
    clearCard(layer.card);
    if (opts.radius) layer.card.style.borderRadius = opts.radius;
    var h = document.createElement("h3");
    h.className = "sm-title";
    h.textContent = opts.title || "Details";
    var content = document.createElement("div");
    content.className = "sm-body";
    if (typeof opts.html === "string") {
      content.innerHTML = opts.html;
    } else if (opts.html) {
      content.appendChild(opts.html);
    }
    layer.card.appendChild(h);
    layer.card.appendChild(content);
    // Non-dismissible: leave onBackdrop unset so overlay clicks are ignored.
    if (opts.dismissible !== false) {
      layer.onBackdrop = function () { closeLayer(layer); };
    }
    return {
      el: content,
      close: function () { closeLayer(layer); }
    };
  }

  function close() {
    if (stack.length) closeLayer(stack[stack.length - 1]);
  }

  function isOpen() {
    return stack.length > 0;
  }

  /*
   * Proof lightbox: shows an enlarged proof image (or a PDF) in a stacked
   * modal on top of the review modal, so the page never navigates away.
   */
  function lightbox(src, caption) {
    var isPdf = /\.pdf(\?|$)/i.test(src);
    var layer = buildLayer("1000px");
    clearCard(layer.card);
    var h = document.createElement("h3");
    h.className = "sm-title";
    h.textContent = caption || (isPdf ? "Proof Document" : "Proof of Payment");
    var body = document.createElement("div");
    body.className = "sm-body";
    var media;
    if (isPdf) {
      media = document.createElement("iframe");
      media.src = src;
      media.style.cssText = "width:100%;height:70vh;border:1px solid #ddd;background:#fff;";
    } else {
      media = document.createElement("img");
      media.src = src;
      media.alt = caption || "Proof";
      media.style.cssText = "display:block;max-width:100%;max-height:70vh;margin:0 auto;border:1px solid #ddd;";
    }
    body.appendChild(media);
    var row = document.createElement("div");
    body.appendChild(row);
    layer.card.appendChild(h);
    layer.card.appendChild(body);
    layer.onBackdrop = function () { closeLayer(layer); };
    addButtons(row, [{ text: "Close", onClick: function () { closeLayer(layer); } }]);
  }

  /* Clicking a proof image (or PDF link) inside any .sm-proof box enlarges it in place. */
  document.addEventListener("click", function (e) {
    if (!e.target || typeof e.target.closest !== "function") return;
    var img = e.target.closest(".sm-proof img");
    if (img && img.src) {
      e.preventDefault();
      lightbox(img.src, img.getAttribute("alt"));
      return;
    }
    var link = e.target.closest(".sm-proof a[href]");
    if (link) {
      var href = link.getAttribute("href") || "";
      if (/\.pdf(\?|$)/i.test(href)) {
        e.preventDefault();
        lightbox(href, "Proof Document");
      }
    }
  });

  window.SimpleModal = {
    alert: alert,
    confirm: confirm,
    prompt: prompt,
    open: open,
    close: close,
    isOpen: isOpen
  };
})();
