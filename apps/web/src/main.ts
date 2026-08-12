import { bootstrapV197Bridge } from "./bridge/v197Bridge";
import { installV197Diagnostics } from "./bridge/v197Diagnose";

void bootstrapV197Bridge()
  .catch(error => {
    // The bridge is intentionally nonvisual. Leave the canonical V197 entry intact
    // if a read-only API hydration cannot start.
    console.error("NUR V197 bridge did not start", error);
  })
  .finally(() => {
    // The bridge owns the host body mount. Diagnostics must attach afterwards
    // or that mount removes the opt-in panel before it can report the live rig.
    installV197Diagnostics();
  });

if ("serviceWorker" in navigator) {
  if (import.meta.env.DEV) {
    const reloadKey = "nur-v197-dev-service-worker-cleared";
    window.addEventListener("load", () => {
      const wasControlled = navigator.serviceWorker.controller !== null;
      void Promise.all([
        navigator.serviceWorker.getRegistrations()
          .then(registrations => Promise.all(registrations.map(registration => registration.unregister()))),
        "caches" in window
          ? window.caches.keys().then(keys => Promise.all(
            keys
              .filter(key => key.startsWith("nur-v197-shell-"))
              .map(key => window.caches.delete(key)),
          ))
          : Promise.resolve([]),
      ]).then(() => {
        if (wasControlled && window.sessionStorage.getItem(reloadKey) !== "true") {
          window.sessionStorage.setItem(reloadKey, "true");
          window.location.reload();
          return;
        }
        window.sessionStorage.removeItem(reloadKey);
      }).catch(error => {
        console.warn("NUR local cache cleanup failed", error);
      });
    }, { once: true });
  } else if (window.isSecureContext) {
    window.addEventListener("load", () => {
      void navigator.serviceWorker.register("/service-worker.js", { scope: "/" })
        .then(registration => registration?.update())
        .catch(error => {
          console.warn("NUR offline shell registration failed", error);
        });
    }, { once: true });
  }
}
