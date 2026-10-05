// file_queue.js - Shared file upload queue for Treasurer dashboard

window.FileQueue = (function () {
  var queues = {};

  function isPreviewable(file) {
    return file.type.startsWith("image/") || file.type === "application/pdf";
  }

  function render(key) {
    var q = queues[key];
    if (!q) return;
    var container = document.getElementById(q.containerId);
    if (!container) return;
    container.innerHTML = "";
    for (var fi = 0; fi < q.files.length; fi++) {
      (function (fiIdx) {
        var file = q.files[fiIdx];

        // Compact row mode: name + View + Remove (used by the aid filing cards).
        if (q.mode === "rows") {
          var row = document.createElement("div");
          row.className = "fq-row";
          row.title = file.name;
          var ico = document.createElement("span");
          ico.className = "fq-row-ico";
          ico.innerHTML = file.type.indexOf("image/") === 0
            ? '<i class="fa-regular fa-file-image"></i>'
            : (file.type === "application/pdf" ? '<i class="fa-solid fa-file-pdf"></i>' : '<i class="fa-solid fa-file-word"></i>');
          var nameWrap = document.createElement("span");
          nameWrap.className = "fq-row-name";
          nameWrap.textContent = file.name;
          var sizeEl = document.createElement("small");
          sizeEl.className = "fq-row-size";
          sizeEl.textContent = file.size > 1048576
            ? (file.size / 1048576).toFixed(1) + " MB"
            : Math.max(1, Math.round(file.size / 1024)) + " KB";
          nameWrap.appendChild(sizeEl);
          var actions = document.createElement("span");
          actions.className = "fq-row-actions";
          if (isPreviewable(file)) {
            var viewBtn = document.createElement("button");
            viewBtn.type = "button";
            viewBtn.className = "fq-view-btn";
            viewBtn.textContent = "View";
            viewBtn.title = "Preview this file";
            viewBtn.onclick = function (e) {
              e.stopPropagation();
              preview(key, fiIdx);
            };
            actions.appendChild(viewBtn);
          }
          var rmBtn = document.createElement("button");
          rmBtn.type = "button";
          rmBtn.className = "fq-remove-btn";
          rmBtn.textContent = "Remove";
          rmBtn.title = "Remove this file";
          rmBtn.onclick = function (e) {
            e.stopPropagation();
            // FileQueue.remove is only exposed on the public API — calling the
            // bare name here throws ReferenceError and the file never deletes.
            SimpleModal.confirm("Remove this uploaded file?", {
              title: "Remove file",
              okText: "Yes, remove",
              danger: true,
            }).then(function (yes) {
              if (yes) FileQueue.remove(key, fiIdx);
            });
          };
          actions.appendChild(rmBtn);
          row.appendChild(ico);
          row.appendChild(nameWrap);
          row.appendChild(actions);
          container.appendChild(row);
          return;
        }

        var div = document.createElement("div");
        div.className = "file-queue-thumb";
        div.title = file.name;
        div.onclick = function () {
          preview(key, fiIdx);
        };
        if (file.type.startsWith("image/")) {
          var img = document.createElement("img");
          img.src = URL.createObjectURL(file);
          img.onload = function () {
            URL.revokeObjectURL(this.src);
          };
          div.appendChild(img);
        } else {
          var iconDiv = document.createElement("div");
          iconDiv.className = "fq-icon";
          iconDiv.innerHTML =
            file.type === "application/pdf"
              ? '<i class="fa-solid fa-file-pdf"></i>'
              : '<i class="fa-solid fa-file-word"></i>';
          div.appendChild(iconDiv);
        }
        var removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "fq-remove";
        removeBtn.innerHTML = "&times;";
        removeBtn.title = "Remove file";
        removeBtn.onclick = function (e) {
          e.stopPropagation();
          SimpleModal.confirm("Remove this uploaded file?", {
            title: "Remove file",
            okText: "Yes, remove",
            danger: true,
          }).then(function (yes) {
            if (yes) FileQueue.remove(key, fiIdx);
          });
        };
        div.appendChild(removeBtn);
        container.appendChild(div);
      })(fi);
    }
  }

  function preview(key, idx) {
    var q = queues[key];
    if (!q || idx >= q.files.length) return;
    var file = q.files[idx];
    var url = URL.createObjectURL(file);
    // Declared here — `width` was previously only assigned in the PDF branch,
    // so previewing an image threw "width is not defined" and nothing opened.
    var width = "90vw";
    var wrap = document.createElement("div");
    wrap.style.textAlign = "center";
    if (file.type.startsWith("image/")) {
      var img = document.createElement("img");
      img.src = url;
      img.style.cssText = "max-width:100%;max-height:70vh;border-radius:8px;";
      wrap.appendChild(img);
    } else if (file.type === "application/pdf") {
      width = "90vw";
      var frame = document.createElement("iframe");
      frame.src = url;
      frame.style.cssText = "width:100%;height:80vh;border:none;border-radius:8px;";
      wrap.appendChild(frame);
    } else {
      var iconDiv = document.createElement("div");
      iconDiv.innerHTML =
        '<i class="fa-solid fa-file-word" style="font-size:4rem;color:#1565c0;"></i>';
      var nameP = document.createElement("p");
      nameP.style.cssText = "margin-top:16px;font-weight:600;word-break:break-all;";
      nameP.textContent = file.name;
      var noteP = document.createElement("p");
      noteP.style.cssText = "margin-top:8px;color:#757575;font-size:0.85rem;";
      noteP.textContent = "Preview not available for this file type.";
      var dlBtn = document.createElement("button");
      dlBtn.type = "button";
      dlBtn.textContent = "Download File";
      dlBtn.style.cssText =
        "margin-top:12px;padding:8px 24px;background:#1b5e20;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:0.9rem;";
      dlBtn.onclick = function () {
        var a = document.createElement("a");
        a.href = url;
        a.download = file.name;
        a.click();
      };
      wrap.appendChild(iconDiv);
      wrap.appendChild(nameP);
      wrap.appendChild(noteP);
      wrap.appendChild(dlBtn);
    }
    var viewer = SimpleModal.open({ title: "File Preview", html: wrap, width: width });

    // Red close button pinned to the top-right corner of the modal card.
    // (viewer.el is the content body — the card itself is .sm-card.)
    var modalCard = viewer.el.closest(".sm-card") || viewer.el;
    modalCard.style.position = "relative";
    var closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.innerHTML = "&times;";
    closeBtn.title = "Close preview";
    closeBtn.style.cssText = "position:absolute;top:10px;right:12px;width:34px;height:34px;border:none;border-radius:50%;background:#e53935;color:#fff;font-size:20px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,0.3);z-index:5;";
    closeBtn.onmouseover = function () { closeBtn.style.background = "#c62828"; };
    closeBtn.onmouseout = function () { closeBtn.style.background = "#e53935"; };
    closeBtn.onclick = function () {
      URL.revokeObjectURL(url);
      viewer.close();
    };
    modalCard.appendChild(closeBtn);
  }

  return {
    init: function (key, opts) {
      if (queues[key]) return;
      queues[key] = {
        files: [],
        inputId: opts.inputId,
        containerId: opts.containerId,
        maxFiles: opts.maxFiles || 1,
        accept: opts.accept || "image/*,.pdf,.docx",
        mode: opts.mode || "thumbs",
        onChange: opts.onChange || null,
      };
    },

    handleInput: async function (key) {
      var q = queues[key];
      if (!q) return;
      var inputEl = document.getElementById(q.inputId);
      if (!inputEl || !inputEl.files) return;
      for (var fi = 0; fi < inputEl.files.length; fi++) {
        var file = inputEl.files[fi];
        if (q.maxFiles === 1) {
          q.files = [];
        }
        if (q.files.length >= q.maxFiles) {
          showToast("Maximum of " + q.maxFiles + " file(s).", true);
          break;
        }
        var dup = false;
        for (var di = 0; di < q.files.length; di++) {
          if (
            q.files[di].name === file.name &&
            q.files[di].size === file.size
          ) {
            dup = true;
            break;
          }
        }
        if (dup) continue;
        q.files.push(file);
      }
      inputEl.value = "";
      render(key);
      if (q.onChange) q.onChange(key, q.files);
    },

    remove: function (key, idx) {
      var q = queues[key];
      if (!q || idx >= q.files.length) return;
      q.files.splice(idx, 1);
      render(key);
      if (q.onChange) q.onChange(key, q.files);
    },

    preview: function (key, idx) {
      preview(key, idx);
    },

    getFiles: function (key) {
      var q = queues[key];
      return q ? q.files : [];
    },

    clear: function (key) {
      var q = queues[key];
      if (!q) return;
      q.files = [];
      render(key);
      if (q.onChange) q.onChange(key, q.files);
    },

    pushFiles: function (key, fileArray) {
      var q = queues[key];
      if (!q) return;
      for (var fi = 0; fi < fileArray.length; fi++) {
        q.files.push(fileArray[fi]);
      }
      render(key);
      if (q.onChange) q.onChange(key, q.files);
    },
  };
})();
