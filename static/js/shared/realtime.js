// realtime.js — central realtime service for ISUCauFA dashboards.
//
// One shared WebSocket per channel (auditor / treasurer / president /
// member) with:
//   * token auth (?token=, same convention as the per-dashboard sockets),
//   * ping/pong heartbeat with stale-connection watchdog,
//   * exponential-backoff reconnect,
//   * a 5-second auto-update polling fallback that runs only while the
//     socket is down, so pages stay fresh without a manual refresh even
//     where no ASGI server is available (e.g. plain WSGI hosting).
//
// Usage:
//   var off = window.CaufaRealtime.subscribe({
//     channel: "treasurer",              // socket group, one connection each
//     path: "/ws/treasurer-dashboard/",  // ws endpoint for the channel
//     event: "fund_updated",             // message type to listen for...
//     events: ["fund_updated"],          // ...or several types at once
//     onEvent: function (msg) { ... },   // fired on each matching WS message
//     poll: function () { ... },         // 5s fallback refresh while WS down
//     pollIntervalMs: 5000,              // fallback cadence (default 5000)
//     pollWhenHidden: false,             // poll even when the tab is hidden
//     resyncOnReconnect: true,           // run poll() once after reconnect
//     onStatusChange: function (s) { },  // "connecting" | "live" | "fallback"
//   });
//   off(); // unsubscribe (socket closes when the last subscriber leaves)
(function () {
  "use strict";

  var DEFAULT_POLL_MS = 5000;
  var RECONNECT_MIN_MS = 2000;
  var RECONNECT_MAX_MS = 30000;
  var HEARTBEAT_MS = 25000;
  var PONG_TIMEOUT_MS = 10000;

  var channels = {}; // name -> channel record

  function wsUrl(path) {
    var proto = window.location.protocol === "https:" ? "wss://" : "ws://";
    var token = window.WS_AUTH_TOKEN || window.MEMBER_WS_TOKEN || "";
    return proto + window.location.host + path + (token ? "?token=" + encodeURIComponent(token) : "");
  }

  function setStatus(ch, status) {
    if (!ch || ch.status === status) return;
    ch.status = status;
    (ch.subs || []).forEach(function (sub) {
      try { if (typeof sub.onStatusChange === "function") sub.onStatusChange(status); } catch (e) {}
    });
  }

  function socketOpen(ch) {
    return !!(ch.socket && ch.socket.readyState === 1);
  }

  function ensureChannel(name, path) {
    var ch = channels[name];
    if (!ch) {
      ch = channels[name] = {
        name: name,
        path: path,
        socket: null,
        status: "connecting",
        subs: [],
        reconnectTimer: null,
        reconnectDelay: RECONNECT_MIN_MS,
        heartbeatTimer: null,
        watchdogTimer: null,
        fallbackTimer: null,
        lastPong: 0,
      };
    }
    return ch;
  }

  function subEvents(sub) {
    if (sub.events) return sub.events;
    if (sub.event) return [sub.event];
    return ["*"];
  }

  function routeMessage(ch, msg) {
    if (!msg || typeof msg !== "object") return;
    if (msg.type === "pong") {
      ch.lastPong = Date.now();
      return;
    }
    if (msg.type === "ping" || msg.type === "connection_established") return;
    (ch.subs || []).forEach(function (sub) {
      var evts = subEvents(sub);
      if (evts.indexOf("*") === -1 && evts.indexOf(msg.type) === -1) return;
      try { sub.onEvent(msg); } catch (e) {}
    });
  }

  function startHeartbeat(ch) {
    stopHeartbeat(ch);
    ch.lastPong = Date.now();
    ch.heartbeatTimer = setInterval(function () {
      if (!socketOpen(ch)) return;
      try { ch.socket.send(JSON.stringify({ type: "ping" })); } catch (e) {}
      // Watchdog: no pong within the window means a dead socket.
      if (ch.watchdogTimer) clearTimeout(ch.watchdogTimer);
      ch.watchdogTimer = setTimeout(function () {
        if (Date.now() - ch.lastPong > HEARTBEAT_MS + PONG_TIMEOUT_MS) {
          try { ch.socket.close(); } catch (e) {}
        }
      }, PONG_TIMEOUT_MS);
    }, HEARTBEAT_MS);
  }

  function stopHeartbeat(ch) {
    if (ch.heartbeatTimer) { clearInterval(ch.heartbeatTimer); ch.heartbeatTimer = null; }
    if (ch.watchdogTimer) { clearTimeout(ch.watchdogTimer); ch.watchdogTimer = null; }
  }

  function pollIntervalFor(ch) {
    var ms = DEFAULT_POLL_MS;
    (ch.subs || []).forEach(function (sub) {
      if (sub.pollIntervalMs && sub.pollIntervalMs > 0) ms = Math.min(ms, sub.pollIntervalMs);
    });
    return ms;
  }

  // 5-second auto-update fallback: while the socket is down, each
  // subscriber's poll() runs on this cadence so the view still refreshes
  // with no manual reload. Paused while the tab is hidden unless the
  // subscriber opts into background polling.
  function startFallback(ch) {
    stopFallback(ch);
    ch.fallbackTimer = setInterval(function () {
      if (socketOpen(ch)) return;
      if (document.visibilityState === "hidden") {
        var anyBackground = (ch.subs || []).some(function (s) { return s.pollWhenHidden; });
        if (!anyBackground) return;
      }
      (ch.subs || []).slice().forEach(function (sub) {
        if (typeof sub.poll !== "function") return;
        if (document.visibilityState === "hidden" && !sub.pollWhenHidden) return;
        try { sub.poll(); } catch (e) {}
      });
    }, pollIntervalFor(ch));
  }

  function stopFallback(ch) {
    if (ch.fallbackTimer) { clearInterval(ch.fallbackTimer); ch.fallbackTimer = null; }
  }

  function scheduleReconnect(ch) {
    if (ch.reconnectTimer || !(ch.subs || []).length) return;
    var delay = ch.reconnectDelay;
    ch.reconnectDelay = Math.min(ch.reconnectDelay * 2, RECONNECT_MAX_MS);
    ch.reconnectTimer = setTimeout(function () {
      ch.reconnectTimer = null;
      connect(ch);
    }, delay + Math.floor(Math.random() * 1000));
  }

  function connect(ch) {
    if (typeof window.WebSocket === "undefined") {
      setStatus(ch, "fallback");
      return;
    }
    if (ch.socket && (ch.socket.readyState === 0 || ch.socket.readyState === 1)) return;
    setStatus(ch, "connecting");
    var socket;
    try {
      socket = new WebSocket(wsUrl(ch.path));
    } catch (e) {
      setStatus(ch, "fallback");
      scheduleReconnect(ch);
      return;
    }
    ch.socket = socket;
    socket.onopen = function () {
      ch.reconnectDelay = RECONNECT_MIN_MS;
      setStatus(ch, "live");
      startHeartbeat(ch);
      // Catch-up resync: pull once so nothing changed while offline is missed.
      (ch.subs || []).slice().forEach(function (sub) {
        if (sub.resyncOnReconnect === false || typeof sub.poll !== "function") return;
        try { sub.poll(); } catch (e) {}
      });
    };
    socket.onmessage = function (event) {
      var msg = null;
      try { msg = JSON.parse(event.data); } catch (e) { return; }
      routeMessage(ch, msg);
    };
    socket.onclose = function () {
      stopHeartbeat(ch);
      if (ch.socket === socket) ch.socket = null;
      setStatus(ch, "fallback");
      scheduleReconnect(ch);
    };
    socket.onerror = function () {
      try { socket.close(); } catch (e) {}
    };
  }

  function subscribe(opts) {
    opts = opts || {};
    if (!opts.channel || !opts.path) return function () {};
    var ch = ensureChannel(opts.channel, opts.path);
    var sub = {
      event: opts.event || "*",
      events: Array.isArray(opts.events) ? opts.events.slice() : null,
      onEvent: opts.onEvent,
      poll: opts.poll,
      pollIntervalMs: opts.pollIntervalMs || DEFAULT_POLL_MS,
      pollWhenHidden: !!opts.pollWhenHidden,
      resyncOnReconnect: opts.resyncOnReconnect !== false,
      onStatusChange: opts.onStatusChange,
    };
    ch.subs.push(sub);
    // Restart the fallback cadence in case a tighter interval joined.
    startFallback(ch);
    try { sub.onStatusChange(ch.status); } catch (e) {}
    connect(ch);

    var off = function () {
      var idx = ch.subs.indexOf(sub);
      if (idx !== -1) ch.subs.splice(idx, 1);
      if (!ch.subs.length) {
        if (ch.reconnectTimer) { clearTimeout(ch.reconnectTimer); ch.reconnectTimer = null; }
        stopHeartbeat(ch);
        stopFallback(ch);
        if (ch.socket) { try { ch.socket.close(); } catch (e) {} ch.socket = null; }
        delete channels[ch.name];
      } else {
        startFallback(ch);
      }
    };
    return off;
  }

  function getStatus(channel) {
    var ch = channels[channel];
    return ch ? ch.status : "fallback";
  }

  function isLive(channel) {
    return getStatus(channel) === "live";
  }

  // Tab visible again: reconnect now if down, and let the fallback tick
  // (or the resync) pull fresh data immediately.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState !== "visible") return;
    Object.keys(channels).forEach(function (name) {
      var ch = channels[name];
      if (!socketOpen(ch)) {
        if (ch.reconnectTimer) { clearTimeout(ch.reconnectTimer); ch.reconnectTimer = null; }
        ch.reconnectDelay = RECONNECT_MIN_MS;
        connect(ch);
      }
    });
  });
  window.addEventListener("online", function () {
    Object.keys(channels).forEach(function (name) {
      var ch = channels[name];
      if (!socketOpen(ch)) {
        if (ch.reconnectTimer) { clearTimeout(ch.reconnectTimer); ch.reconnectTimer = null; }
        ch.reconnectDelay = RECONNECT_MIN_MS;
        connect(ch);
      }
    });
  });

  window.CaufaRealtime = {
    subscribe: subscribe,
    getStatus: getStatus,
    isLive: isLive,
    DEFAULT_POLL_MS: DEFAULT_POLL_MS,
  };
})();
