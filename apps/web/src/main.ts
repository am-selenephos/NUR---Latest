import { bootstrapV197Bridge } from "./bridge/v197Bridge";
import { installV197Diagnostics } from "./bridge/v197Diagnose";

installV197Diagnostics();

void bootstrapV197Bridge().catch(error => {
  // The bridge is intentionally nonvisual. Leave the canonical V197 entry intact
  // if a read-only API hydration cannot start.
  console.error("NUR V197 bridge did not start", error);
});

if ("serviceWorker" in navigator && (window.isSecureContext || window.location.hostname === "localhost")) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/service-worker.js", { scope: "/" }).catch(error => {
      console.warn("NUR offline shell registration failed", error);
    });
  }, { once: true });
}
