// Встраивается оболочкой (desktop-win/shell) в страницы главного фрейма — как PAGE_SCRIPT в desktop/shell.py.
// Браузер шлёт уведомление, только когда вкладка скрыта; у программы «скрыто» — это ещё и окно не в фокусе
// (window.__tgDesktopActive выставляет оболочка). Выход из панели в локальном режиме не нужен: вход выполняет
// сама программа. TG_DESKTOP_APP — версия и режим программы для значка «Вышло обновление»: кнопка «Обновить
// программу» переходит на <панель>/tg-desktop/update, переход ловит оболочка.
(() => {
  if (window.top !== window || window.__tgDesktopInit) return;   // мини-приложения ботов во фреймах не трогаем
  window.__tgDesktopInit = true;
  const APP = __TG_APP__;
  window.TG_DESKTOP = true;
  window.TG_DESKTOP_APP = { version: APP.version, mode: APP.mode, update: true };
  // строкой с префиксом — объекты оболочка не получает (см. webview.rs, attach_messages)
  const post = msg => { try { window.chrome.webview.postMessage("tg-desktop:" + JSON.stringify(msg)); } catch (e) { /* не WebView2 */ } };

  const real = Object.getOwnPropertyDescriptor(Document.prototype, "visibilityState");
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get() { return window.__tgDesktopActive === false ? "hidden" : real.get.call(document); },
  });

  // new Notification(...) — системное уведомление Windows от имени TG Panel; разрешение есть всегда
  class DesktopNotification extends EventTarget {
    constructor(title, options = {}) {
      super();
      this.title = String(title);
      this.body = String(options.body || "");
      this.tag = options.tag || "";
      this.data = options.data;
      this.onclick = this.onclose = this.onerror = this.onshow = null;
      post({ type: "notify", title: this.title, body: this.body });
    }
    close() {}
    static get permission() { return "granted"; }
    static requestPermission(cb) {
      if (typeof cb === "function") cb("granted");
      return Promise.resolve("granted");
    }
  }
  Object.defineProperty(window, "Notification", { configurable: true, writable: true, value: DesktopNotification });

  // ошибки страницы — в журнал программы: пустое окно из-за ошибки в app.js иначе не объяснить
  const reported = new Set();
  const report = text => {
    text = String(text).slice(0, 1000);
    if (reported.size < 50 && !reported.has(text)) { reported.add(text); post({ type: "js-error", text }); }
  };
  window.addEventListener("error", e => report(`${e.message} (${e.filename}:${e.lineno})`));
  window.addEventListener("unhandledrejection", e => report(`unhandledrejection: ${e.reason?.stack || e.reason}`));

  const ready = fn => (document.body ? fn() : document.addEventListener("DOMContentLoaded", fn, { once: true }));

  // тема панели (data-theme на <html>) — и заголовку окна: тёмная панель без светлой полосы сверху
  let theme = null;
  const sendTheme = () => {
    const t = document.documentElement.getAttribute("data-theme");
    if ((t === "dark" || t === "light") && t !== theme) { theme = t; post({ type: "theme", theme: t }); }
  };
  // <html> появляется только при разборе страницы — скрипт выполняется раньше
  ready(() => {
    sendTheme();
    new MutationObserver(sendTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  });
  if (APP.hideLogout) {
    const style = () => {
      const s = document.createElement("style");
      s.textContent = "#logout { display: none !important; }";
      document.head.appendChild(s);
    };
    if (document.head) style(); else document.addEventListener("DOMContentLoaded", style, { once: true });
  }

  // Плашка оболочки вместо модальных окон: «Обновление готово · Перезапустить», «Обновлено до X».
  // Цвета — токены панели (--elev, --text, --accent…), с запасными значениями для чужих страниц.
  const CSS = `
    :host { all: initial; }
    .bar { position: fixed; top: 14px; left: 50%; transform: translateX(-50%); z-index: 2147483000;
      display: flex; align-items: center; gap: 12px; max-width: min(560px, calc(100vw - 32px)); box-sizing: border-box;
      padding: 10px 10px 10px 12px; border-radius: 14px; background: var(--elev, #141f36); color: var(--text, #e7eef9);
      border: 1px solid var(--border-strong, rgb(148 163 184 / .18));
      box-shadow: var(--shadow, 0 16px 48px rgb(0 0 0 / .45)), inset 0 1px 0 var(--edge, rgb(255 255 255 / .05));
      font: 13.5px/1.4 Inter, system-ui, "Segoe UI", sans-serif; animation: in .4s cubic-bezier(.34, 1.45, .64, 1); }
    .bar.out { animation: out .2s ease-in forwards; }
    .ico { flex: none; width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center;
      color: var(--accent, #4f8cff); background: var(--accent-soft, rgb(79 140 255 / .16)); }
    .ico svg { width: 17px; height: 17px; }
    .txt { min-width: 0; display: flex; flex-direction: column; }
    .txt b { font-weight: 600; }
    .txt span { color: var(--muted, #8796b3); font-size: 12.5px; overflow: hidden; display: -webkit-box;
      -webkit-line-clamp: 3; -webkit-box-orient: vertical; white-space: pre-line; }
    button { font: inherit; cursor: pointer; border: 0; border-radius: 10px; }
    .act { flex: none; padding: 7px 14px; background: var(--accent, #4f8cff); color: #fff; font-weight: 600; }
    .act:hover { filter: brightness(1.08); }
    .x { flex: none; width: 28px; height: 28px; background: transparent; color: var(--muted, #8796b3); font-size: 18px; line-height: 1; }
    .x:hover { color: var(--text, #e7eef9); background: var(--accent-soft, rgb(79 140 255 / .16)); }
    @keyframes in { from { opacity: 0; transform: translate(-50%, -10px) scale(.97); } }
    @keyframes out { to { opacity: 0; transform: translate(-50%, -8px); } }`;
  const ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>';
  let host = null;
  window.__tgDesktopBanner = banner => ready(() => {
    host?.remove();
    host = null;
    if (!banner) return;
    host = document.createElement("tg-desktop-banner");
    const root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `<style>${CSS}</style><div class="bar" role="status"><span class="ico">${ICON}</span>
      <div class="txt"><b></b><span></span></div>${banner.action ? '<button class="act"></button>' : ""}
      <button class="x" title="Закрыть" aria-label="Закрыть">×</button></div>`;
    root.querySelector("b").textContent = banner.title || "";
    const text = root.querySelector(".txt span");
    if (banner.text) text.textContent = banner.text; else text.remove();
    const bar = root.querySelector(".bar"), current = host;
    const close = send => {
      if (send) post({ type: "banner", id: banner.id, action: send });
      bar.classList.add("out");
      setTimeout(() => current.remove(), 220);
      if (host === current) host = null;
    };
    const act = root.querySelector(".act");
    if (act) { act.textContent = banner.action; act.onclick = () => close("action"); }
    root.querySelector(".x").onclick = () => close("dismiss");
    if (banner.timeout) setTimeout(() => host === current && close("timeout"), banner.timeout);
    document.body.appendChild(host);
  });
})();
