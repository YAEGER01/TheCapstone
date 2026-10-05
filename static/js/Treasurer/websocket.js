(function () {
  "use strict";

  var WS_TOKEN = window.WS_AUTH_TOKEN || "";
  var WS_URL = (window.location.protocol === "https:" ? "wss://" : "ws://") + window.location.host + "/ws/treasurer-dashboard/" + (WS_TOKEN ? "?token=" + encodeURIComponent(WS_TOKEN) : "");
  var ws = null;
  var wsReconnectTimer = null;
  var pollTimer = null;
  var POLL_INTERVAL_MS = 20000;

  // Polling fallback: when the WebSocket can't connect (e.g. shared cPanel
  // has no ASGI server), refresh the whole dashboard periodically instead.
  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(function () {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        refreshSection("all");
      }
    }, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
    try {
      ws = new WebSocket(WS_URL);
    } catch (e) {
      scheduleReconnect();
      return;
    }
    ws.onmessage = function (event) {
      try {
        var msg = JSON.parse(event.data);
        handleWsMessage(msg);
      } catch (e) {}
    };
    ws.onclose = function () {
      scheduleReconnect();
    };
    ws.onerror = function () {
      ws.close();
    };
  }

  function scheduleReconnect() {
    if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
    wsReconnectTimer = setTimeout(connectWebSocket, 5000);
  }

  function handleWsMessage(msg) {
    if (msg.type === "ping" || msg.type === "pong" || msg.type === "connection_established") return;
    if (msg.type === "fund_updated") {
      // ISUCauFA, Inc. fund changed elsewhere (approval, release, fee, ...) —
      // refresh the fund card / overview / ledger live, no manual refresh.
      if (typeof window.nxFundRefreshAll === "function") window.nxFundRefreshAll();
      return;
    }
    if (msg.type === "notification_created") {
      // Live in-app/push notification landed — nudge the bell dots and the
      // notifications panel so the Treasurer sees it without a manual refresh.
      if (typeof window.nxUpdateNavbarNotifDots === "function") window.nxUpdateNavbarNotifDots();
      if (typeof window.nxRefreshNotifications === "function") window.nxRefreshNotifications();
      showForegroundNotification(msg.notification || {});
      return;
    }
    if (msg.type === "data_changed") {
      var section = msg.section || "all";
      refreshSection(section);
    }
  }

  function refreshSection(section) {
    if (section === "all" || section === "members") {
      if (typeof refreshEnrolledTableIfChanged === "function") {
        refreshEnrolledTableIfChanged();
      }
      if (typeof fetchMemberBreakdown === "function") {
        fetchMemberBreakdown();
      }
      if (typeof renderMembersFromBackend === "function") {
        renderMembersFromBackend();
      }
    }
    if (section === "all" || section === "membership_fees") {
      if (typeof renderFeesTable === "function") {
        renderFeesTable();
      }
      if (typeof fetchMembershipFeeTotal === "function") {
        fetchMembershipFeeTotal();
      }
    }
    if (section === "all" || section === "monthly_dues") {
      if (typeof fetchAndRenderOtc === "function") {
        fetchAndRenderOtc();
      }
      if (typeof fetchSalaryHistory === "function") {
        fetchSalaryHistory();
      }
    }
    if (section === "all" || section === "aids") {
      if (typeof bootMedicalAidTable === "function") {
        bootMedicalAidTable();
      }
      if (typeof bootDeathAidTable === "function") {
        bootDeathAidTable();
      }
      if (window.AidTracking && typeof window.AidTracking.loadPosts === "function") {
        window.AidTracking.loadPosts();
      }
      if (window.AidTracking && typeof window.AidTracking.loadHistoryPosts === "function") {
        window.AidTracking.loadHistoryPosts();
      }
    }
    if (section === "all" || section === "returned_entries") {
      if (window.__refreshReturnedEntries) {
        window.__refreshReturnedEntries();
      }
      if (window.__refreshReturnedMonthlyDues) {
        window.__refreshReturnedMonthlyDues();
      }
    }
    if (section === "all" || section === "releases") {
      if (typeof fetchReleases === "function") {
        fetchReleases();
      }
      if (typeof fetchApprovedTransactionsTotal === "function") {
        fetchApprovedTransactionsTotal();
      }
    }
    if (section === "all" || section === "registration") {
      if (typeof fetchRegistrationRequests === "function") {
        fetchRegistrationRequests();
      }
      if (typeof fetchMemberBreakdown === "function") {
        fetchMemberBreakdown();
      }
      if (typeof fetchMembershipFeeTotal === "function") {
        fetchMembershipFeeTotal();
      }
    }
    if (section === "all" || section === "financial") {
      if (typeof fetchFinancialPendingCounts === "function") {
        fetchFinancialPendingCounts();
      }
    }
  }

  function showForegroundNotification(n) {
    // SW pushes only surface while the tab is unfocused — show one immediately
    // when a notification arrives in a visible, focused dashboard.
    if (document.visibilityState !== "visible" || !("Notification" in window) || Notification.permission !== "granted") return;
    try {
      var fg = new Notification(n.sender_role ? (n.sender_role + " · ISUCauFA, Inc.") : "ISUCauFA, Inc. Notification", {
        body: n.message || "You have a new notification.",
        icon: "/static/img/isu_caufa_official_192.png",
        tag: "caufa-live",
      });
      fg.onclick = function () { window.focus(); this.close(); };
    } catch (e) {}
  }

  document.addEventListener("turbo:load", function () {
    connectWebSocket();
    startPolling();
  });
  document.addEventListener("turbo:before-cache", function () {
    if (ws) { ws.onclose = null; ws.close(); ws = null; }
    if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
    stopPolling();
  });
})();
