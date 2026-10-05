(function () {
  "use strict";

  var VAPID_PUBLIC_KEY = window.VAPID_PUBLIC_KEY || null;

  // Web Push works on any secure context: localhost, an ngrok HTTPS tunnel, or
  // the live domain. We no longer restrict by host — the subscription records
  // its own origin so delivery and links work wherever you opened the app.
  var currentHost = (window.location.hostname || "").toLowerCase();
  var IS_SECURE =
    !!window.isSecureContext || currentHost === "localhost" || currentHost === "127.0.0.1";

  // Detect recipient type from page (member vs officer)
  var RECIPIENT_TYPE = (window.PUSH_RECIPIENT_TYPE || "officer").toLowerCase();
  var IS_MEMBER = RECIPIENT_TYPE === "member";

  // The bell always has a working handler, so a click never fails silently.
  // Prefer the dashboard's toast; fall back to the console.
  function notifyUser(message, isError) {
    if (typeof window.showToast === "function") {
      try {
        window.showToast(message, !!isError);
        return;
      } catch (e) {}
    }
    console[isError ? "warn" : "log"]("[push] " + message);
  }

  var state = {
    swRegistration: null,
    subscribed: false,
    denied: false,
  };

  function urlBase64ToUint8Array(base64String) {
    var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    var rawData = atob(base64);
    var output = new Uint8Array(rawData.length);
    for (var i = 0; i < rawData.length; ++i) {
      output[i] = rawData.charCodeAt(i);
    }
    return output;
  }

  function getCsrfToken() {
    var el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  var WELCOME_COOLDOWN_MS = 24 * 60 * 60 * 1000; // 24 hours

  function getMemberName() {
    var el = document.querySelector(".user-name, .side-user-name, .profile-name");
    if (el && el.textContent.trim()) {
      return el.textContent.trim().split(" ")[0];
    }
    return "User";
  }

  function getOfficerFirstName() {
    var el = document.querySelector(".user-name");
    if (el && el.textContent.trim()) {
      return el.textContent.trim().split(" ")[0];
    }
    return "User";
  }

  function getDashboardUrl() {
    var el = document.querySelector(".user-role");
    if (!el) return "/";
    var role = (el.textContent || "").trim().toLowerCase();
    if (role.indexOf("treasurer") !== -1) return "/treasurer/";
    if (role.indexOf("auditor") !== -1) return "/auditor/";
    if (role.indexOf("president") !== -1) return "/president/";
    return "/member/";
  }

  function showWelcomeNotification() {
    if (Notification.permission !== "granted") return;
    try {
      var last = localStorage.getItem("caufa_welcomed_ts");
      if (last && Date.now() - parseInt(last, 10) < WELCOME_COOLDOWN_MS) return;
      localStorage.setItem("caufa_welcomed_ts", String(Date.now()));
    } catch (e) {}
    var name = IS_MEMBER ? getMemberName() : getOfficerFirstName();
    var url = getDashboardUrl();
    var notif = new Notification("Hello " + name + "!", {
      body: IS_MEMBER ? "Welcome to your ISUCauFA Member Dashboard" : "Welcome to the CAUFA Dashboard",
      icon: "/static/img/isu_caufa_official_192.png",
      badge: "/static/img/isu_caufa_official_badge.png",
      vibrate: [200, 100, 200],
    });
    notif.onclick = function () {
      window.focus();
      this.close();
      if (url) window.location.href = url;
    };
  }

  function updateBellIcon() {
    var bell = document.getElementById("notifBellBtn");
    if (bell) {
      var icon = bell.querySelector("i");
      // Preserve each dashboard's authored classes and only toggle our state,
      // so the bell keeps its layout on every dashboard.
      bell.classList.remove("subscribed", "denied");
      if (state.subscribed) {
        bell.classList.add("subscribed");
        if (icon) icon.className = "fa-solid fa-bell";
        bell.title = "Push notifications enabled on this device";
      } else if (state.denied) {
        bell.classList.add("denied");
        if (icon) icon.className = "fa-solid fa-bell-slash";
        bell.title = "Notifications blocked — update browser settings";
      } else {
        if (icon) icon.className = "fa-regular fa-bell";
        bell.title = "Enable push notifications";
      }
    }
    if (window.PUSH_CONFIG && typeof window.PUSH_CONFIG.onStateChange === "function") {
      try {
        window.PUSH_CONFIG.onStateChange(state);
      } catch (e) {}
    }
  }

  function setSubscribedState(subscribed, denied) {
    state.subscribed = subscribed;
    state.denied = !!denied;
    updateBellIcon();
  }

  // Only ever called from an explicit user action (bell click), because
  // pushManager.subscribe() triggers the browser permission prompt when
  // permission is still "default".
  function subscribeUser(registration) {
    if (!registration) return Promise.reject(new Error("No service worker"));

    return registration.pushManager
      .subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
      })
      .then(function (subscription) {
        var subJson = subscription.toJSON();
        return fetch("/api/push/subscribe/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken(),
          },
          body: JSON.stringify({
            endpoint: subJson.endpoint,
            keys: subJson.keys,
            recipient_type: RECIPIENT_TYPE,
          }),
        })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              return {};
            })
            .then(function (data) {
              // Green means the backend actually saved this device.
              if (!response.ok || !data.ok) {
                setSubscribedState(false, false);
                throw new Error(data.error || "Subscription could not be saved");
              }
              setSubscribedState(true, false);
              showWelcomeNotification();
              return true;
            });
        })
        .catch(function (error) {
          console.error("Push subscription failed:", error);
          setSubscribedState(false, Notification.permission === "denied");
          notifyUser((error && error.message) || "Could not enable notifications on this device.", true);
          throw error;
        });
      });
  }

  // On load we only *read* the current state. We never subscribe or prompt here.
  function refreshSubscriptionState(registration) {
    registration.pushManager
      .getSubscription()
      .then(function (subscription) {
        var permission = "Notification" in window ? Notification.permission : "denied";

        if (permission === "denied") {
          setSubscribedState(false, true);
          return;
        }
        if (!subscription || permission !== "granted") {
          setSubscribedState(false, false);
          return;
        }

        var subJson = subscription.toJSON();
        return fetch("/api/push/validate-subscription/", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrfToken(),
          },
          body: JSON.stringify({
            endpoint: subJson.endpoint,
            recipient_type: RECIPIENT_TYPE,
          }),
        })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              return { valid: false };
            })
            .then(function (data) {
              setSubscribedState(!!(response.ok && data.valid), false);
            });
        })
        .catch(function () {
          setSubscribedState(false, false);
        });
      })
      .catch(function () {
        setSubscribedState(false, false);
      });
  }

  function requestPermission() {
    // Explicit user action — tell the user why, never fail silently.
    if (!VAPID_PUBLIC_KEY) {
      notifyUser("Push notifications are not configured on the server yet.", true);
      return;
    }
    if (!IS_SECURE) {
      notifyUser(
        "Notifications need a secure (HTTPS) connection. Open the site over HTTPS or localhost.",
        true
      );
      return;
    }
    if (!("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
      notifyUser("This browser does not support push notifications.", true);
      return;
    }

    // Explicit user action — safe to ask the browser here.
    function doRequest() {
      if (!("Notification" in window)) {
        notifyUser("This browser does not support push notifications.", true);
        return;
      }

      if (Notification.permission === "granted") {
        navigator.serviceWorker.ready.then(function (registration) {
          state.swRegistration = registration;
          subscribeUser(registration).catch(function () {});
        }).catch(function () {});
        return;
      }
      if (Notification.permission === "denied") {
        setSubscribedState(false, true);
        notifyUser("Notifications are blocked for this site in your browser settings.", true);
        return;
      }
      Notification.requestPermission()
        .then(function (permission) {
          if (permission === "granted") {
            return subscribeUser(state.swRegistration);
          }
          setSubscribedState(false, permission === "denied");
          if (permission === "denied") {
            notifyUser("Notifications are blocked for this site in your browser settings.", true);
          }
        })
        .catch(function () {});
    }

    if (!state.swRegistration) {
      navigator.serviceWorker
        .register("/sw.js", { updateViaCache: "none" })
        .then(function (reg) {
          return reg.update().catch(function () {}).then(function () {
            return navigator.serviceWorker.ready;
          });
        })
        .then(function (reg) {
          state.swRegistration = reg;
          doRequest();
        })
        .catch(function (error) {
          console.error("Service Worker registration failed:", error);
          notifyUser("Could not set up notifications on this device.", true);
        });
    } else {
      doRequest();
    }
  }

  window.requestPushPermission = requestPermission;

  // PWA Install Prompt Handling
  var deferredInstallPrompt = null;
  var isStandalone = (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) || window.navigator.standalone === true;

  function isIos() {
    var ua = window.navigator.userAgent || "";
    if (/iphone|ipad|ipod/i.test(ua)) return true;
    return window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1;
  }

  function showInstallBanner() {
    var banner = document.getElementById("installBanner");
    if (banner) banner.hidden = false;
  }

  function hideInstallBanner() {
    var banner = document.getElementById("installBanner");
    if (banner) banner.hidden = true;
  }

  function showIosHint() {
    var hint = document.getElementById("iosPushHint");
    if (hint && isIos() && !isStandalone) {
      hint.style.display = "";
    }
  }

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredInstallPrompt = event;
    if (!isStandalone) showInstallBanner();
  });

  window.addEventListener("appinstalled", function () {
    deferredInstallPrompt = null;
    hideInstallBanner();
  });

  // Expose install function for manual button clicks
  window.installPwa = function () {
    if (deferredInstallPrompt) {
      deferredInstallPrompt.prompt();
      deferredInstallPrompt.userChoice.then(function (choice) {
        if (choice && choice.outcome === "accepted") {
          toast("ISUCauFA installed.");
        }
        deferredInstallPrompt = null;
      });
    } else if (isIos()) {
      showIosHint();
    } else {
      showInstallBanner();
    }
  };

  if (
    VAPID_PUBLIC_KEY &&
    IS_SECURE &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window &&
    !window.PUSH_DELEGATE_TO_PAGE
  ) {
    navigator.serviceWorker
      .register("/sw.js", { updateViaCache: "none" })
      .then(function (registration) {
        return registration.update().catch(function () {}).then(function () {
          return navigator.serviceWorker.ready;
        });
      })
      .then(function (registration) {
        state.swRegistration = registration;
        refreshSubscriptionState(registration);
      })
      .catch(function (error) {
        console.error("Service Worker registration failed:", error);
      });
  }

  // Expose for debugging
  window.__pushInit = {
    subscribe: subscribeUser,
    refresh: refreshSubscriptionState,
    state: state,
    installPwa: window.installPwa,
  };
})();