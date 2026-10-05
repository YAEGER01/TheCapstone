// url_obf.js — transparent URL obfuscation signer for dashboard pages.
//
// - Reads the per-session HMAC subkey from <meta name="url-obf-key">.
// - Patches window.fetch so every same-origin request carrying a query
//   string gets a tamper-proof `_s` signature appended (server verifies in
//   UrlObfuscationMiddleware; edited URLs get the branded 404).
// - Canonicalization MUST match core_system/url_obfuscation.py exactly:
//   path + "?" + sorted(k,v excluding _s/_/t/v), quote_plus encoding,
//   HMAC-SHA256, urlsafe-base64 without padding.
// - window.U(url) — async helper returning the signed URL for manual use.
// - UrlObf.sessionExpiredUrl() — obfuscated /?x=... link for JS-driven
//   session-death redirects (falls back to plain on failure).
//
// Must load WITHOUT defer (before other dashboard scripts) so the fetch
// patch is installed first.
(function () {
  "use strict";

  var SIG_PARAM = "_s";
  var ENVELOPE_PARAM = "x";
  var IGNORED = { _: 1, t: 1, v: 1 };
  var EXEMPT_PREFIXES = [
    "/admin/", "/static/", "/media/", "/sw.js", "/favicon.ico",
    "/__reload__/", "/api/url/", "/api/public/", "/api/push/", "/register/",
  ];

  function sessionKey() {
    try {
      var m = document.querySelector('meta[name="url-obf-key"]');
      var k = m && m.getAttribute("content");
      return k || "";
    } catch (e) {
      return "";
    }
  }

  // Python urllib quote_plus: alphanumerics + _.-~ stay, space -> +, all
  // else %XX uppercase. encodeURIComponent leaves !~*'() unescaped, so fix
  // those (except ~) plus space handling.
  function pyQuotePlus(s) {
    return encodeURIComponent(s)
      .replace(/%20/g, "+")
      .replace(/[!'()*]/g, function (c) {
        return "%" + c.charCodeAt(0).toString(16).toUpperCase();
      });
  }

  function canonical(path, pairs) {
    var kept = pairs.filter(function (p) {
      return p[0] !== SIG_PARAM && !IGNORED[p[0]];
    });
    kept.sort(function (a, b) {
      if (a[0] < b[0]) return -1;
      if (a[0] > b[0]) return 1;
      if (a[1] < b[1]) return -1;
      if (a[1] > b[1]) return 1;
      return 0;
    });
    return path + "?" + kept.map(function (p) {
      return pyQuotePlus(p[0]) + "=" + pyQuotePlus(p[1]);
    }).join("&");
  }

  function b64UrlNoPad(bytes) {
    var bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  var cryptoKeyPromise = null;
  function importKey(raw) {
    if (cryptoKeyPromise) return cryptoKeyPromise;
    cryptoKeyPromise = (async function () {
      if (!raw || !window.crypto || !crypto.subtle) return null;
      try {
        var enc = new TextEncoder().encode(raw);
        return await crypto.subtle.importKey("raw", enc, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
      } catch (e) {
        return null;
      }
    })();
    return cryptoKeyPromise;
  }

  async function computeSig(path, pairs) {
    var raw = sessionKey();
    if (!raw) return "";
    var ck = await importKey(raw);
    if (!ck) return "";
    try {
      var msg = new TextEncoder().encode(canonical(path, pairs));
      var sig = await crypto.subtle.sign("HMAC", ck, msg);
      return b64UrlNoPad(new Uint8Array(sig));
    } catch (e) {
      return "";
    }
  }

  function sameOrigin(url) {
    try {
      var u = new URL(url, window.location.href);
      return u.protocol.indexOf("http") === 0 && u.origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  function exemptPath(path) {
    for (var i = 0; i < EXEMPT_PREFIXES.length; i++) {
      if (path.indexOf(EXEMPT_PREFIXES[i]) === 0) return true;
    }
    return false;
  }

  function splitPairs(search) {
    var out = [];
    var q = (search || "").replace(/^\?/, "");
    if (!q) return out;
    q.split("&").forEach(function (part) {
      if (!part) return;
      var eq = part.indexOf("=");
      var k, v;
      if (eq === -1) { k = part; v = ""; }
      else { k = part.slice(0, eq); v = part.slice(eq + 1); }
      try { k = decodeURIComponent(k.replace(/\+/g, " ")); } catch (e) {}
      try { v = decodeURIComponent(v.replace(/\+/g, " ")); } catch (e) {}
      out.push([k, v]);
    });
    return out;
  }

  // Async signed-URL builder. Returns the input unchanged when signing is
  // impossible (no key, cross-origin, exempt, already signed).
  async function signUrl(input) {
    try {
      if (typeof input !== "string") return input;
      if (!sameOrigin(input)) return input;
      var u = new URL(input, window.location.href);
      if (exemptPath(u.pathname)) return input;
      var pairs = splitPairs(u.search);
      if (!pairs.length) return input;
      var hasSig = pairs.some(function (p) { return p[0] === SIG_PARAM || p[0] === ENVELOPE_PARAM; });
      if (hasSig) return input;
      var sig = await computeSig(u.pathname, pairs);
      if (!sig) return input;
      pairs.push([SIG_PARAM, sig]);
      u.search = "?" + pairs.map(function (p) {
        return pyQuotePlus(p[0]) + "=" + pyQuotePlus(p[1]);
      }).join("&");
      // Preserve relative form callers used.
      var out = u.pathname + u.search + u.hash;
      if (/^https?:\/\//i.test(input)) return u.toString();
      return out;
    } catch (e) {
      return input;
    }
  }

  // Transparent fetch patch: sign same-origin query-bearing URLs on the fly.
  if (window.fetch && !window.fetch.__urlObfPatched) {
    var nativeFetch = window.fetch.bind(window);
    var patched = function (input, init) {
      try {
        var raw = typeof input === "string" ? input : (input && input.url) || "";
        if (typeof raw === "string" && sameOrigin(raw)) {
          var probe = new URL(raw, window.location.href);
          if (!exemptPath(probe.pathname) && probe.search && probe.search.length > 1) {
            var hasTok = /(?:^|[&?])(?:_s|x)=/.test(probe.search);
            if (!hasTok && sessionKey()) {
              return signUrl(raw).then(function (signed) {
                if (input && typeof input !== "string" && input.url) {
                  input = new Request(signed, input);
                } else {
                  input = signed;
                }
                return nativeFetch(input, init);
              });
            }
          }
        }
      } catch (e) { /* fall through unsigned */ }
      return nativeFetch(input, init);
    };
    patched.__urlObfPatched = true;
    window.fetch = patched;
  }

  window.U = signUrl;
  window.UrlObf = {
    signUrl: signUrl,
    sessionExpiredUrl: async function () {
      try {
        var res = await window.fetch("/api/url/session-expired/", { credentials: "same-origin" });
        var data = await res.json();
        if (data && data.url) return data.url;
      } catch (e) {}
      return "/?session_expired=1";
    },
    goSessionExpired: async function () {
      window.location.href = await window.UrlObf.sessionExpiredUrl();
    },
  };
})();
