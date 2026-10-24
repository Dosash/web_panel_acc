/* Панель «Бот рекламы». Чистый JS без сборки: hash-роутинг, JSON API на /<prefix>/api. */
(function () {
  "use strict";
  var P = window.PANEL.prefix, API = P + "/api";

  // ---------------- иконки (lucide) ----------------
  var ICONS = {
    dashboard: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/>',
    receipt: '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    megaphone: '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    message: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    settings: '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    back: '<path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2m-7.07-14.07 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    monitor: '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8M12 17v4"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    copy: '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    trash: '<path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    edit: '<path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.38 2.62a2.12 2.12 0 1 1 3 3L12 15l-4 1 1-4Z"/>',
    plus: '<path d="M5 12h14M12 5v14"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    send: '<path d="M14.54 21.69a.5.5 0 0 0 .94-.03l6.5-19a.5.5 0 0 0-.64-.64l-19 6.5a.5.5 0 0 0-.03.94l7.93 3.18a2 2 0 0 1 1.11 1.11z"/><path d="m21.85 2.15-10.94 10.94"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    external: '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    eye: '<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7 10.75 10.75 0 0 1-19.88 0"/><circle cx="12" cy="12" r="3"/>',
    eyeoff: '<path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="1"/>',
    lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>'
  };
  function icon(name, cls) { return '<svg class="i ' + (cls || "") + '" viewBox="0 0 24 24" aria-hidden="true">' + (ICONS[name] || "") + "</svg>"; }

  // ---------------- утилиты ----------------
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function fmtNum(n) { n = n || 0; if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M"; if (n >= 1e4) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K"; return n.toLocaleString("ru-RU"); }
  function fmtUsd(x) { x = Number(x || 0); return "$" + (Math.round(x * 100) % 100 ? x.toFixed(2) : x.toFixed(0)); }
  function fmtRub(x) { x = Number(x || 0); return (Math.round(x * 100) % 100 ? x.toFixed(2) : x.toFixed(0)) + " ₽"; }
  // цены в трёх валютах; 0 — валюта не задана (способ оплаты в ней не показывается)
  function fmtPrice(stars, usd, rub) {
    var p = [];
    if (+usd) p.push(fmtUsd(usd));
    if (+rub) p.push(fmtRub(rub));
    if (+stars) p.push(stars + " ⭐");
    return p.join(" / ") || "—";
  }
  function shortPrice(stars, usd, rub) { return +usd ? fmtUsd(usd) : +rub ? fmtRub(rub) : +stars ? stars + " ⭐" : "—"; }
  function orderPrice(o) { return shortPrice(o.total_stars, o.total_usd, o.total_rub); }
  function hasPrice(c) { return !!(+c.price_stars || +c.price_usd || +c.price_rub); }
  // Время всегда в часовом поясе бота (как в Telegram), а не браузера
  var TZ = window.PANEL.tz || undefined;
  function fmtDate(ts) { if (!ts) return "—"; return new Date(ts * 1000).toLocaleString("ru-RU", { timeZone: TZ, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }); }
  function fmtDay(ts) { return new Date(ts * 1000).toLocaleDateString("ru-RU", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" }); }
  function fmtTime(ts) { return new Date(ts * 1000).toLocaleTimeString("ru-RU", { timeZone: TZ, hour: "2-digit", minute: "2-digit" }); }
  // Короткий список каналов: «A, B, C и ещё 61»
  function chNames(o, max) {
    max = max || 3;
    var names = o.channels.map(function (c) { return c.title; });
    return names.length > max ? names.slice(0, max).join(", ") + " и ещё " + (names.length - max) : names.join(", ");
  }
  function plural(n, a, b, c) { var m = n % 10, h = n % 100; return n + " " + (m === 1 && h !== 11 ? a : m >= 2 && m <= 4 && (h < 10 || h >= 20) ? b : c); }

  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", headers: { "X-Panel": "1" }, credentials: "same-origin" };
    if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
    return fetch(API + path, init).then(function (r) {
      if (r.status === 401) { state.auth = false; render(); throw new Error("Требуется вход"); }
      return r.json().catch(function () { return { ok: false, error: "Ошибка сервера (" + r.status + ")" }; });
    }).then(function (d) { if (!d.ok) throw new Error(d.error || "Ошибка"); return d.data; });
  }

  function toast(text, isError) {
    var el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : "");
    el.textContent = text;
    $("#toasts").appendChild(el);
    setTimeout(function () { el.remove(); }, isError ? 6000 : 3500);
  }
  function fail(e) { toast(e && e.message ? e.message : String(e), true); }

  function copyText(text) {
    var done = function () { toast("Скопировано"); };
    if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); }); }
    else { fallbackCopy(text); done(); }
  }
  function fallbackCopy(text) {
    var ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e) {} ta.remove();
  }

  // Модальное окно. fields: [{name,label,type,value,hint,placeholder}], actions через onSubmit
  function modal(o) {
    var back = document.createElement("div");
    back.className = "modal-back";
    var fields = (o.fields || []).map(function (f) {
      var id = "f_" + f.name, input;
      if (f.type === "textarea") input = '<textarea class="textarea" id="' + id + '" name="' + f.name + '" rows="' + (f.rows || 6) + '" placeholder="' + esc(f.placeholder || "") + '">' + esc(f.value || "") + "</textarea>";
      else if (f.type === "checkbox") input = '<label class="row"><input type="checkbox" id="' + id + '" name="' + f.name + '"' + (f.value ? " checked" : "") + "> " + esc(f.text || "") + "</label>";
      else input = '<input class="input" id="' + id + '" name="' + f.name + '" type="' + (f.type || "text") + '" value="' + esc(f.value == null ? "" : f.value) + '" placeholder="' + esc(f.placeholder || "") + '"' + (f.step ? ' step="' + f.step + '"' : "") + ">";
      return '<div class="field">' + (f.type === "checkbox" ? "" : '<label for="' + id + '">' + esc(f.label) + "</label>") + input + (f.hint ? '<div class="hint">' + f.hint + "</div>" : "") + "</div>";
    }).join("");
    back.innerHTML = '<div class="modal' + (o.wide ? " wide" : "") + '" role="dialog" aria-modal="true"><form>' +
      '<div class="modal__head"><div class="modal__title">' + esc(o.title) + '</div><span class="spacer"></span><button type="button" class="btn ghost icon sm" data-close aria-label="Закрыть">' + icon("x") + "</button></div>" +
      '<div class="modal__body">' + (o.html || "") + fields + "</div>" +
      '<div class="modal__foot"><button type="button" class="btn secondary" data-close>' + (o.submit ? "Отмена" : "Закрыть") + '</button>' +
      (o.submit ? '<button type="submit" class="btn ' + (o.danger ? "danger" : "primary") + '">' + esc(o.submit) + "</button>" : "") + "</div></form></div>";
    function close() { back.remove(); document.removeEventListener("keydown", onKey); }
    function onKey(e) { if (e.key === "Escape") close(); }
    document.addEventListener("keydown", onKey);
    back.addEventListener("click", function (e) { if (e.target === back || e.target.closest("[data-close]")) close(); });
    $("form", back).addEventListener("submit", function (e) {
      e.preventDefault();
      var values = {};
      (o.fields || []).forEach(function (f) { var el = $("#f_" + f.name, back); values[f.name] = f.type === "checkbox" ? el.checked : el.value; });
      var btn = $('button[type="submit"]', back); if (btn) btn.disabled = true;
      Promise.resolve(o.onSubmit ? o.onSubmit(values, back) : null).then(function (keep) { if (keep !== true) close(); })
        .catch(function (err) { fail(err); if (btn) btn.disabled = false; });
    });
    document.body.appendChild(back);
    var first = $("input,textarea", back) || $('button[type="submit"]', back); if (first) first.focus();
    return { el: back, close: close };
  }
  function confirmBox(title, text, submit, danger) {
    return new Promise(function (resolve) {
      var m = modal({ title: title, html: "<p>" + text + "</p>", submit: submit, danger: danger, onSubmit: function () { resolve(true); } });
      m.el.addEventListener("click", function (e) { if (e.target === m.el || e.target.closest("[data-close]")) resolve(false); });
    });
  }

  // Безопасный рендер HTML-текста поста (форматирование Telegram): разрешаем только простые теги
  function safePostHtml(html) {
    var doc = new DOMParser().parseFromString("<div>" + (html || "") + "</div>", "text/html");
    var allowed = { B: 1, STRONG: 1, I: 1, EM: 1, U: 1, INS: 1, S: 1, STRIKE: 1, DEL: 1, CODE: 1, PRE: 1, A: 1, BLOCKQUOTE: 1, SPAN: 1, "TG-SPOILER": 1, BR: 1 };
    (function walk(node) {
      Array.prototype.slice.call(node.childNodes).forEach(function (ch) {
        if (ch.nodeType === 1) {
          if (!allowed[ch.tagName]) { ch.replaceWith(document.createTextNode(ch.textContent)); return; }
          var href = ch.tagName === "A" ? ch.getAttribute("href") : null;
          Array.prototype.slice.call(ch.attributes).forEach(function (a) { ch.removeAttribute(a.name); });
          if (ch.tagName === "A") {
            if (href && /^(https?:|tg:)/i.test(href)) { ch.setAttribute("href", href); ch.setAttribute("target", "_blank"); ch.setAttribute("rel", "noopener noreferrer"); }
          }
          if (ch.tagName === "TG-SPOILER") ch.className = "spoiler";
          walk(ch);
        }
      });
    })(doc.body.firstChild);
    return doc.body.firstChild.innerHTML;
  }

  var BTN_STYLE = { success: "success", danger: "danger", primary: "info" };   // цвет кнопки в Telegram → токен панели

  function postPreview(order) {
    var p = order.post;
    if (!p) return '<div class="empty small">Снимок поста недоступен (заказ создан до появления панели). Нажмите «Прислать мне в Telegram», чтобы посмотреть пост.</div>';
    var media = "";
    var src = API + "/orders/" + order.id + "/media";
    if (p.kind === "photo" || p.kind === "sticker") media = '<div class="post__media"><img src="' + src + '" alt="" loading="lazy"></div>';
    else if (p.kind === "video" || p.kind === "animation" || p.kind === "video_note") media = '<div class="post__media"><video src="' + src + '" controls muted playsinline preload="metadata"></video></div>';
    else if (p.kind !== "text") media = '<div class="post__file">📎 Вложение: ' + esc(p.kind) + ' · <a href="' + src + '" target="_blank">открыть</a></div>';
    var buttons = (p.buttons || []).map(function (row) {
      return '<div class="brow">' + row.map(function (b) { return '<a href="' + esc(b.url) + '"' + (BTN_STYLE[b.style] ? ' class="' + BTN_STYLE[b.style] + '"' : "") + ' target="_blank" rel="noopener noreferrer">' + esc(b.text) + "</a>"; }).join("") + "</div>";
    }).join("");
    return '<div class="post">' + media + (p.html ? '<div class="post__text">' + safePostHtml(p.html) + "</div>" : "") +
      (buttons ? '<div class="post__buttons">' + buttons + "</div>" : "") + "</div>";
  }

  var STATUS = {
    moderation: ["На модерации", "warning"], approved: ["Ждёт оплаты", "info"], rejected: ["Отклонён", "danger"],
    paid: ["Оплачен, публикуется", "accent"], scheduled: ["Оплачен, ждёт публикации", "accent"], need_time: ["Оплачен — нужно время", "warning"],
    published: ["Опубликован", "success"], cancelled: ["Отменён", ""], expired: ["Бронь истекла", ""]
  };
  function statusBadge(s) { var v = STATUS[s] || [s, ""]; return '<span class="badge ' + v[1] + '"><span class="dot"></span>' + esc(v[0]) + "</span>"; }
  var PAY = { stars: "Telegram Stars", crypto: "CryptoBot", xrocket: "xRocket", freekassa: "FreeKassa", test: "Тестовая" };

  // ---------------- состояние и каркас ----------------
  var state = { auth: true, counts: { moderation: 0, support: 0 }, summary: null };
  var NAV = [
    { group: "Работа", items: [
      { id: "", title: "Обзор", icon: "dashboard" },
      { id: "moderation", title: "Модерация", icon: "shield", count: "moderation" },
      { id: "orders", title: "Заказы", icon: "receipt" },
      { id: "schedule", title: "Расписание", icon: "calendar" },
      { id: "support", title: "Обращения", icon: "message", count: "support" },
      { id: "broadcast", title: "Рассылка", icon: "send" }
    ] },
    { group: "Каналы", items: [
      { id: "channels", title: "Каналы", icon: "megaphone" },
      { id: "links", title: "Ссылки на каналы", icon: "link" }
    ] },
    { group: "Система", items: [{ id: "settings", title: "Настройки", icon: "settings" }] }
  ];
  var PAGES = {};

  function route() { var h = location.hash.replace(/^#\/?/, ""); var parts = h.split("/"); return { page: parts[0] || "", arg: parts[1] || "" }; }

  function shell() {
    var r = route();
    var nav = NAV.map(function (g) {
      return '<div class="nav-group"><div class="nav-label">' + g.group + "</div>" + g.items.map(function (it) {
        var c = it.count ? state.counts[it.count] : 0;
        return '<a class="nav-item' + (r.page === it.id ? " active" : "") + '" href="#/' + it.id + '">' + icon(it.icon) + "<span>" + it.title + "</span>" +
          (c ? '<span class="count">' + c + "</span>" : "") + "</a>";
      }).join("") + "</div>";
    }).join("");
    $("#app").innerHTML =
      '<aside class="sidebar">' +   // панель открыта внутри TG Panel — ссылка «Все панели» не нужна
      '<div class="product"><span class="product__logo">' + icon("megaphone") + '</span><div><div class="product__name">Реклама</div><div class="product__sub">Бот продажи рекламы</div></div></div>' +
      nav + '<div class="sidebar__bottom"><button class="btn ghost icon sm" id="theme" title="Тема"></button><span class="version">v' + esc(window.PANEL.version) + "</span></div></aside>" +
      '<div class="backdrop" id="backdrop"></div>' +
      '<div class="main"><header class="topbar"><button class="btn ghost icon burger" id="burger" aria-label="Меню">' + icon("menu") + "</button>" +
      '<div><h1 id="title"></h1></div><span class="spacer"></span><div class="row" id="actions"></div><span id="status"></span></header>' +
      '<main class="content" id="page"></main></div>';
    $("#burger").onclick = function () { document.body.classList.toggle("nav-open"); };
    $("#backdrop").onclick = function () { document.body.classList.remove("nav-open"); };
    themeButton();
    statusPill();
  }

  function themeButton() {
    var btn = $("#theme"); if (!btn) return;
    var get = function () { try { return localStorage.getItem("panel-theme") || "system"; } catch (e) { return "system"; } };
    var paint = function () { var m = get(); btn.innerHTML = icon(m === "light" ? "sun" : m === "dark" ? "moon" : "monitor"); btn.title = "Тема: " + { light: "светлая", dark: "тёмная", system: "системная" }[m]; };
    btn.onclick = function () {
      var next = { system: "light", light: "dark", dark: "system" }[get()];
      try { localStorage.setItem("panel-theme", next); } catch (e) {}
      if (next === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = next;
      paint();
    };
    paint();
  }

  function statusPill() {
    var el = $("#status"); if (!el) return;
    fetch(API + "/health", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
      el.innerHTML = '<span class="badge success"><span class="dot"></span>Работает</span>';
      state.counts.moderation = d.moderation; state.counts.support = d.support_unread;
      $$(".nav-item").forEach(function (a) {
        var id = a.getAttribute("href").replace("#/", ""), it = null;
        NAV.forEach(function (g) { g.items.forEach(function (x) { if (x.id === id) it = x; }); });
        if (!it || !it.count) return;
        var c = state.counts[it.count], badge = $(".count", a);
        if (c && !badge) a.insertAdjacentHTML("beforeend", '<span class="count">' + c + "</span>");
        else if (c) badge.textContent = c; else if (badge) badge.remove();
      });
    }).catch(function () { el.innerHTML = '<span class="badge danger"><span class="dot"></span>Ошибка</span>'; });
  }

  function setPage(title, actions) {
    $("#title").textContent = title;
    document.title = title + " — Реклама";
    $("#actions").innerHTML = actions || "";
  }
  function loading() { $("#page").innerHTML = '<div class="card"><div class="skeleton" style="width:40%"></div><div class="skeleton"></div><div class="skeleton" style="width:70%"></div><div class="skeleton" style="width:55%"></div></div>'; }
  function empty(iconName, title, hint, action) {
    return '<div class="empty">' + icon(iconName) + '<div class="empty__title">' + esc(title) + "</div><div>" + (hint || "") + "</div>" + (action || "") + "</div>";
  }

  function render() {
    if (!state.auth) return renderLogin();
    if (!$(".sidebar")) shell();
    var r = route();
    $$(".nav-item").forEach(function (a) { a.classList.toggle("active", a.getAttribute("href") === "#/" + r.page); });
    document.body.classList.remove("nav-open");
    (PAGES[r.page] || PAGES[""])(r.arg);
  }

  function renderLogin() {
    $("#app").innerHTML = '<div class="login card"><div class="card__head"><span class="product__logo">' + icon("lock") + '</span><div class="card__title">Вход в панель «Реклама»</div></div>' +
      '<form class="stack" id="loginForm"><div class="field"><label for="pw">Пароль</label><input class="input" id="pw" type="password" autocomplete="current-password" autofocus></div>' +
      '<button class="btn primary" type="submit">Войти</button></form></div>';
    $("#loginForm").onsubmit = function (e) {
      e.preventDefault();
      api("/login", { method: "POST", body: { password: $("#pw").value } }).then(function () { state.auth = true; $("#app").innerHTML = ""; render(); }).catch(fail);
    };
  }

  // ---------------- Обзор ----------------
  PAGES[""] = function () {
    setPage("Обзор", '<a class="btn secondary sm" href="#/links">' + icon("link") + " Ссылки на каналы</a>");
    loading();
    api("/summary").then(function (s) {
      state.summary = s;
      var st = s.stats || {}, au = s.audience || {};
      var tile = function (label, value, hint, href, attn) {
        return '<' + (href ? 'a href="' + href + '"' : "div") + ' class="tile' + (attn ? " attn" : "") + '"><div class="tile__label">' + label + '</div><div class="tile__value">' + value + "</div>" + (hint ? '<div class="tile__hint">' + hint + "</div>" : "") + "</" + (href ? "a" : "div") + ">";
      };
      var upcoming = s.upcoming.length ? s.upcoming.map(function (o) {
        return '<div class="sched-row"><span class="time">' + esc(fmtDate(o.publish_at)) + '</span><span class="spacer small">#' + o.id + " · " + esc(chNames(o)) + "</span>" + statusBadge(o.status) + "</div>";
      }).join("") : empty("calendar", "Публикаций не запланировано", "");
      var pay = function (name, on) { return '<div class="row" style="justify-content:space-between;padding:6px 0"><span>' + name + "</span>" + (on ? '<span class="badge success"><span class="dot"></span>Подключено</span>' : '<span class="badge"><span class="dot"></span>Не настроено</span>') + "</div>"; };
      $("#page").innerHTML =
        '<div class="tiles">' +
        tile("На модерации", s.moderation, "ждут проверки", "#/moderation", s.moderation > 0) +
        tile("Ждут оплаты", s.awaiting_payment, "одобрены", "#/orders/approved") +
        tile("Запланировано", s.scheduled, "оплачены, ждут времени", "#/schedule") +
        tile("Новые сообщения", s.support_unread, "в обращениях", "#/support", s.support_unread > 0) +
        tile("Запуски бота", fmtNum(au.starts), "сегодня " + fmtNum(au.starts_day) + " · за неделю " + fmtNum(au.starts_week)) +
        tile("Пользователи", fmtNum(au.active), "не заблокировали бота · всего " + fmtNum(au.users) + (au.blocked ? " · ушли " + fmtNum(au.blocked) : "") + (au.new_day ? " · новых за сутки " + au.new_day : ""), "#/broadcast") +
        tile("Каналов", s.channels, s.channels_visible + " видны покупателям" + (s.channels_no_admin ? " · ⚠️ без бота: " + s.channels_no_admin : ""), "#/channels") +
        tile("Охват", fmtNum(s.reach), "подписчиков суммарно", "#/channels") +
        "</div>" +
        '<div class="grid-2"><div class="card flush"><div class="card__head"><div class="card__title">Ближайшие публикации</div><span class="spacer"></span><a class="btn ghost sm" href="#/schedule">Всё расписание</a></div>' + upcoming + "</div>" +
        '<div class="stack"><div class="card"><div class="card__head"><div class="card__title">Продажи</div></div>' +
        '<div class="tiles" style="margin:0;grid-template-columns:repeat(2,1fr)">' +
        tile("Оплаченных заказов", st.paid || 0) + tile("Клиентов", st.users || 0) +
        tile("Звёздами", (st.stars || 0) + " ⭐") + tile("Криптой", fmtUsd((st.usd || 0) + (st.xrocket || 0)), "CryptoBot " + fmtUsd(st.usd) + " · xRocket " + fmtUsd(st.xrocket)) +
        tile("Рублями", fmtRub(st.freekassa), "FreeKassa: СБП, карты") +
        "</div></div>" +
        '<div class="card"><div class="card__head"><div class="card__title">Способы оплаты</div></div>' + pay("Telegram Stars", s.payments.stars) + pay("CryptoBot", s.payments.cryptobot) + pay("xRocket Pay", s.payments.xrocket) + pay("FreeKassa (₽)", s.payments.freekassa) +
        '<div class="small muted" style="margin-top:8px">Бот: <a href="https://t.me/' + esc(s.bot) + '" target="_blank">@' + esc(s.bot) + "</a></div></div></div></div>";
    }).catch(fail);
  };

  // ---------------- Модерация ----------------
  PAGES.moderation = function (arg) {
    setPage("Модерация");
    loading();
    api("/orders?status=moderation").then(function (orders) {
      orders = orders.slice().reverse(); // старые сверху — в порядке очереди
      if (!orders.length) { $("#page").innerHTML = '<div class="card">' + empty("shield", "Очередь пуста", "Новые посты появятся здесь — и придут уведомлением в Telegram.") + "</div>"; return; }
      var current = orders.filter(function (o) { return String(o.id) === arg; })[0] || orders[0];
      var list = orders.map(function (o) {
        return '<a class="list-item' + (o === current ? " active" : "") + '" href="#/moderation/' + o.id + '"><div class="list-item__main"><div class="list-item__title">' + (o.is_test ? "🧪 " : "") + "#" + o.id + " · " + esc(o.user_name || o.user_id) + '</div><div class="list-item__sub">' +
          esc(plural(o.channels.length, "канал", "канала", "каналов") + " · " + orderPrice(o) + " · " + o.publish_text) + "</div></div></a>";
      }).join("");
      $("#page").innerHTML = '<div class="split"><div class="card flush"><div class="card__head"><div class="card__title">В очереди</div><span class="badge accent">' + orders.length + '</span></div><div class="scroll">' + list + "</div></div>" +
        '<div class="card" id="modDetail"></div></div>';
      renderModDetail(current);
    }).catch(fail);
  };

  function orderKv(o) {
    return '<dl class="kv">' +
      "<dt>Заказчик</dt><dd>" + esc(o.user_name || "") + ' · <a href="tg://user?id=' + o.user_id + '">' + o.user_id + "</a></dd>" +
      "<dt>Публикация</dt><dd>" + esc(o.publish_text) + (o.time_ok ? "" : ' <span class="badge warning">время прошло</span>') + "</dd>" +
      "<dt>Каналы (" + o.channels.length + ")</dt><dd>" + (o.channels.length > 6
        ? esc(chNames(o, 6)) + ' <details style="display:inline"><summary class="small" style="cursor:pointer;color:var(--accent)">все</summary><div class="small">' + esc(o.channels.map(function (c) { return c.title; }).join(", ")) + "</div></details>"
        : esc(chNames(o, 6))) + "</dd>" +
      "<dt>Сумма</dt><dd>" + esc(fmtPrice(o.total_stars, o.total_usd, o.total_rub)) + "</dd>" +
      "<dt>Статус</dt><dd>" + statusBadge(o.status) + (o.is_test ? ' <span class="badge info">тестовый</span>' : "") + "</dd>" +
      (o.pay_method ? "<dt>Оплата</dt><dd>" + esc(PAY[o.pay_method] || o.pay_method) + (o.paid_at ? " · " + fmtDate(o.paid_at) : "") + "</dd>" : "") +
      (o.reject_reason ? "<dt>Причина отказа</dt><dd>" + esc(o.reject_reason) + "</dd>" : "") +
      "<dt>Создан</dt><dd>" + fmtDate(o.created_at) + "</dd></dl>";
  }

  function renderModDetail(o) {
    var box = $("#modDetail");
    box.innerHTML = '<div class="card__head"><div class="card__title">Заказ #' + o.id + '</div><span class="spacer"></span>' +
      '<button class="btn ghost sm" id="mPreview">' + icon("send") + " Прислать мне в Telegram</button></div>" +
      '<div class="grid-2"><div>' + postPreview(o) + "</div><div class=\"stack\">" + orderKv(o) +
      (o.time_ok ? "" : '<div class="badge warning" style="height:auto;padding:8px 12px;white-space:normal">Время публикации уже прошло — после одобрения пользователь выберет новое.</div>') +
      '<div class="row wrap"><button class="btn success" id="mApprove">' + icon("check") + ' Одобрить</button><button class="btn danger" id="mReject">' + icon("x") + " Отклонить</button></div></div></div>";
    $("#mPreview").onclick = function () { api("/orders/" + o.id + "/preview", { method: "POST" }).then(function () { toast("Пост отправлен вам в Telegram"); }).catch(fail); };
    $("#mApprove").onclick = function () {
      this.disabled = true;
      api("/orders/" + o.id + "/approve", { method: "POST" }).then(function () { toast("Заказ #" + o.id + " одобрен, пользователю отправлен счёт"); location.hash = "#/moderation"; PAGES.moderation(""); statusPill(); }).catch(function (e) { fail(e); PAGES.moderation(""); });
    };
    $("#mReject").onclick = function () {
      modal({ title: "Отклонить заказ #" + o.id, submit: "Отклонить", danger: true,
        fields: [{ name: "reason", label: "Причина (увидит пользователь)", type: "textarea", rows: 4, placeholder: "Необязательно" }],
        onSubmit: function (v) { return api("/orders/" + o.id + "/reject", { method: "POST", body: { reason: v.reason } }).then(function () { toast("Заказ #" + o.id + " отклонён"); location.hash = "#/moderation"; PAGES.moderation(""); statusPill(); }); } });
    };
  }

  // ---------------- Заказы ----------------
  var ORDER_TABS = [["", "Все"], ["moderation", "На модерации"], ["approved", "Ждут оплаты"], ["scheduled", "Запланированы"], ["need_time", "Нужно время"], ["published", "Опубликованы"], ["rejected", "Отклонены"], ["cancelled", "Отменены"]];
  PAGES.orders = function (arg) {
    setPage("Заказы");
    var tabs = '<div class="tabs">' + ORDER_TABS.map(function (t) { return '<a class="tab' + (arg === t[0] ? " active" : "") + '" href="#/orders/' + t[0] + '">' + t[1] + "</a>"; }).join("") + "</div>";
    loading();
    api("/orders" + (arg ? "?status=" + arg : "")).then(function (orders) {
      if (!orders.length) { $("#page").innerHTML = tabs + '<div class="card">' + empty("receipt", "Заказов нет", "") + "</div>"; return; }
      var rows = orders.map(function (o) {
        return '<tr class="clickable" data-id="' + o.id + '"><td class="num">' + (o.is_test ? "🧪 " : "") + "#" + o.id + "</td><td>" + esc(o.user_name || o.user_id) + '</td><td class="t-title" title="' + esc(o.channels.map(function (c) { return c.title; }).join(", ")) + '">' + esc(chNames(o, 2)) +
          '</td><td class="nowrap">' + esc(o.publish_text) + '</td><td class="right num nowrap">' + orderPrice(o) + "</td><td>" + statusBadge(o.status) + '</td><td class="nowrap small muted">' + esc(o.pay_method ? (PAY[o.pay_method] || o.pay_method) : "—") + "</td></tr>";
      }).join("");
      $("#page").innerHTML = tabs + '<div class="card flush"><div class="table-wrap"><table class="table"><thead><tr><th>№</th><th>Заказчик</th><th>Каналы</th><th>Публикация</th><th class="right">Сумма</th><th>Статус</th><th>Оплата</th></tr></thead><tbody>' + rows + "</tbody></table></div></div>";
      $$("tr[data-id]").forEach(function (tr) { tr.onclick = function () { openOrder(+tr.dataset.id); }; });
    }).catch(fail);
  };
  function openOrder(id) {
    api("/orders/" + id).then(function (o) {
      var m = modal({ title: "Заказ #" + o.id, wide: true, html: '<div class="grid-2"><div>' + postPreview(o) + "</div><div>" + orderKv(o) + "</div></div>" +
        '<div class="row wrap"><button type="button" class="btn secondary sm" id="oPrev">' + icon("send") + " Прислать мне в Telegram</button>" +
        (o.status === "moderation" ? '<a class="btn primary sm" href="#/moderation/' + o.id + '" id="oMod">' + icon("shield") + " Открыть в модерации</a>" : "") + "</div>" });
      $("#oPrev", m.el).onclick = function () { api("/orders/" + o.id + "/preview", { method: "POST" }).then(function () { toast("Пост отправлен вам в Telegram"); }).catch(fail); };
      var mod = $("#oMod", m.el); if (mod) mod.addEventListener("click", m.close);
    }).catch(fail);
  }

  // ---------------- Расписание ----------------
  PAGES.schedule = function (arg) {
    var test = arg === "test";
    setPage("Расписание", '<div class="tabs" style="margin:0;border:0"><a class="tab' + (test ? "" : " active") + '" href="#/schedule">Рабочие</a><a class="tab' + (test ? " active" : "") + '" href="#/schedule/test">🧪 Тестовые</a></div>');
    loading();
    api("/schedule" + (test ? "?test=1" : "")).then(function (rows) {
      if (!rows.length) { $("#page").innerHTML = '<div class="card">' + empty("calendar", "Ничего не запланировано", "Здесь появятся заказы с выбранным временем публикации.") + "</div>"; return; }
      var html = "", last = "";
      rows.forEach(function (o) {
        var day = fmtDay(o.publish_at);
        if (day !== last) { html += '<div class="day-head">' + esc(day) + "</div>"; last = day; }
        html += '<div class="sched-row clickable" data-id="' + o.id + '" style="cursor:pointer"><span class="time">' + fmtTime(o.publish_at) + '</span><span class="spacer">#' + o.id + " · " + esc(o.user_name || "") + ' <span class="muted small">— ' + esc(chNames(o, 4)) + "</span></span>" + statusBadge(o.status) + "</div>";
      });
      $("#page").innerHTML = '<div class="card flush"><div class="card__head"><div class="card__title">Ближайшие публикации</div><span class="spacer"></span><span class="small muted">⏰ оплаченные занимают время, остальные — ещё нет</span></div>' + html + "</div>";
      $$(".sched-row[data-id]").forEach(function (r) { r.onclick = function () { openOrder(+r.dataset.id); }; });
    }).catch(fail);
  };

  // ---------------- Каналы ----------------
  var chState = { q: "", filter: "all", page: 0, list: [] };
  var CH_PAGE = 25;
  PAGES.channels = function () {
    setPage("Каналы",
      '<button class="btn secondary sm" id="chRefresh">' + icon("refresh") + ' Обновить статистику</button>' +
      '<button class="btn secondary sm" id="chPrice">Цена для всех</button>' +
      '<button class="btn primary sm" id="chAdd">' + icon("plus") + " Добавить каналы</button>");
    $("#chAdd").onclick = addChannels;
    $("#chPrice").onclick = priceAll;
    $("#chRefresh").onclick = function () {
      var b = this; b.disabled = true; b.innerHTML = icon("refresh", "spin") + " Обновляю…";
      api("/channels/refresh-all", { method: "POST" }).then(function (r) { toast("Обновлено каналов: " + r.updated + (r.errors.length ? ", ошибок: " + r.errors.length : "")); loadChannels(); })
        .catch(fail).then(function () { b.disabled = false; b.innerHTML = icon("refresh") + " Обновить статистику"; });
    };
    loading();
    loadChannels();
  };
  function loadChannels() { return api("/channels").then(function (list) { chState.list = list; drawChannels(); }).catch(fail); }
  function chFiltered() {
    var q = chState.q.toLowerCase();
    return chState.list.filter(function (c) {
      if (q && (c.title + " " + (c.username || "") + " " + c.chat_id).toLowerCase().indexOf(q) < 0) return false;
      if (chState.filter === "visible") return c.visible;
      if (chState.filter === "hidden") return !c.active;
      if (chState.filter === "noadmin") return !c.bot_admin;
      if (chState.filter === "noprice") return !hasPrice(c);
      return true;
    });
  }
  function drawChannels() {
    var all = chState.list, list = chFiltered();
    var pages = Math.max(1, Math.ceil(list.length / CH_PAGE));
    chState.page = Math.min(chState.page, pages - 1);
    var items = list.slice(chState.page * CH_PAGE, (chState.page + 1) * CH_PAGE);
    var cnt = function (f) { return all.filter(f).length; };
    var filters = [["all", "Все", all.length], ["visible", "Видны покупателям", cnt(function (c) { return c.visible; })], ["hidden", "Скрыты", cnt(function (c) { return !c.active; })],
      ["noadmin", "Бот не админ", cnt(function (c) { return !c.bot_admin; })], ["noprice", "Без цены", cnt(function (c) { return !hasPrice(c); })]];
    var rows = items.map(function (c) {
      var status = !c.bot_admin ? '<span class="badge warning"><span class="dot"></span>Бот не админ</span>' : !c.active ? '<span class="badge"><span class="dot"></span>Скрыт</span>' :
        !hasPrice(c) ? '<span class="badge warning"><span class="dot"></span>Без цены</span>' : '<span class="badge success"><span class="dot"></span>Виден</span>';
      var err = c.avg_views && c.subscribers ? (c.avg_views / c.subscribers * 100).toFixed(1) + "%" : "—";
      return '<tr data-id="' + c.id + '"><td><div class="t-title">' + (c.public_link ? '<a href="' + esc(c.public_link) + '" target="_blank" rel="noopener">' + esc(c.title) + "</a>" : esc(c.title)) + '</div><div class="xs muted">' + (c.username ? "@" + esc(c.username) : esc(c.chat_id)) + "</div></td>" +
        '<td class="right num">' + fmtNum(c.subscribers) + '</td><td class="right num">' + (c.avg_views ? "~" + fmtNum(c.avg_views) : "—") + (c.views_manual ? ' <span class="xs muted">вручн.</span>' : "") + '</td><td class="right num">' + err + "</td>" +
        '<td class="right num nowrap">' + fmtPrice(c.price_stars, c.price_usd, c.price_rub) + "</td><td>" + status + "</td>" +
        '<td><div class="actions"><button class="btn ghost icon sm" data-a="link" title="Скопировать ссылку для канала">' + icon("link") + '</button><button class="btn ghost icon sm" data-a="edit" title="Изменить">' + icon("edit") + '</button><button class="btn ghost icon sm" data-a="refresh" title="Обновить данные">' + icon("refresh") + '</button><button class="btn ghost icon sm" data-a="toggle" title="' + (c.active ? "Скрыть" : "Показывать") + '">' + icon(c.active ? "eyeoff" : "eye") + '</button><button class="btn ghost icon sm" data-a="delete" title="Удалить">' + icon("trash") + "</button></div></td></tr>";
    }).join("");
    $("#page").innerHTML =
      '<div class="row wrap" style="margin-bottom:16px"><div class="search" style="width:280px">' + icon("search") + '<input class="input" id="chQ" placeholder="Поиск по названию, @username, ID" value="' + esc(chState.q) + '"></div>' +
      '<div class="tabs" style="margin:0;border:0">' + filters.map(function (f) { return '<button class="tab' + (chState.filter === f[0] ? " active" : "") + '" data-f="' + f[0] + '">' + f[1] + ' <span class="badge">' + f[2] + "</span></button>"; }).join("") + "</div></div>" +
      '<div class="card flush">' + (items.length ? '<div class="table-wrap"><table class="table"><thead><tr><th>Канал</th><th class="right">Подписчики</th><th class="right">Просмотры</th><th class="right">ERR</th><th class="right">Цена</th><th>Статус</th><th class="right">Действия</th></tr></thead><tbody>' + rows + "</tbody></table></div>" +
        '<div class="pager"><span>' + plural(list.length, "канал", "канала", "каналов") + '</span><div class="row"><button class="btn secondary sm" id="pPrev"' + (chState.page ? "" : " disabled") + '>Назад</button><span>' + (chState.page + 1) + " / " + pages + '</span><button class="btn secondary sm" id="pNext"' + (chState.page < pages - 1 ? "" : " disabled") + ">Вперёд</button></div></div>"
        : empty("megaphone", all.length ? "Ничего не найдено" : "Каналов пока нет", all.length ? "Измените поиск или фильтр." : "Добавьте бота админом в каналы — он найдёт их сам, или добавьте списком.",
          all.length ? "" : '<div style="margin-top:12px"><button class="btn primary" id="emptyAdd">' + icon("plus") + " Добавить каналы</button></div>")) + "</div>";
    var q = $("#chQ");
    q.oninput = function () { chState.q = q.value; chState.page = 0; var pos = q.selectionStart; drawChannels(); var n = $("#chQ"); n.focus(); n.setSelectionRange(pos, pos); };
    $$("[data-f]").forEach(function (b) { b.onclick = function () { chState.filter = b.dataset.f; chState.page = 0; drawChannels(); }; });
    if ($("#pPrev")) { $("#pPrev").onclick = function () { chState.page--; drawChannels(); }; $("#pNext").onclick = function () { chState.page++; drawChannels(); }; }
    if ($("#emptyAdd")) $("#emptyAdd").onclick = addChannels;
    $$("tr[data-id] [data-a]").forEach(function (b) {
      b.onclick = function () {
        var c = chState.list.filter(function (x) { return x.id === +b.closest("tr").dataset.id; })[0];
        channelAction(b.dataset.a, c, b);
      };
    });
  }
  function replaceChannel(c) { chState.list = chState.list.map(function (x) { return x.id === c.id ? c : x; }); drawChannels(); }
  function channelAction(a, c, btn) {
    if (a === "link") return copyText(c.link);
    if (a === "toggle") return api("/channels/" + c.id, { method: "PATCH", body: { active: !c.active } }).then(function (n) { replaceChannel(n); toast(n.active ? "Канал показывается" : "Канал скрыт"); }).catch(fail);
    if (a === "refresh") { btn.disabled = true; return api("/channels/" + c.id + "/refresh", { method: "POST" }).then(function (n) { replaceChannel(n); toast("Данные обновлены"); }).catch(function (e) { fail(e); btn.disabled = false; }); }
    if (a === "delete") return confirmBox("Удалить канал?", "Канал <b>" + esc(c.title) + "</b> пропадёт из каталога. Автообнаружение не вернёт его обратно — только ручное добавление.", "Удалить", true)
      .then(function (yes) { if (yes) api("/channels/" + c.id, { method: "DELETE" }).then(function () { chState.list = chState.list.filter(function (x) { return x.id !== c.id; }); drawChannels(); toast("Канал удалён"); }).catch(fail); });
    if (a === "edit") {
      modal({ title: c.title, submit: "Сохранить",
        html: '<div class="field"><label>Ссылка для размещения в канале</label><div class="row"><input class="input mono" readonly value="' + esc(c.link) + '"><button type="button" class="btn secondary icon" id="eCopy" title="Скопировать">' + icon("copy") + '</button><button type="button" class="btn secondary icon" id="eToken" title="Новая ссылка">' + icon("refresh") + "</button></div></div>",
        fields: [
          { name: "price_stars", label: "Цена, ⭐", type: "number", step: "1", value: c.price_stars || "", hint: "Telegram Stars." },
          { name: "price_usd", label: "Цена, $", type: "number", step: "0.01", value: c.price_usd || "", hint: "CryptoBot и xRocket." },
          { name: "price_rub", label: "Цена, ₽", type: "number", step: "0.01", value: c.price_rub || "", hint: "FreeKassa: СБП, карты, FKWallet. Пустое поле — оплату в этой валюте покупатель не увидит." },
          { name: "avg_views", label: "Просмотров на пост", type: "number", step: "1", value: c.views_manual ? c.avg_views : "", placeholder: "Авто: " + (c.avg_views || "нет данных"), hint: "Пусто — считать автоматически (только для публичных каналов)." },
          { name: "active", type: "checkbox", value: !!c.active, text: "Показывать покупателям" }
        ],
        onSubmit: function (v) {
          return api("/channels/" + c.id, { method: "PATCH", body: { price_usd: v.price_usd, price_stars: v.price_stars, price_rub: v.price_rub, avg_views: v.avg_views || null, active: v.active } })
            .then(function (n) { replaceChannel(n); toast("Сохранено"); });
        } });
      $("#eCopy").onclick = function () { copyText(c.link); };
      $("#eToken").onclick = function () {
        confirmBox("Новая ссылка?", "Старая ссылка перестанет работать — её нужно будет заменить в канале.", "Создать новую", true).then(function (yes) {
          if (!yes) return;
          api("/channels/" + c.id + "/token", { method: "POST" }).then(function (n) { replaceChannel(n); $$(".modal-back").forEach(function (m) { m.remove(); }); toast("Новая ссылка создана"); channelAction("edit", n); }).catch(fail);
        });
      };
    }
  }
  function addChannels() {
    var dp = state.summary ? state.summary.default_price : null;
    modal({ title: "Добавить каналы", submit: "Добавить", wide: true,
      html: '<p class="small muted">По одному каналу в строке: <code>@username</code>, ссылка <code>t.me/…</code> или ID <code>-100…</code>. Можно сразу с ценой через <code>|</code>: звёзды, доллары, рубли; <code>-</code> — валюта не принимается.' +
        " Без цены каналу ставится цена по умолчанию" + (dp ? " (" + esc(fmtPrice(dp.stars, dp.usd, dp.rub)) + ")" : "") + ". Бота можно добавить в каналы и позже — такие каналы будут помечены «бот не админ».</p>",
      fields: [{ name: "text", label: "Каналы", type: "textarea", rows: 10, placeholder: "@channel | 30 0.59 50\n@channel2 | - 5 450\nhttps://t.me/channel3\n-1001234567890" }],
      onSubmit: function (v, el) {
        $(".modal__body", el).insertAdjacentHTML("beforeend", '<div class="skeleton"></div><div class="small muted" id="addProg">Добавляю… это может занять до минуты.</div>');
        return api("/channels/bulk", { method: "POST", body: { text: v.text } }).then(function (r) {
          loadChannels();
          var html = "<p><b>Добавлено: " + r.added.length + "</b>" + (r.errors.length ? ", не добавлено: " + r.errors.length : "") + "</p>";
          if (r.added.some(function (c) { return !c.bot_admin; })) html += '<p class="small">⚠️ В части каналов бот пока не администратор — они скрыты от покупателей до его добавления.</p>';
          if (r.errors.length) html += '<div class="small">' + r.errors.map(function (e) { return "• <code>" + esc(e.line) + "</code> — " + esc(e.error); }).join("<br>") + "</div>";
          modal({ title: "Результат", html: html });
        });
      } });
  }
  function priceAll() {
    modal({ title: "Цена для всех каналов", submit: "Применить ко всем",
      html: '<p class="small muted">Цена будет выставлена всем ' + chState.list.length + " каналам сразу.</p>",
      fields: [{ name: "price_stars", label: "Цена, ⭐", type: "number", step: "1" }, { name: "price_usd", label: "Цена, $", type: "number", step: "0.01" },
        { name: "price_rub", label: "Цена, ₽", type: "number", step: "0.01", hint: "Пустое поле — оплату в этой валюте покупатель не увидит." }],
      onSubmit: function (v) { return api("/channels/price-all", { method: "POST", body: v }).then(function () { toast("Цена обновлена у всех каналов"); loadChannels(); }); } });
  }

  // ---------------- Ссылки ----------------
  var linkQ = "";
  PAGES.links = function () {
    setPage("Ссылки на каналы", '<a class="btn secondary sm" href="' + API + '/links.txt" download>' + icon("download") + ' Скачать .txt</a><button class="btn primary sm" id="lAll">' + icon("copy") + " Скопировать все</button>");
    loading();
    api("/channels").then(function (list) {
      function draw() {
        var q = linkQ.toLowerCase();
        var items = list.filter(function (c) { return !q || (c.title + " " + (c.username || "")).toLowerCase().indexOf(q) >= 0; });
        $("#page").innerHTML =
          '<div class="card" style="margin-bottom:16px"><p>Разместите ссылку в канале — в описании или закреплённом посте. По ней покупатель сразу попадает в бота на заказ рекламы <b>именно в этом канале</b>.</p></div>' +
          '<div class="row" style="margin-bottom:16px"><div class="search" style="width:320px">' + icon("search") + '<input class="input" id="lQ" placeholder="Поиск канала" value="' + esc(linkQ) + '"></div><span class="small muted">' + plural(items.length, "канал", "канала", "каналов") + "</span></div>" +
          '<div class="card flush">' + (items.length ? items.map(function (c) {
            return '<div class="link-row"><div class="link-row__title" title="' + esc(c.title) + '">' + (c.bot_admin ? "" : "⚠️ ") + esc(c.title) + '</div><div class="link-row__url">' + esc(c.link) + '</div><button class="btn secondary sm" data-copy="' + esc(c.link) + '">' + icon("copy") + " Копировать</button></div>";
          }).join("") : empty("link", "Каналов нет", "")) + "</div>";
        var inp = $("#lQ");
        inp.oninput = function () { linkQ = inp.value; var pos = inp.selectionStart; draw(); var n = $("#lQ"); n.focus(); n.setSelectionRange(pos, pos); };
        $$("[data-copy]").forEach(function (b) { b.onclick = function () { copyText(b.dataset.copy); }; });
      }
      $("#lAll").onclick = function () { copyText(list.map(function (c) { return c.title + " — " + c.link; }).join("\n")); };
      draw();
    }).catch(fail);
  };

  // ---------------- Обращения ----------------
  // адреса: #/support, #/support/<uid>, #/support/closed, #/support/closed-<uid>
  PAGES.support = function (arg) {
    var closed = arg.indexOf("closed") === 0;
    var uid = closed ? arg.replace(/^closed-?/, "") : arg;
    setPage("Обращения");
    loading();
    api("/support?status=" + (closed ? "closed" : "open")).then(function (threads) {
      var list = threads.map(function (t) {
        return '<a class="list-item' + (String(t.user_id) === uid ? " active" : "") + '" href="#/support/' + (closed ? "closed-" : "") + t.user_id + '"><div class="list-item__main"><div class="list-item__title">' + esc(t.user_name || t.user_id) + '</div><div class="list-item__sub">' + esc(t.last_text || "📎 вложение") + "</div></div>" +
          (t.unread ? '<span class="badge accent">' + t.unread + "</span>" : "") + "</a>";
      }).join("") || empty("inbox", closed ? "Закрытых диалогов нет" : "Обращений нет", closed ? "" : "Пользователи пишут через «💬 Связаться с нами» в боте.");
      $("#page").innerHTML = '<div class="split"><div class="card flush"><div class="tabs" style="margin:0;padding:0 16px"><a class="tab' + (closed ? "" : " active") + '" href="#/support">Открытые</a><a class="tab' + (closed ? " active" : "") + '" href="#/support/closed">Закрытые</a></div><div class="scroll">' + list + "</div></div>" +
        '<div class="card flush" id="thread" style="min-height:420px">' + (uid ? "" : empty("message", "Выберите диалог", "Слева — пользователи, которые написали в бот.")) + "</div></div>";
      if (uid) openThread(uid);
    }).catch(fail);
  };
  function openThread(uid) {
    var box = $("#thread");
    box.innerHTML = '<div style="padding:24px"><div class="skeleton"></div><div class="skeleton" style="width:60%"></div></div>';
    api("/support/" + uid).then(function (d) {
      var t = d.thread, isOpen = t.status === "open";
      var msgs = d.messages.map(function (m) {
        var media = "";
        if (m.has_file) {
          var src = API + "/support/media/" + m.id;
          media = m.media === "photo" ? '<img src="' + src + '" alt="" loading="lazy">' : (m.media === "video" || m.media === "animation") ? '<video src="' + src + '" controls muted preload="metadata"></video>' : '<div>📎 <a href="' + src + '" target="_blank">' + esc(m.media || "файл") + "</a></div>";
        } else if (m.media) media = '<div class="muted">📎 ' + esc(m.media) + "</div>";
        return '<div class="msg' + (m.from_admin ? " admin" : "") + '">' + media + esc(m.text || "") + '<div class="msg__meta">' + (m.from_admin ? "Вы" : "Пользователь") + " · " + fmtDate(m.created_at) + "</div></div>";
      }).join("");
      box.innerHTML = '<div class="card__head"><div><div class="card__title">' + esc(t.user_name || t.user_id) + '</div><div class="xs muted">ID ' + t.user_id + ' · <a href="tg://user?id=' + t.user_id + '">открыть в Telegram</a></div></div><span class="spacer"></span>' +
        '<button class="btn secondary sm" id="tStatus">' + (isOpen ? icon("check") + " Закрыть диалог" : "Открыть снова") + "</button></div>" +
        '<div class="chat" id="chat">' + (msgs || empty("message", "Сообщений нет", "")) + "</div>" +
        '<form class="composer" id="reply"><textarea class="textarea" id="replyText" placeholder="Ответ пользователю… (Ctrl+Enter — отправить)" required></textarea><button class="btn primary" type="submit">' + icon("send") + " Отправить</button></form>";
      var chat = $("#chat"); chat.scrollTop = chat.scrollHeight;
      statusPill();
      $("#tStatus").onclick = function () {
        api("/support/" + uid + "/status", { method: "POST", body: { status: isOpen ? "closed" : "open" } }).then(function () { toast(isOpen ? "Диалог закрыт" : "Диалог открыт"); location.hash = isOpen ? "#/support/closed-" + uid : "#/support/" + uid; }).catch(fail);
      };
      var ta = $("#replyText");
      ta.onkeydown = function (e) { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $("#reply").requestSubmit(); };
      $("#reply").onsubmit = function (e) {
        e.preventDefault();
        var text = ta.value.trim(); if (!text) return;
        var btn = $("#reply button"); btn.disabled = true;
        api("/support/" + uid + "/reply", { method: "POST", body: { text: text } }).then(function () { toast("Ответ отправлен"); openThread(uid); }).catch(function (err) { fail(err); btn.disabled = false; });
      };
    }).catch(fail);
  }

  // ---------------- Рассылка ----------------
  var BC_STATUS = { running: ["Идёт", "accent"], done: ["Завершена", "success"], stopped: ["Остановлена", ""], error: ["Ошибка", "danger"] };
  var bcTimer = null, bcTab = "panel";
  function bcSchedule(fn, ms) { clearTimeout(bcTimer); bcTimer = setTimeout(function () { if (route().page === "broadcast") fn(); }, ms); }
  function draftPreview(d) {
    // тот же вид, что у постов в модерации; вложение — из черновика
    var html = postPreview({ post: d.post, id: 0 });
    return html.split(API + "/orders/0/media").join(API + "/broadcast/draft/media?t=" + d.created_at);
  }
  function bar(done, total) {
    var pct = total ? Math.min(100, Math.round(done / total * 100)) : 0;
    return '<div class="progress"><div class="progress__fill" style="width:' + pct + '%"></div></div><div class="small muted" style="margin-top:6px">' + fmtNum(done) + " из " + fmtNum(total) + " · " + pct + "%</div>";
  }
  PAGES.broadcast = function () {
    setPage("Рассылка");
    loading();
    loadBroadcast();
  };
  function loadBroadcast() {
    return api("/broadcast").then(drawBroadcast).catch(fail);
  }
  function drawBroadcast(st) {
    if (route().page !== "broadcast") return;
    var au = st.audience, d = st.draft, running = st.history.filter(function (b) { return b.status === "running"; })[0];
    var capturing = !!st.capture_until, ck = st.check;

    var compose = '<div class="card"><div class="card__head"><div class="card__title">Новый пост</div></div>' +
      '<div class="tabs"><button class="tab' + (bcTab === "panel" ? " active" : "") + '" data-tab="panel">Написать здесь</button><button class="tab' + (bcTab === "tg" ? " active" : "") + '" data-tab="tg">Прислать в бота (@justpost)</button></div>' +
      (bcTab === "panel"
        ? '<form class="stack" id="bcForm"><div class="field"><label for="bcText">Текст</label><textarea class="textarea" id="bcText" rows="8" placeholder="Текст рекламного поста"></textarea>' +
          '<div class="hint">Форматирование — HTML как в Telegram: &lt;b&gt;жирный&lt;/b&gt;, &lt;i&gt;курсив&lt;/i&gt;, &lt;u&gt;, &lt;s&gt;, &lt;a href="https://…"&gt;ссылка&lt;/a&gt;, &lt;code&gt;, &lt;blockquote&gt;, &lt;tg-spoiler&gt;. С фото/видео — до 1024 символов, без — до 4096.</div></div>' +
          '<div class="field"><label for="bcFile">Фото, видео, GIF или файл</label><input class="input" id="bcFile" type="file" accept="image/*,video/*,.gif,.pdf,.zip" style="padding-top:7px"><div class="hint">Необязательно. До 20 МБ.</div></div>' +
          '<div class="field"><label for="bcButtons">Кнопки</label><textarea class="textarea" id="bcButtons" rows="3" style="min-height:72px" placeholder="Перейти в канал | https://t.me/channel"></textarea><div class="hint">Строка — ряд кнопок: <code>Текст | https://ссылка</code>. Две кнопки в одном ряду — через <code>;;</code>. Необязательно.</div></div>' +
          '<div><button class="btn primary" type="submit">' + icon("send") + " Сохранить и прислать мне в Telegram</button></div></form>"
        : '<div class="stack"><ol class="small" style="margin:0;padding-left:20px;line-height:1.8"><li>Нажмите «Жду пост».</li><li>В течение 10 минут отправьте боту <a href="https://t.me/' + esc(st.bot) + '" target="_blank">@' + esc(st.bot) + "</a> один пост: через <code>@justpost</code>, пересылкой или просто сообщением — с фото/видео и кнопками.</li><li>Пост появится здесь как черновик.</li></ol>" +
          (capturing
            ? '<div class="row wrap"><span class="badge accent"><span class="dot"></span>Жду пост в боте до ' + fmtTime(st.capture_until) + '</span><button class="btn secondary sm" id="bcCapStop">Отменить</button></div>'
            : '<div><button class="btn primary" id="bcCap">' + icon("inbox") + " Жду пост</button></div>") +
          '<p class="xs muted">Альбомы (несколько фото в одном посте) разослать нельзя. Команды вроде /start ботом обрабатываются как обычно.</p></div>') + "</div>";

    var draft = '<div class="card"><div class="card__head"><div class="card__title">Черновик</div>' + (d ? '<span class="badge">' + (d.source === "panel" ? "из панели" : "из Telegram") + " · " + fmtDate(d.created_at) + "</span>" : "") + "</div>" +
      (d
        ? '<div class="stack">' + draftPreview(d) +
          '<div class="field"><label for="bcBtnEdit">Кнопки под постом</label><textarea class="textarea" id="bcBtnEdit" rows="3" style="min-height:72px" placeholder="Без кнопок">' + esc(d.buttons_text) + '</textarea><div class="row"><button class="btn secondary sm" id="bcBtnSave">Сохранить кнопки</button><span class="xs muted">Формат — как при создании.</span></div></div>' +
          '<div class="row wrap"><button class="btn secondary sm" id="bcPrev">' + icon("send") + ' Прислать мне в Telegram</button><button class="btn ghost sm" id="bcDel">' + icon("trash") + " Удалить черновик</button></div>" +
          '<div class="row wrap" style="padding-top:8px;border-top:1px solid var(--border)"><button class="btn primary" id="bcGo"' + (running ? " disabled" : "") + ">" + icon("megaphone") + " Разослать " + plural(au.active, "пользователю", "пользователям", "пользователям") + "</button>" +
          (running ? '<span class="small muted">дождитесь окончания текущей рассылки</span>' : "") + "</div></div>"
        : empty("send", "Черновика нет", "Напишите пост слева или пришлите его в бота.")) + "</div>";

    var current = running
      ? '<div class="card" style="margin-bottom:20px"><div class="card__head"><div class="card__title">Идёт рассылка #' + running.id + '</div><span class="spacer"></span><button class="btn danger sm" id="bcStop" data-id="' + running.id + '">' + icon("stop") + " Остановить</button></div>" +
        bar(running.sent + running.blocked + running.failed, running.total) +
        '<div class="small" style="margin-top:8px">Доставлено: <b>' + running.sent + "</b> · заблокировали бота: " + running.blocked + " · ошибок: " + running.failed + "</div></div>"
      : "";

    var audience = '<div class="card"><div class="card__head"><div class="card__title">Аудитория</div></div>' +
      '<div class="tiles" style="margin:0 0 16px;grid-template-columns:repeat(3,1fr)">' +
      '<div class="tile"><div class="tile__label">Получат рассылку</div><div class="tile__value">' + fmtNum(au.active) + '</div><div class="tile__hint">не заблокировали бота</div></div>' +
      '<div class="tile"><div class="tile__label">Заблокировали</div><div class="tile__value">' + fmtNum(au.blocked) + "</div></div>" +
      '<div class="tile"><div class="tile__label">Всего</div><div class="tile__value">' + fmtNum(au.users) + '</div><div class="tile__hint">запусков: ' + fmtNum(au.starts) + "</div></div></div>" +
      (ck.running
        ? '<div class="small" style="margin-bottom:6px">Проверяю, кто заблокировал бота…</div>' + bar(ck.done, ck.total)
        : '<div class="row wrap"><button class="btn secondary sm" id="bcCheck">' + icon("users") + ' Проверить, кто заблокировал бота</button>' + (ck.finished_at ? '<span class="xs muted">последняя проверка ' + fmtDate(ck.finished_at) + ": заблокировали " + ck.blocked + "</span>" : "") + "</div>" +
          '<p class="xs muted" style="margin-top:8px">Блокировки бот замечает сам; проверка нужна для старых пользователей. Пользователям ничего не приходит — Telegram лишь на пару секунд может показать «печатает…».</p>') + "</div>";

    var history = st.history.length
      ? '<div class="card flush"><div class="card__head"><div class="card__title">История рассылок</div></div><div class="table-wrap"><table class="table"><thead><tr><th>№</th><th>Дата</th><th>Пост</th><th class="right">Получателей</th><th class="right">Доставлено</th><th class="right">Заблокировали</th><th class="right">Ошибок</th><th>Статус</th></tr></thead><tbody>' +
        st.history.map(function (b) {
          var s = BC_STATUS[b.status] || [b.status, ""];
          var text = b.post && b.post.html ? b.post.html.replace(/<[^>]+>/g, "") : (b.post ? b.post.kind : "");
          return "<tr><td class=\"num\">#" + b.id + '</td><td class="nowrap">' + fmtDate(b.created_at) + '</td><td class="t-title" title="' + esc(text) + '">' + esc(text.slice(0, 80) || "—") + '</td><td class="right num">' + b.total + '</td><td class="right num">' + b.sent + '</td><td class="right num">' + b.blocked + '</td><td class="right num">' + b.failed + "</td><td>" +
            '<span class="badge ' + s[1] + '"><span class="dot"></span>' + s[0] + "</span>" + (b.error ? '<div class="xs muted">' + esc(b.error) + "</div>" : "") + "</td></tr>";
        }).join("") + "</tbody></table></div></div>"
      : "";

    // форму не перерисовываем, пока в ней что-то набрано
    var form = $("#bcForm"), keep = form && ($("#bcText").value || $("#bcButtons").value || $("#bcFile").value);
    var editBtns = $("#bcBtnEdit"), keepBtns = editBtns && editBtns.value !== editBtns.defaultValue;
    if (keep || keepBtns) {
      var cur = $("#bcCurrent"); if (cur) cur.innerHTML = current;
      var aud = $("#bcAudience"); if (aud) { aud.innerHTML = audience; bindBroadcast(st); }
      var hist = $("#bcHistory"); if (hist) hist.innerHTML = history;
    } else {
      $("#page").innerHTML = '<div id="bcCurrent">' + current + '</div><div class="grid-2" style="margin-bottom:20px;align-items:start"><div class="stack">' + compose + '<div id="bcAudience">' + audience + "</div></div>" + draft + '</div><div id="bcHistory">' + history + "</div>";
      bindBroadcast(st);
    }
    if (running || capturing || ck.running) bcSchedule(loadBroadcast, capturing ? 3000 : 2000);
  }
  function bindBroadcast(st) {
    var on = function (id, fn) { var el = $(id); if (el) el.onclick = fn; };
    $$("[data-tab]").forEach(function (b) { b.onclick = function () { bcTab = b.dataset.tab; $("#page").innerHTML = ""; drawBroadcast(st); }; });
    var form = $("#bcForm");
    if (form) form.onsubmit = function (e) {
      e.preventDefault();
      var fd = new FormData(), file = $("#bcFile").files[0];
      fd.append("text", $("#bcText").value); fd.append("buttons", $("#bcButtons").value);
      if (file) { if (file.size > 20 * 1024 * 1024) return fail("Файл больше 20 МБ"); fd.append("file", file, file.name); }
      var btn = $('button[type="submit"]', form); btn.disabled = true; btn.innerHTML = icon("refresh", "spin") + " Отправляю…";
      fetch(API + "/broadcast/draft", { method: "POST", body: fd, headers: { "X-Panel": "1" }, credentials: "same-origin" })
        .then(function (r) { return r.json().catch(function () { return { ok: false, error: r.status === 413 ? "Файл слишком большой" : "Ошибка сервера (" + r.status + ")" }; }); })
        .then(function (d) {
          if (!d.ok) throw new Error(d.error || "Ошибка");
          toast("Черновик сохранён и отправлен вам в Telegram");
          form.reset(); loadBroadcast();
        }).catch(fail).then(function () { btn.disabled = false; btn.innerHTML = icon("send") + " Сохранить и прислать мне в Telegram"; });
    };
    on("#bcCap", function () { api("/broadcast/capture", { method: "POST", body: {} }).then(function () { toast("Жду пост в боте — отправьте его в течение 10 минут"); loadBroadcast(); }).catch(fail); });
    on("#bcCapStop", function () { api("/broadcast/capture", { method: "POST", body: { stop: true } }).then(loadBroadcast).catch(fail); });
    on("#bcBtnSave", function () { api("/broadcast/draft/buttons", { method: "PUT", body: { buttons: $("#bcBtnEdit").value } }).then(function () { toast("Кнопки сохранены"); $("#page").innerHTML = ""; loadBroadcast(); }).catch(fail); });
    on("#bcPrev", function () { api("/broadcast/draft/preview", { method: "POST" }).then(function () { toast("Пост отправлен вам в Telegram"); }).catch(fail); });
    on("#bcDel", function () { confirmBox("Удалить черновик?", "Пост останется в чате с ботом, но из панели пропадёт.", "Удалить", true).then(function (yes) { if (yes) api("/broadcast/draft", { method: "DELETE" }).then(function () { $("#page").innerHTML = ""; loadBroadcast(); }).catch(fail); }); });
    on("#bcGo", function () {
      var n = st.audience.active;
      confirmBox("Разослать пост?", "Пост получат <b>" + plural(n, "пользователь", "пользователя", "пользователей") + "</b> бота. Это займёт примерно " + Math.max(1, Math.ceil(n / 20 / 60)) + " мин. Отменить уже отправленные сообщения нельзя.", "Разослать")
        .then(function (yes) { if (yes) api("/broadcast/start", { method: "POST" }).then(function (r) { toast("Рассылка #" + r.id + " запущена"); $("#page").innerHTML = ""; loadBroadcast(); }).catch(fail); });
    });
    on("#bcStop", function () {
      var id = this.dataset.id;
      confirmBox("Остановить рассылку?", "Уже отправленные сообщения останутся у пользователей.", "Остановить", true).then(function (yes) { if (yes) api("/broadcast/" + id + "/stop", { method: "POST" }).then(function () { toast("Рассылка остановлена"); loadBroadcast(); }).catch(fail); });
    });
    on("#bcCheck", function () { api("/broadcast/check", { method: "POST" }).then(function () { toast("Проверка запущена"); loadBroadcast(); }).catch(fail); });
  }

  // ---------------- Настройки ----------------
  PAGES.settings = function () {
    setPage("Настройки");
    loading();
    api("/summary").then(function (s) {
      state.summary = s;
      $("#page").innerHTML = '<div class="grid-2">' +
        '<div class="card"><div class="card__head"><div class="card__title">Цена для новых каналов</div></div><p class="small muted" style="margin-bottom:16px">Ставится автоматически каналам, которые бот находит сам (когда его назначают админом или он видит пост), и при добавлении без цены.</p>' +
        '<form class="stack" id="dpForm"><div class="row"><div class="field" style="flex:1"><label for="dpStars">Цена, ⭐</label><input class="input" id="dpStars" type="number" step="1" value="' + (s.default_price.stars || "") + '"></div><div class="field" style="flex:1"><label for="dpUsd">Цена, $</label><input class="input" id="dpUsd" type="number" step="0.01" value="' + (s.default_price.usd || "") + '"></div><div class="field" style="flex:1"><label for="dpRub">Цена, ₽</label><input class="input" id="dpRub" type="number" step="0.01" value="' + (s.default_price.rub || "") + '"></div></div><p class="xs muted">Пустое поле — оплату в этой валюте покупатель не увидит.</p><div><button class="btn primary" type="submit">Сохранить</button></div></form></div>' +
        '<div class="card"><div class="card__head"><div class="card__title">Тестовый режим</div></div><p class="small" style="margin-bottom:12px">Включается у администратора в самом боте (кнопка «🧪 Тестовый режим»). Тестовые заказы публикуются только в тестовый канал и не попадают в статистику.</p>' +
        '<p class="small muted" style="margin-bottom:16px">Сейчас включён у: ' + (s.test_admins.length ? s.test_admins.map(function (a) { return "<code>" + a + "</code>"; }).join(", ") : "никого") + "</p>" +
        '<button class="btn danger" id="clearTest">' + icon("trash") + " Удалить тестовые заказы</button></div>" +
        '<div class="card"><div class="card__head"><div class="card__title">Премиум-эмодзи</div></div><p class="small" style="margin-bottom:12px">Telegram показывает премиум-эмодзи в каналах, только если у бота есть дополнительный юзернейм, купленный на <a href="https://fragment.com" target="_blank" rel="noopener noreferrer">Fragment</a> (за TON) и привязанный к боту. Без него в опубликованных постах они заменяются обычными эмодзи.</p>' +
        '<label class="row"><input type="checkbox" id="peOn"' + (s.premium_emoji ? " checked" : "") + "> У бота есть юзернейм с Fragment — премиум-эмодзи доступны</label>" +
        '<p class="xs muted" style="margin-top:12px">Выключено — покупатели видят, что премиум-эмодзи недоступны. Включено — что доступны, и посты (уже оплаченные тоже) публикуются с ними. То же самое — в боте: админ-панель → «✨ Премиум-эмодзи».</p></div>' +
        '<div class="card"><div class="card__head"><div class="card__title">Бот</div></div><dl class="kv"><dt>Telegram</dt><dd><a href="https://t.me/' + esc(s.bot) + '" target="_blank">@' + esc(s.bot) + "</a></dd><dt>Администраторы</dt><dd>" + s.admin_ids.map(function (a) { return "<code>" + a + "</code>"; }).join(", ") +
        "</dd><dt>Версия</dt><dd>" + esc(s.version) + "</dd><dt>Оплата</dt><dd>Stars ✓ · CryptoBot " + (s.payments.cryptobot ? "✓" : "—") + " · xRocket " + (s.payments.xrocket ? "✓" : "—") + " · FreeKassa " + (s.payments.freekassa ? "✓" : "—") + "</dd></dl></div>" +
        "</div>" + '<div id="botCfg" style="margin-top:20px"></div>';
      loadBotSettings();
      $("#dpForm").onsubmit = function (e) {
        e.preventDefault();
        api("/settings/default-price", { method: "PUT", body: { price_usd: $("#dpUsd").value, price_stars: $("#dpStars").value, price_rub: $("#dpRub").value } }).then(function () { toast("Цена для новых каналов сохранена"); }).catch(fail);
      };
      $("#peOn").onchange = function () {
        var box = this;
        api("/settings/premium-emoji", { method: "PUT", body: { on: box.checked } })
          .then(function (r) { toast(r.premium_emoji ? "Премиум-эмодзи включены" : "Премиум-эмодзи выключены"); })
          .catch(function (e) { box.checked = !box.checked; fail(e); });
      };
      $("#clearTest").onclick = function () {
        confirmBox("Удалить тестовые заказы?", "Все тестовые заказы и их брони времени будут удалены. Рабочие заказы не затрагиваются.", "Удалить", true).then(function (yes) {
          if (yes) api("/test/clear", { method: "POST" }).then(function (r) { toast("Удалено тестовых заказов: " + r.deleted); }).catch(fail);
        });
      };
    }).catch(fail);
  };

  // ---------------- Настройки бота и ключи платёжных систем ----------------
  var CFG_GROUPS = [
    { id: "cryptobot", title: "CryptoBot", pay: "cryptobot", text: "Оплата криптой в @CryptoBot (цены в $)." },
    { id: "xrocket", title: "xRocket Pay", pay: "xrocket", text: "Оплата криптой в @xRocket (цены в $)." },
    { id: "xrocket_hook", title: "xRocket — вебхук", pay: "xrocket_hook", on: "Включён", off: "Выключен (опрос)",
      text: "Необязательно. С вебхуком xRocket сам сообщает об оплате — заказ оплачивается за секунды. Без него бот проверяет счета каждые 20 секунд." },
    { id: "freekassa", title: "FreeKassa", pay: "freekassa", text: "Оплата в рублях: СБП, карты, FKWallet (цены в ₽)." },
    { id: "bot", title: "Параметры бота", text: "Применяются сразу. Токен бота — с перезапуском." }
  ];
  var SRC = { panel: ["из панели", "accent"], env: ["из .env", ""], "default": ["по умолчанию", ""] };
  function loadBotSettings() {
    api("/settings/bot").then(drawBotSettings).catch(function (e) { $("#botCfg").innerHTML = '<div class="card">' + esc(e.message) + "</div>"; });
  }
  function cfgInput(f) {
    var id = "cfg_" + f.key;
    if (f.kind === "bool") return '<label class="row"><input type="checkbox" id="' + id + '"' + (f.value ? " checked" : "") + "> " + esc(f.label) + "</label>";
    if (f.kind === "secret") return '<div class="row"><input class="input mono" id="' + id + '" type="password" autocomplete="new-password" placeholder="' + esc(f.set ? f.value + " — введите новый, чтобы заменить" : "не задан") + '">' +
      (f.set ? '<button type="button" class="btn secondary sm" data-clear="' + f.key + '" title="Удалить ключ">Очистить</button>' : "") + "</div>";
    return '<input class="input' + (f.kind === "ids" || f.kind === "chat" ? " mono" : "") + '" id="' + id + '" value="' + esc(f.value) + '">';
  }
  function hookHelp(pm) {
    var url = pm.xrocket_hook_url || "https://ваш-домен" + P + "/hook/xrocket";
    return '<ol class="small muted" style="margin:0 0 12px 18px;display:grid;gap:6px">' +
      "<li>Нужен домен с HTTPS, который ведёт на бота (Cloudflare Tunnel, nginx + Let&#39;s Encrypt и т. п.). " +
      "<b>Наружу открывайте только путь <code>" + esc(P) + "/hook/xrocket</code></b> — у панели нет пароля.</li>" +
      "<li>@xRocket → Pay API → ваше приложение → Settings: <b>API Version — Current</b>, <b>Webhook URL</b> — " +
      '<code>' + esc(url) + "</code>" + (pm.xrocket_hook_url ? ' <button type="button" class="btn ghost sm" data-copy="' + esc(url) + '">' + icon("copy") + "</button>" : "") +
      ", скопируйте <b>Webhook secret</b>.</li>" +
      "<li>Вставьте секрет и домен ниже → «Сохранить». Бот сам проверит, что адрес открывается из интернета; " +
      "вручную — откройте адрес в браузере, должно быть «xRocket webhook: ok».</li>" +
      "<li>Пока вебхук включён, бот на всякий случай перепроверяет счета раз в 10 минут. Очистить секрет — вернуться к опросу.</li></ol>" +
      (pm.xrocket_hook ? '<p class="small muted" style="margin-bottom:12px">Последний вебхук: ' + (pm.xrocket_hook_last ? fmtDate(pm.xrocket_hook_last) : "ещё не приходил") + "</p>" : "") +
      (pm.xrocket ? "" : '<p class="small" style="margin-bottom:12px">⚠️ Сначала подключите xRocket Pay (API Token) — без него вебхук не работает.</p>');
  }
  function drawBotSettings(d) {
    var box = $("#botCfg"); if (!box) return;
    var cards = CFG_GROUPS.map(function (g) {
      var fields = d.fields.filter(function (f) { return f.group === g.id; });
      var status = g.pay ? (d.payments[g.pay] ? '<span class="badge success"><span class="dot"></span>' + (g.on || "Подключено") + "</span>" : '<span class="badge"><span class="dot"></span>' + (g.off || "Не настроено") + "</span>") : "";
      var body = fields.map(function (f) {
        var src = SRC[f.source] || ["", ""];
        var meta = '<span class="badge ' + src[1] + '">' + src[0] + "</span>" + (f.source === "panel" ? ' <button type="button" class="btn ghost sm" data-reset="' + f.key + '" title="Убрать значение из панели — снова действует .env">вернуть из .env</button>' : "");
        return '<div class="field">' + (f.kind === "bool" ? "" : '<label for="cfg_' + f.key + '">' + esc(f.label) + "</label>") + cfgInput(f) +
          '<div class="hint">' + f.hint + " " + meta + "</div></div>";
      }).join("");
      return '<div class="card"><div class="card__head"><div class="card__title">' + esc(g.title) + '</div><span class="spacer"></span>' + status + "</div>" +
        '<p class="small muted" style="margin-bottom:12px">' + esc(g.text) + "</p>" + (g.id === "xrocket_hook" ? hookHelp(d.payments) : "") +
        '<form class="stack" data-group="' + g.id + '">' + body + '<div><button class="btn primary" type="submit">Сохранить</button></div></form></div>';
    }).join("");
    box.innerHTML = '<div class="card__title" style="margin-bottom:12px">Ключи и параметры бота</div>' +
      '<p class="small muted" style="margin-bottom:16px">Значения из панели важнее файла <code>.env</code>. Ключи платёжных систем проверяются при сохранении — неработающий не сохранится. Сохранённые ключи панель не показывает: видны только последние 4 символа.</p>' +
      '<div class="grid-2">' + cards + "</div>";
    var byKey = {}; d.fields.forEach(function (f) { byKey[f.key] = f; });
    $$("[data-copy]", box).forEach(function (b) { b.onclick = function () { copyText(b.dataset.copy); }; });
    $$("form[data-group]", box).forEach(function (form) {
      form.onsubmit = function (e) {
        e.preventDefault();
        var values = {};
        d.fields.filter(function (f) { return f.group === form.dataset.group; }).forEach(function (f) {
          var el = $("#cfg_" + f.key);
          if (f.kind === "bool") { if (el.checked !== !!f.value) values[f.key] = el.checked ? "true" : "false"; }
          else if (f.kind === "secret") { if (el.value.trim()) values[f.key] = el.value.trim(); }
          else if (el.value.trim() !== String(f.value)) values[f.key] = el.value.trim();
        });
        if (!Object.keys(values).length) return toast("Изменений нет");
        var go = function () { saveBotSettings({ method: "PUT", body: { values: values } }, $('button[type="submit"]', form)); };
        if (values.BOT_TOKEN) confirmBox("Сменить токен бота?", "Бот перезапустится с новым токеном (≈10 секунд). Если это другой бот — назначьте его админом в каналах, иначе он не сможет публиковать.", "Сменить и перезапустить", true).then(function (yes) { if (yes) go(); });
        else go();
      };
    });
    $$("[data-clear]", box).forEach(function (b) {
      b.onclick = function () {
        var f = byKey[b.dataset.clear];
        confirmBox("Очистить «" + f.label + "»?", f.group === "bot" ? "Значение будет удалено." : f.group === "xrocket_hook" ? "Вебхук выключится (секрет и домен), оплаты xRocket снова будут проверяться опросом каждые 20 секунд." : "Оплата этим способом выключится сразу.", "Очистить", true).then(function (yes) {
          if (!yes) return;
          var v = {}; v[f.key] = "";
          if (f.group === "xrocket_hook") { v.XROCKET_WEBHOOK_TOKEN = ""; v.XROCKET_WEBHOOK_DOMAIN = ""; }
          saveBotSettings({ method: "PUT", body: { values: v } }, b);
        });
      };
    });
    $$("[data-reset]", box).forEach(function (b) {
      b.onclick = function () {
        var f = byKey[b.dataset.reset];
        confirmBox("Вернуть «" + f.label + "» из .env?", "Значение из панели удалится, снова будет действовать файл .env на сервере." + (f.key === "BOT_TOKEN" ? " Бот перезапустится." : ""), "Вернуть", f.key === "BOT_TOKEN").then(function (yes) {
          if (yes) saveBotSettings({ method: "DELETE", path: "/" + f.key }, b);
        });
      };
    });
  }
  function saveBotSettings(req, btn) {
    if (btn) btn.disabled = true;
    api("/settings/bot" + (req.path || ""), { method: req.method, body: req.body }).then(function (r) {
      var bad = Object.keys(r.verify || {}).filter(function (k) { return r.verify[k]; });
      if (bad.length) toast("Сохранено, но не подключилось: " + bad.map(function (k) { return k + " — " + r.verify[k]; }).join("; "), true);
      else toast("Сохранено");
      if (r.restart) return waitRestart();
      drawBotSettings(r);
    }).catch(function (e) { fail(e); if (btn) btn.disabled = false; });
  }
  function waitRestart() {
    $("#botCfg").innerHTML = '<div class="card"><div class="skeleton" style="width:40%"></div><p class="small">Бот перезапускается с новым токеном… страница обновится сама.</p></div>';
    var tries = 0;
    setTimeout(function poll() {
      fetch(API + "/health", { credentials: "same-origin" }).then(function (r) { if (!r.ok) throw 0; location.reload(); })
        .catch(function () { if (++tries < 40) setTimeout(poll, 3000); else toast("Бот не поднялся за 2 минуты — проверьте логи контейнера", true); });
    }, 5000);
  }

  // ---------------- старт ----------------
  window.addEventListener("hashchange", render);
  fetch(API + "/auth", { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (d) {
    state.auth = !!(d.data && d.data.logged_in);
    render();
  }).catch(function () { render(); });
  setInterval(function () { if (state.auth && $(".sidebar")) statusPill(); }, 30000);
})();
