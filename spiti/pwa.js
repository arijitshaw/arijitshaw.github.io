// Shared by every page under spiti/: registers the offline service worker, offers
// "Install app", and shows an "Update" prompt when a new version is published.
// Elements can opt in with data attributes:
//   data-pwa-install   click -> install prompt (hidden when already installed)
//   data-pwa-update    click -> check for updates now
//   data-pwa-version   filled with the saved version
(() => {
  const script = document.currentScript;
  if (!script || !("serviceWorker" in navigator) || !window.isSecureContext) return;

  const swUrl = new URL("sw.js", script.src);
  const scope = new URL("./", script.src).pathname;
  let reg = null, deferredInstall = null, reloading = false;

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
.pwa-toast button{flex:none;appearance:none;border:0;border-radius:999px;padding:8px 14px;cursor:pointer;
  font:600 14px/1 "Lora",Georgia,serif;background:#e6bb78;color:#201f1d}
.pwa-toast button.x{background:transparent;color:#f3f2f2;padding:8px 10px;font-size:16px}
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

  // ---- updates ----
  function offerUpdate(worker) {
    toast("A new version is ready.", {
      label: "Update",
      run: () => { reloading = true; worker.postMessage({ type: "skip-waiting" }); }
    });
  }

  navigator.serviceWorker.addEventListener("controllerchange", () => { if (reloading) location.reload(); });
  navigator.serviceWorker.addEventListener("message", e => {
    if (e.data && e.data.type === "version")
      document.querySelectorAll("[data-pwa-version]").forEach(el => { el.textContent = e.data.version; });
  });

  function watch(r) {
    r.addEventListener("updatefound", () => {
      const worker = r.installing;
      if (!worker) return;
      worker.addEventListener("statechange", () => {
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
    syncInstallUI();
    navigator.serviceWorker.register(swUrl, { scope }).then(r => {
      reg = r;
      watch(r);
      if (r.waiting && navigator.serviceWorker.controller) offerUpdate(r.waiting);
      navigator.serviceWorker.ready.then(ready => {
        // keep what this page pulled from other sites (fonts, scripts) for offline use
        const urls = performance.getEntriesByType("resource").map(x => x.name).filter(u => u.startsWith("http"));
        ready.active.postMessage({ type: "cache", urls });
        ready.active.postMessage({ type: "version" });
      });
      document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") r.update().catch(() => {}); });
    }).catch(() => {});
  };
  if (document.readyState === "complete") start(); else addEventListener("load", start);
})();
