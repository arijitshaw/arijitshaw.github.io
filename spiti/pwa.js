// Shared by every page under spiti/: registers the offline service worker, shows how much of the
// site is saved for offline use, offers "Install app" and an "Update" prompt, and marks links that
// need signal when the phone is offline.
// Elements can opt in with data attributes:
//   data-pwa-install   click -> install prompt (hidden when already installed)
//   data-pwa-update    click -> check for updates now
//   data-pwa-version   filled with the saved version
//   data-pwa-status    filled with the offline-saving status (progress, size, or a failure)
(() => {
  const script = document.currentScript;
  const MB = n => (n / 1048576).toFixed(1) + " MB";
  const setAll = (sel, text) => document.querySelectorAll(sel).forEach(el => { el.textContent = text; });

  // ---- toast ----
  let toastEl, toastTimer;
  function toast(text, action, ms) {
    if (!toastEl) {
      const style = document.createElement("style");
      style.textContent = `
.pwa-toast{position:fixed;left:50%;bottom:calc(16px + env(safe-area-inset-bottom));z-index:1000;display:flex;align-items:center;gap:10px;
  max-width:calc(100vw - 32px);width:max-content;padding:8px 8px 8px 18px;border-radius:999px;background:#201f1d;color:#f3f2f2;
  font:400 14.5px/1.35 "Lora",Georgia,serif;box-shadow:0 10px 30px rgba(0,0,0,.3);
  transform:translate(-50%,calc(100% + 40px));transition:transform .3s ease}
.pwa-toast.show{transform:translate(-50%,0)}
.pwa-toast span{padding:6px 0}
.pwa-toast button{flex:none;appearance:none;border:0;border-radius:999px;padding:10px 14px;min-height:40px;cursor:pointer;
  font:600 14px/1 "Lora",Georgia,serif;background:#e6bb78;color:#201f1d}
.pwa-toast button.x{background:transparent;color:#f3f2f2;padding:8px 12px;font-size:16px}
.is-offline a.needs-signal{opacity:.6}
.is-offline a.needs-signal::after{content:" · needs signal";font-size:.78em;font-style:italic;white-space:nowrap}
@media (prefers-reduced-motion:reduce){.pwa-toast{transition:none}}`;
      document.head.appendChild(style);
      toastEl = document.createElement("div");
      toastEl.className = "pwa-toast";
      toastEl.setAttribute("role", "status");
      toastEl.setAttribute("aria-live", "polite");
      document.body.appendChild(toastEl);
    }
    clearTimeout(toastTimer);
    toastEl.replaceChildren();
    const msg = document.createElement("span");
    msg.textContent = text;
    toastEl.append(msg);
    if (action) {
      const b = document.createElement("button");
      b.textContent = action.label;
      b.onclick = action.run;
      toastEl.append(b);
    }
    const x = document.createElement("button");
    x.className = "x"; x.setAttribute("aria-label", "Dismiss"); x.textContent = "✕";
    x.onclick = () => toastEl.classList.remove("show");
    toastEl.append(x);
    requestAnimationFrame(() => toastEl.classList.add("show"));
    if (ms) toastTimer = setTimeout(() => toastEl.classList.remove("show"), ms);
  }

  // ---- links that need signal (T6.4) ----
  const markExternal = () => document.querySelectorAll("a[href]").forEach(a => {
    try { if (new URL(a.href, location.href).origin !== location.origin) a.classList.add("needs-signal"); } catch {}
  });
  const syncOnline = () => document.documentElement.classList.toggle("is-offline", !navigator.onLine);
  addEventListener("online", syncOnline);
  addEventListener("offline", syncOnline);
  document.addEventListener("click", e => {
    const a = e.target.closest && e.target.closest("a[href]");
    if (!a || navigator.onLine) return;
    try { if (new URL(a.href, location.href).origin === location.origin) return; } catch { return; }
    e.preventDefault();
    toast("You're offline. This link needs signal; everything on this site still works.", null, 5000);
  }, true);

  if (!script || !("serviceWorker" in navigator) || !window.isSecureContext) {
    const start = () => { markExternal(); syncOnline(); setAll("[data-pwa-status]", "Offline saving isn't available in this browser."); };
    if (document.readyState === "loading") addEventListener("DOMContentLoaded", start); else start();
    return;
  }

  const swUrl = new URL("sw.js", script.src);
  const scope = new URL("./", script.src).pathname;
  let reg = null, deferredInstall = null, reloading = false, lastProgress = 0;

  // ---- offline status (T6.2) ----
  function showStatus(d) {
    if (d.type === "progress") {
      setAll("[data-pwa-status]", `Saving for offline: ${d.done} of ${d.total} files · ${MB(d.bytes)} of ${MB(d.totalBytes)}`);
    } else if (d.type === "installed") {
      setAll("[data-pwa-status]", `Saved for offline: ${d.files} files · ${MB(d.bytes)} · version ${d.version}`);
    } else if (d.type === "status") {
      setAll("[data-pwa-status]", d.complete
        ? `Saved for offline: ${d.files} files · ${MB(d.bytes)} · version ${d.version}`
        : `Offline copy incomplete (${d.have} of ${d.files} files). Open the site once with signal to finish.`);
    } else if (d.type === "install-failed") {
      setAll("[data-pwa-status]", `Saving for offline failed: ${d.error}. Reload with signal to try again.`);
      toast("Couldn't save the site for offline use. Reload with signal to try again.", null, 8000);
    }
    if (d.version) setAll("[data-pwa-version]", d.version);
  }

  // ---- updates ----
  function offerUpdate(worker) {
    toast("A new version is ready.", {
      label: "Update",
      run: () => { reloading = true; worker.postMessage({ type: "skip-waiting" }); }
    });
  }

  navigator.serviceWorker.addEventListener("controllerchange", () => { if (reloading) location.reload(); });
  navigator.serviceWorker.addEventListener("message", e => {
    const d = e.data || {};
    if (d.type === "version") setAll("[data-pwa-version]", d.version);
    if (d.type === "progress") {
      lastProgress = Date.now();
      if (!reg || !reg.waiting) showStatus(d);
    }
    if (["installed", "status", "install-failed"].includes(d.type)) showStatus(d);
  });

  function watch(r) {
    r.addEventListener("updatefound", () => {
      const worker = r.installing;
      if (!worker) return;
      worker.addEventListener("statechange", () => {
        if (worker.state === "redundant" && !reloading && Date.now() - lastProgress < 60000)
          toast("Saving for offline stopped. Reload with signal to try again.", null, 8000);
        if (worker.state !== "installed") return;
        if (navigator.serviceWorker.controller) offerUpdate(worker);
        else toast("Saved for offline use.", null, 4000);
      });
    });
  }

  async function checkForUpdates() {
    if (!reg) return toast("Offline saving isn't available in this browser.", null, 4000);
    if (reg.waiting) return offerUpdate(reg.waiting);
    toast("Checking for updates…");
    try {
      await reg.update();
    } catch {
      return toast("Can't reach the site right now. You're reading the saved copy.", null, 5000);
    }
    if (reg.waiting) offerUpdate(reg.waiting);
    else if (reg.installing) toast("Downloading the new version…");
    else toast("You have the latest version.", null, 3000);
  }

  // ---- install ----
  const standalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const syncInstallUI = () => document.querySelectorAll("[data-pwa-install]").forEach(el => { el.hidden = standalone(); });

  addEventListener("beforeinstallprompt", e => { e.preventDefault(); deferredInstall = e; syncInstallUI(); });
  addEventListener("appinstalled", () => { deferredInstall = null; syncInstallUI(); toast("Installed. Look for Spiti on your home screen.", null, 5000); });

  function install() {
    if (deferredInstall) {
      deferredInstall.prompt();
      deferredInstall.userChoice.finally(() => { deferredInstall = null; syncInstallUI(); });
    } else if (ios) {
      toast("In Safari, tap Share, then “Add to Home Screen”.", null, 7000);
    } else {
      toast("Open your browser menu and choose “Install app” or “Add to Home screen”.", null, 7000);
    }
  }

  document.addEventListener("click", e => {
    const t = e.target.closest("[data-pwa-install],[data-pwa-update]");
    if (!t) return;
    e.preventDefault();
    if (t.hasAttribute("data-pwa-install")) install(); else checkForUpdates();
  });

  // ---- register ----
  const start = () => {
    markExternal();
    syncOnline();
    syncInstallUI();
    navigator.serviceWorker.register(swUrl, { scope }).then(r => {
      reg = r;
      watch(r);
      if (r.waiting && navigator.serviceWorker.controller) offerUpdate(r.waiting);
      if (r.installing) setAll("[data-pwa-status]", "Saving for offline…");
      navigator.serviceWorker.ready.then(ready => {
        // keep what this page pulled from other sites (fonts, scripts) for offline use
        const urls = performance.getEntriesByType("resource").map(x => x.name).filter(u => u.startsWith("http"));
        ready.active.postMessage({ type: "cache", urls });
        ready.active.postMessage({ type: "status" });
      });
      document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") r.update().catch(() => {}); });
    }).catch(() => setAll("[data-pwa-status]", "Offline saving could not start in this browser."));
  };
  if (document.readyState === "complete") start(); else addEventListener("load", start);
})();
