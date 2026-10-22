"use strict";

// ---------- состояние ----------
const S = {
  accounts: new Map(),      // id -> account
  scope: "",                // "" = все аккаунты, иначе id аккаунта
  folder: "main",           // main | unread | archive | id папки панели (число)
  folders: [],              // папки панели: [{id, name, items: [{account_id, chat_id}]}]
  dialogs: [],
  current: null,            // {account_id, id, title, type, can_send, ...}
  messages: [],
  replyTo: null,
  editing: null,
  unseen: 0,                // новые сообщения, пришедшие пока лента прокручена вверх
  ghost: readPref("ghost", "1") === "1",
  lan: null,                // веб-панель из локальной сети: {name, url, proxy_port} из /api/session
  view: "chats",            // chats | lan
};
const COLORS = ["#4f8cff", "#2ecc8f", "#f5a524", "#f2555a", "#a36cf7",
                "#12a4b8", "#f76b15", "#d6409f", "#8d9b2a", "#6e56cf"];
const SKIP_DIRS = ["user_data", "emoji", "dumps", "temp", "tdummy", "webview"];
const GROUP_GAP = 5 * 60;   // сообщения одного автора ближе 5 минут склеиваются в группу

const $ = (s, root = document) => root.querySelector(s);
const key = (aid, cid) => `${aid}:${cid}`;

function readPref(k, def) { try { return localStorage.getItem(k) ?? def; } catch { return def; } }
function writePref(k, v) { try { localStorage.setItem(k, v); } catch { /* приватный режим */ } }

// ---------- иконки ----------
const ICONS = {
  plane: '<path class="f" d="M21.5 4.5 2.8 11.7c-.9.4-.9 1.6 0 1.9l4.7 1.6 1.8 5.6c.2.7 1.1.9 1.6.4l2.7-2.6 4.8 3.5c.6.4 1.4.1 1.6-.6l3-15.5c.2-.9-.7-1.6-1.5-1.3z"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5z"/><path d="m3 13 9 5 9-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  ghost: '<path d="M3 3l18 18"/><path d="M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.1M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
  clip: '<path d="m21 11-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.6-8.6a3.7 3.7 0 0 1 5.2 5.2l-8.6 8.6a1.8 1.8 0 0 1-2.6-2.6L15 7"/>',
  send: '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/>',
  reply: '<path d="M9 17 4 12l5-5"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  pin: '<path d="M12 17v5"/><path d="M9 3h6l-1 6 4 4v2H6v-2l4-4z"/>',
  trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  back: '<path d="m15 18-6-6 6-6"/>',
  down: '<path d="M12 5v14M19 12l-7 7-7-7"/>',
  channel: '<path d="M3 11v2a1 1 0 0 0 1 1h3l6 4V6L7 10H4a1 1 0 0 0-1 1z"/><path d="M17 8a5 5 0 0 1 0 8"/>',
  group: '<circle cx="9" cy="8" r="4"/><path d="M2 21a7 7 0 0 1 14 0"/><path d="M16 4a4 4 0 0 1 0 8M22 21a7 7 0 0 0-4-6.3"/>',
  bot: '<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 8V4M9 13h.01M15 13h.01"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  muted: '<path d="M3 3l18 18"/><path d="M18 8a6 6 0 0 0-9.3-5M6 8c0 7-3 9-3 9h14"/><path d="M10.3 21a2 2 0 0 0 3.4 0"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  monitor: '<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  zip: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M10 4h1M10 7h1M10 10h1M10 13v3h1v-3z"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  msg: '<path d="M21 12a8 8 0 0 1-11.6 7.2L3 21l1.8-6.4A8 8 0 1 1 21 12z"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
  at: '<circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.9 7.9"/>',
  hash: '<path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/>',
  door: '<path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/><path d="M10 17l-5-5 5-5M5 12h11"/>',
  alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a2 2 0 0 0 3.4 0"/>',
  archive: '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9M10 13h4"/>',
  folderPlus: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 10v6M9 13h6"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  server: '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M11 6.5h6M11 17.5h6"/>',
  external: '<path d="M14 3h7v7"/><path d="M21 3 10 14"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/>',
};
function icon(name, cls = "") {
  const body = ICONS[name] || "";
  const filled = name === "more" || name === "plane";
  return `<svg class="i ${filled ? "fill" : ""} ${cls}" viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
}
function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach(el => { if (!el.firstChild) el.innerHTML = icon(el.dataset.icon); });
}

// ---------- форматирование ----------
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function linkify(text) {
  return esc(text).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
}
// Только http(s), tg:, mailto: и tel: — ссылки вида javascript: из сообщений не пропускаем
function safeUrl(raw) {
  const s = String(raw || "").trim();
  const withScheme = /^[a-z][a-z0-9+.-]*:/i.test(s) ? s : `https://${s}`;
  try {
    const u = new URL(withScheme);
    return ["http:", "https:", "tg:", "mailto:", "tel:"].includes(u.protocol) ? u.href : "";
  } catch { return ""; }
}
function extLink(url, inner) {
  const href = safeUrl(url);
  return href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${inner}</a>` : inner;
}
function wrapEntity(e, inner, raw) {
  switch (e.type) {
    case "bold": return `<b>${inner}</b>`;
    case "italic": return `<i>${inner}</i>`;
    case "underline": return `<u>${inner}</u>`;
    case "strike": return `<s>${inner}</s>`;
    case "code": return `<code>${inner}</code>`;
    case "pre": return `<pre><code>${inner}</code></pre>`;
    case "quote": return `<blockquote>${inner}</blockquote>`;
    case "spoiler": return `<span class="spoiler" title="Спойлер — нажмите, чтобы показать">${inner}</span>`;
    case "link": return extLink(e.url, inner);
    case "url": return extLink(raw, inner);
    case "email": return `<a href="mailto:${esc(raw)}">${inner}</a>`;
    case "phone": return `<a href="tel:${esc(raw.replace(/[^\d+]/g, ""))}">${inner}</a>`;
    case "mention": return extLink(`https://t.me/${raw.replace(/^@/, "")}`, inner);
    case "mention_name": case "hashtag": case "command": return `<span class="tag">${inner}</span>`;
    default: return inner;
  }
}
// Текст с форматированием Telegram. Сущности вкладываются деревом, чтобы цитата с жирным словом
// внутри осталась одной цитатой, а не развалилась на куски
function renderText(text, entities) {
  if (!text) return "";
  if (!entities?.length) return linkify(text);
  const list = entities.map(e => ({ ...e, end: e.offset + e.length })).sort((a, b) => a.offset - b.offset || b.end - a.end);
  let i = 0;
  function build(start, end) {
    let out = "", pos = start;
    while (i < list.length && list[i].offset < end) {
      const e = list[i++];
      const s = Math.max(e.offset, pos), en = Math.min(e.end, end);
      if (s >= en) continue;
      out += esc(text.slice(pos, s));
      out += wrapEntity(e, build(s, en), text.slice(e.offset, e.end));
      pos = en;
    }
    return out + esc(text.slice(pos, end));
  }
  return build(0, text.length);
}
function initials(name) {
  const parts = String(name || "?").replace(/[^\p{L}\p{N}\s]/gu, "").trim().split(/\s+/);
  return ((parts[0]?.[0] || "?") + (parts[1]?.[0] || "")).toUpperCase();
}
function fmtClock(ts) { return new Date(ts * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" }); }
function fmtTime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000), now = new Date();
  if (d.toDateString() === now.toDateString()) return fmtClock(ts);
  if (now - d < 6 * 864e5) return d.toLocaleDateString("ru", { weekday: "short" });
  return d.toLocaleDateString("ru", { day: "2-digit", month: "2-digit", year: "2-digit" });
}
function fmtSize(n) {
  if (!n) return "";
  const u = ["Б", "КБ", "МБ", "ГБ"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}
const MEDIA_LABEL = {
  photo: "Фото", video: "Видео", gif: "GIF", round: "Видеосообщение", voice: "Голосовое сообщение",
  audio: "Аудио", file: "Файл", sticker: "Стикер", poll: "Опрос", geo: "Геопозиция", contact: "Контакт",
  webpage: "Ссылка",
};
const mediaLabel = t => MEDIA_LABEL[t] || "Медиа";
function toast(text, err = false) {
  const t = $("#toast");
  t.innerHTML = `<span class="ti">${icon(err ? "alert" : "check")}</span><span>${esc(text)}</span>`;
  t.className = "toast" + (err ? " err" : ""); t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => (t.hidden = true), err ? 6000 : 2800);
}

// ---------- подсказки ----------
let tipEl = null;
document.addEventListener("mouseover", e => {
  const host = e.target.closest("[data-tip]");
  if (!host) { tipEl?.remove(); tipEl = null; return; }
  if (tipEl?.dataset.for === host.dataset.tip) return;
  tipEl?.remove();
  const r = host.getBoundingClientRect();
  tipEl = document.createElement("div");
  tipEl.className = "tip"; tipEl.dataset.for = host.dataset.tip; tipEl.textContent = host.dataset.tip;
  tipEl.style.left = `${r.right + 12}px`; tipEl.style.top = `${r.top + r.height / 2}px`;
  document.body.appendChild(tipEl);
});

// ---------- API ----------
async function api(path, { method = "GET", body, form } = {}) {
  const opts = { method, headers: {} };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, opts);
  if (r.status === 401 && !path.startsWith("/api/login")) { showLogin(); throw new Error("Нужен вход"); }
  const data = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
  if (!r.ok) {
    const d = data?.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : `Ошибка ${r.status}`);
  }
  return data;
}
const acc = id => S.accounts.get(Number(id));
const chatPath = (aid, cid) => `/api/accounts/${aid}/chats/${cid}`;
function peerColor(id) { return COLORS[Math.abs(Number(id)) % COLORS.length]; }

// Аватар грузится, только когда попадает на экран (в длинных списках это сотни картинок)
const avatarObserver = new IntersectionObserver(entries => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    avatarObserver.unobserve(e.target);
    loadAvatar(e.target);
  }
}, { rootMargin: "200px" });
const avatarMissing = new Set();
function loadAvatar(el) {
  const src = el.dataset.src;
  if (avatarMissing.has(src)) return;
  const img = new Image();
  img.alt = "";
  img.onload = () => { el.textContent = ""; el.appendChild(img); };
  img.onerror = () => avatarMissing.add(src);
  img.src = src;
}
function avatarEl(aid, peer, name, color, cls = "") {
  const el = document.createElement("div");
  el.className = "avatar " + cls;
  el.style.setProperty("--c", color || COLORS[0]);
  el.textContent = initials(name);
  if (aid != null) {
    const v = avatarVersion.get(key(aid, peer));
    el.dataset.src = `/api/accounts/${aid}/avatar/${peer}${v ? `?v=${v}` : ""}`;
    if (!avatarMissing.has(el.dataset.src)) avatarObserver.observe(el);
  }
  return el;
}
// Браузер кэширует аватар на час — после смены фото добавляем к адресу версию
const avatarVersion = new Map();
function bumpAvatar(aid, peer) {
  avatarMissing.delete(`/api/accounts/${aid}/avatar/${peer}`);
  avatarVersion.set(key(aid, peer), Date.now());
}
// Аватар с карандашом: нажатие открывает выбор картинки, onFile загружает её
function editableAvatar(avatarNode, onFile) {
  const wrap = document.createElement("label");
  wrap.className = "ava-edit";
  wrap.title = "Сменить аватар";
  wrap.append(avatarNode);
  wrap.insertAdjacentHTML("beforeend", `<span class="pen">${icon("edit")}</span><input type="file" accept="image/*" hidden>`);
  wrap.querySelector("input").onchange = async e => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    wrap.classList.add("loading");
    try { await onFile(f); } catch (ex) { toast(ex.message, true); }
    wrap.classList.remove("loading");
  };
  return wrap;
}

// ---------- вход ----------
function showLogin() { $("#app").hidden = true; $("#login").hidden = false; $("#login-password").focus(); }
$("#login-form").addEventListener("submit", async e => {
  e.preventDefault();
  $("#login-error").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: { password: $("#login-password").value } });
    $("#login-password").value = "";
    start();
  } catch (err) { $("#login-error").textContent = err.message; }
});
$("#logout").onclick = async () => { await api("/api/logout", { method: "POST" }); location.reload(); };

// ---------- аккаунты (рейка) ----------
async function loadAccounts() {
  const list = await api("/api/accounts");
  S.accounts = new Map(list.map(a => [a.id, a]));
  renderRail();
}
function statusText(a) {
  return { online: "В сети", connecting: "Подключение…", offline: "Не подключён", error: "Ошибка: " + (a.error || "") }[a.status] || a.status;
}
function accountLine(a) {
  return [a.username && "@" + a.username, a.phone && "+" + a.phone].filter(Boolean).join(" · ");
}
function renderRail() {
  const box = $("#rail-accounts");
  box.innerHTML = "";
  for (const a of S.accounts.values()) {
    const b = document.createElement("button");
    b.className = "rail-item acc" + (S.view === "chats" && String(S.scope) === String(a.id) ? " active" : "");
    b.dataset.tip = `${a.name}\n${accountLine(a) || a.full_name || ""}\n${statusText(a)}`.replace(/\n+/g, "\n").trim();
    b.style.setProperty("--c", a.color);
    b.appendChild(avatarEl(a.status === "online" ? a.id : null, "me", a.full_name || a.name, a.color));
    b.insertAdjacentHTML("beforeend", `<span class="dot ${a.status}"></span>`);
    const unread = S.dialogs.filter(d => d.account_id === a.id && d.unread && !d.muted).length;
    if (unread && S.scope === "") b.insertAdjacentHTML("beforeend", `<span class="badge">${unread > 99 ? "99+" : unread}</span>`);
    b.onclick = () => setScope(a.id);
    b.oncontextmenu = e => { e.preventDefault(); accountMenu(a.id); };
    box.appendChild(b);
  }
  $(".rail-item.all").classList.toggle("active", S.view === "chats" && S.scope === "");
  $("#lan-open").classList.toggle("active", S.view === "lan");
  renderScope();
}
function renderScope() {
  const a = acc(S.scope);
  $("#scope-title").textContent = a ? a.name : "Все аккаунты";
  $("#scope-sub").textContent = a ? [accountLine(a), statusText(a)].filter(Boolean).join(" · ")
    : S.accounts.size ? `${[...S.accounts.values()].filter(x => x.status === "online").length} из ${S.accounts.size} в сети` : "";
  $("#account-menu").hidden = !a;
}
$(".rail-item.all").onclick = () => setScope("");
function setScope(id) {
  const scope = id === "" ? "" : Number(id);
  const fromLan = S.view === "lan";
  if (fromLan) showLan(false);
  if (fromLan && scope === S.scope) return;  // вернулись к тому же списку — он обновлялся по событиям
  S.scope = scope;
  S.dialogs = [];
  renderRail();
  loadDialogs();
}
$("#account-menu").onclick = () => accountMenu(S.scope);

// ---------- веб-панель из локальной сети ----------
function lanFrameUrl(p) {
  // Сайт запрещает встраивание, поэтому iframe смотрит на прокси TG Panel на отдельном порту
  // (app/lan_proxy.py). Со страницы по https iframe на http заблокирует браузер — тогда новая вкладка.
  if (!p.proxy_port || location.protocol !== "http:") return "";
  const u = new URL(p.url);
  return `http://${location.hostname}:${p.proxy_port}${u.pathname}${u.search}`;
}
function setupLan(p) {
  S.lan = p || null;
  $("#lan-open").hidden = !S.lan;
  if (!S.lan) { if (S.view === "lan") showLan(false); return; }
  const host = new URL(S.lan.url).host;
  $("#lan-open").dataset.tip = `${S.lan.name}\n${host}`;
  $("#lan-open").setAttribute("aria-label", S.lan.name);
  $("#lan-title").textContent = S.lan.name;
  $("#lan-sub").textContent = `${host} · локальная сеть`;
  $("#lan-tab").href = S.lan.url;
}
function showLan(on) {
  S.view = on ? "lan" : "chats";
  $("#app").classList.toggle("lan-mode", on);
  $("#lan").hidden = !on;
  renderRail();
}
$("#lan-open").onclick = () => {
  const src = lanFrameUrl(S.lan);
  if (!src) { window.open(S.lan.url, "_blank", "noopener"); return; }
  const f = $("#lan-frame");
  // src ставим один раз: при возврате из чатов панель остаётся на той же странице
  if (f.dataset.src !== src) { f.dataset.src = src; f.src = src; }
  showLan(true);
};
$("#lan-back").onclick = () => showLan(false);
$("#lan-reload").onclick = () => { const f = $("#lan-frame"); f.src = f.dataset.src || "about:blank"; };

// ---------- диалоги ----------
let dialogsReq = 0;
function skeletonDialogs(n = 9) {
  return Array.from({ length: n }, () => `<div class="skel-dialog"><div class="skel c"></div><div><div class="skel l1"></div><div class="skel l2"></div></div></div>`).join("");
}
async function loadDialogs() {
  const req = ++dialogsReq;
  const params = new URLSearchParams({ archived: S.folder === "archive", limit: 100 });
  if (S.scope !== "") params.set("account_id", S.scope);
  if (typeof S.folder === "number") params.set("folder_id", S.folder);
  if (!S.dialogs.length) $("#dialog-list").innerHTML = skeletonDialogs();
  try {
    const list = await api(`/api/dialogs?${params}`);
    if (req !== dialogsReq) return;
    S.dialogs = list;
    renderDialogs();
    renderRail();
  } catch (e) { if (req === dialogsReq) $("#dialog-list").innerHTML = emptyState("alert", e.message); }
}
let reloadTimer;
function reloadDialogsSoon() { clearTimeout(reloadTimer); reloadTimer = setTimeout(loadDialogs, 700); }
function emptyState(ic, text) { return `<div class="empty-list">${icon(ic)}<div>${esc(text)}</div></div>`; }

function previewHtml(d) {
  const you = d.last_out ? '<span class="you">Вы: </span>' : "";
  if (d.last_action) return `<span class="media-label">${esc(d.last_action)}</span>`;
  const label = d.last_media && d.last_media !== "webpage" ? `<span class="media-label">${mediaLabel(d.last_media)}${d.last_text ? ", " : ""}</span>` : "";
  return you + label + esc(d.last_text);
}
const TYPE_ICON = { channel: "channel", group: "group", bot: "bot" };
function renderDialogs() {
  const q = $("#dialog-filter").value.trim().toLowerCase();
  let list = S.dialogs;
  if (S.folder === "unread") list = list.filter(d => d.unread > 0);
  if (q) list = list.filter(d => d.title.toLowerCase().includes(q) || (d.username || "").toLowerCase().includes(q));
  const box = $("#dialog-list");
  if (!list.length) {
    box.innerHTML = !S.accounts.size ? emptyState("plus", "Добавьте первый аккаунт кнопкой «+» слева")
      : q ? emptyState("search", "Ничего не найдено")
      : S.folder === "unread" ? emptyState("check", "Всё прочитано")
      : typeof S.folder === "number" ? emptyState("folder", "Папка пуста. Нажмите на чат правой кнопкой → «Добавить в папку»")
      : emptyState("msg", "Чатов нет");
    return;
  }
  box.innerHTML = "";
  const frag = document.createDocumentFragment();
  const all = S.scope === "";
  for (const d of list) {
    const a = acc(d.account_id) || { color: "#888", name: "?" };
    const el = document.createElement("div");
    const active = S.current && key(S.current.account_id, S.current.id) === key(d.account_id, d.id);
    el.className = "dialog" + (active ? " active" : "") + (d.unread ? " has-unread" : "");
    el.style.setProperty("--c", a.color);
    el.dataset.key = key(d.account_id, d.id);
    el.appendChild(avatarEl(d.account_id, d.id, d.title, peerColor(d.id)));
    const typeIcon = TYPE_ICON[d.type] ? icon(TYPE_ICON[d.type]) : "";
    const flags = [d.muted ? icon("muted") : "", d.pinned && !all ? icon("pin") : ""].join("");
    el.insertAdjacentHTML("beforeend", `
      ${all ? '<span class="acc-mark"></span>' : ""}
      <div>
        <div class="d-row">
          <span class="d-name">${typeIcon}<span class="t">${esc(d.title)}</span></span>
          ${all ? `<span class="chip" style="--c:${a.color}">${esc(a.name)}</span>` : ""}
          <span class="d-time">${fmtTime(d.date)}</span>
        </div>
        <div class="d-row">
          <span class="d-text">${previewHtml(d)}</span>
          <span class="d-flags">${flags}${d.unread ? `<span class="badge ${d.muted ? "dim" : ""}">${d.unread > 999 ? "999+" : d.unread}</span>` : ""}</span>
        </div>
      </div>`);
    el.onclick = () => openChat(d);
    // правый клик мышью, долгое нажатие на телефоне
    el.oncontextmenu = e => { e.preventDefault(); dialogMenu(d, e.clientX, e.clientY); };
    frag.appendChild(el);
  }
  box.appendChild(frag);
}
$("#dialog-filter").addEventListener("input", renderDialogs);

// ---------- чат ----------
async function openChat(d) {
  S.current = { ...d, can_send: d.type !== "channel" || d.is_admin };
  S.messages = []; S.replyTo = null; S.editing = null; S.unseen = 0; atBottom = true;
  updateReplyBar(); updateToBottom();
  $("#chat").classList.remove("empty");
  document.querySelectorAll(".dialog").forEach(el => el.classList.toggle("active", el.dataset.key === key(d.account_id, d.id)));
  renderChatHead();
  $("#messages").innerHTML = Array.from({ length: 7 }, (_, i) =>
    `<div class="skel skel-msg" style="width:${30 + (i * 37) % 45}%;align-self:${i % 3 ? "flex-start" : "flex-end"}"></div>`).join("");
  const cur = S.current;
  try {
    const msgs = await api(`${chatPath(d.account_id, d.id)}/messages?limit=40`);
    if (S.current !== cur) return;
    S.messages = msgs;
    renderMessages(true);
    if (!S.ghost && d.unread) markRead(d);
  } catch (e) { $("#messages").innerHTML = emptyState("alert", e.message); }
  api(chatPath(d.account_id, d.id)).then(info => {
    if (S.current !== cur) return;
    Object.assign(S.current, info);
    renderChatHead();
  }).catch(() => {});
  if (matchMedia("(min-width: 861px)").matches) $("#composer-text").focus();
}
function renderChatHead() {
  const c = S.current, a = acc(c.account_id) || {};
  const head = $(".chat-avatar");
  head.innerHTML = "";
  head.appendChild(avatarEl(c.account_id, c.id, c.title, peerColor(c.id), "sm"));
  $(".chat-title").textContent = c.title;
  const kind = { user: "пользователь", bot: "бот", group: "группа", channel: "канал" }[c.type] || "";
  const extra = c.members ? `${c.members.toLocaleString("ru")} участн.` : c.username ? `@${c.username}` : kind;
  $(".chat-sub").innerHTML = `<span class="chip" style="--c:${a.color}">${esc(a.name || "")}</span><span>${esc(extra)}</span>`;
  $("#composer").hidden = !c.can_send;
  $("#readonly-bar").hidden = c.can_send;
}
async function markRead(d) {
  try {
    await api(`${chatPath(d.account_id, d.id)}/read`, { method: "POST" });
    const item = S.dialogs.find(x => x.account_id === d.account_id && x.id === d.id);
    if (item) { item.unread = 0; renderDialogs(); renderRail(); }
  } catch (e) { toast(e.message, true); }
}
$("#chat-back").onclick = () => { $("#chat").classList.add("empty"); S.current = null; renderDialogs(); };

const VISUAL = new Set(["photo", "video", "gif", "round", "sticker"]);
// Размер известен заранее — место под картинку резервируется, и лента не прыгает при загрузке
function sizeAttr(md, maxW = 520, maxH = 380) {
  if (!md.w || !md.h) return "";
  const k = Math.min(1, maxW / md.w, maxH / md.h);
  return ` width="${Math.round(md.w * k)}" height="${Math.round(md.h * k)}" style="aspect-ratio:${md.w}/${md.h}"`;
}
function mediaHtml(m) {
  const md = m.media; if (!md) return "";
  const src = `${chatPath(m.account_id, m.chat_id)}/messages/${m.id}/media`;
  switch (md.type) {
    case "photo": return `<a href="${src}" target="_blank"><img loading="lazy" src="${src}" alt=""${sizeAttr(md)}></a>`;
    case "sticker": return md.mime === "image/webp" ? `<img class="sticker" loading="lazy" src="${src}" alt="стикер"${sizeAttr(md, 170, 170)}>` : `<div class="misc muted">Стикер</div>`;
    case "gif": case "round": return `<video src="${src}" autoplay loop muted playsinline preload="metadata"${sizeAttr(md, 360, 360)}></video>`;
    case "video": return `<video src="${src}" controls preload="none" poster="${src}?thumb=1"${sizeAttr(md)}></video>`;
    case "voice": case "audio": return `<audio src="${src}" controls preload="none"></audio>${md.name ? `<div class="small muted" style="padding:2px 6px">${esc(md.name)}</div>` : ""}`;
    case "file": return `<a class="file" href="${src}" target="_blank" download="${esc(md.name || "file")}"><span class="ico">${icon("download")}</span><span><b>${esc(md.name || "Файл")}</b><span class="small" style="opacity:.75">${fmtSize(md.size)}</span></span></a>`;
    case "webpage": return "";
    case "contact": return `<div class="misc">${icon("user")}<span>${esc(md.name)}<br><span class="small">${esc(md.phone)}</span></span></div>`;
    case "poll": return `<div class="misc">${icon("sliders")}<span><b>Опрос</b><br>${esc(md.title)}</span></div>`;
    case "geo": return `<div class="misc">${icon("link")}<span>Геопозиция</span></div>`;
    default: return `<div class="misc muted">${esc(mediaLabel(md.type))}</div>`;
  }
}
const BUTTON_ICON = { url: "link", webview: "link", copy: "copy", switch: "reply", profile: "user" };
function buttonsHtml(m) {
  if (!m.buttons?.length) return "";
  return `<div class="kb">${m.buttons.map((row, r) => `<div class="kb-row">${row.map((b, c) => {
    const ic = BUTTON_ICON[b.kind] ? `<span class="kb-ic">${icon(BUTTON_ICON[b.kind])}</span>` : "";
    const href = (b.kind === "url" || b.kind === "webview") && safeUrl(b.url);
    return href
      ? `<a class="kb-btn" href="${esc(href)}" target="_blank" rel="noopener noreferrer" title="${esc(b.url)}">${esc(b.text)}${ic}</a>`
      : `<button class="kb-btn" data-row="${r}" data-col="${c}"${b.kind === "disabled" ? " disabled" : ""}>${esc(b.text)}${ic}</button>`;
  }).join("")}</div>`).join("")}</div>`;
}
async function pressButton(m, row, col, btnEl) {
  const b = m.buttons?.[row]?.[col];
  if (!b) return;
  if (b.kind === "copy") { await navigator.clipboard.writeText(b.copy || ""); return toast("Скопировано"); }
  if (b.kind === "switch") return toast("Inline-режим бота пока не поддерживается", true);
  if (b.kind === "profile" || b.kind === "buy" || b.kind === "other") return toast("Эта кнопка работает только в приложении Telegram", true);
  btnEl.disabled = true; btnEl.classList.add("loading");
  try {
    const res = await api(`${chatPath(m.account_id, m.chat_id)}/messages/${m.id}/click`, { method: "POST", body: { row, col } });
    if (res.url) window.open(safeUrl(res.url), "_blank", "noopener");
    if (res.message) res.alert ? alert(res.message) : toast(res.message);
  } catch (e) { toast(e.message, true); }
  btnEl.disabled = false; btnEl.classList.remove("loading");
}
function sameGroup(a, b) {
  return a && b && !a.action && !b.action && a.out === b.out && a.sender_id === b.sender_id
    && Math.abs(b.date - a.date) < GROUP_GAP && dayLabel(a.date) === dayLabel(b.date);
}
function messageEl(m, i, isNew = false) {
  if (m.action) {
    const s = document.createElement("div");
    s.className = "service"; s.dataset.id = m.id;
    s.textContent = `${m.sender_name && S.current?.type !== "channel" ? m.sender_name + ": " : ""}${m.action}`;
    return s;
  }
  const prev = S.messages[i - 1], next = S.messages[i + 1];
  const first = !sameGroup(prev, m), last = !sameGroup(m, next);
  const mediaOnly = m.media && VISUAL.has(m.media.type) && !m.text;
  const el = document.createElement("div");
  el.className = "msg" + (m.out ? " out" : "") + (first ? " grp-first" : "") + (last ? " grp-last" : "")
    + (mediaOnly ? " media-only" : "") + (isNew ? " new" : "");
  el.dataset.id = m.id;
  const showSender = first && !m.out && S.current && S.current.type === "group";
  const reply = m.reply_to ? S.messages.find(x => x.id === m.reply_to) : null;
  const wp = m.media?.type === "webpage" ? m.media : null;
  const web = wp && (wp.title || wp.description) ? `<a class="webpage" href="${esc(safeUrl(wp.url))}" target="_blank" rel="noopener noreferrer">
      ${wp.site ? `<span class="wp-site">${esc(wp.site)}</span>` : ""}${wp.title ? `<b>${esc(wp.title)}</b>` : ""}${wp.description ? `<span class="wp-desc">${esc(wp.description)}</span>` : ""}</a>` : "";
  const spoiler = m.media?.spoiler;
  const meta = `${m.views != null ? `${icon("eye")}${m.views.toLocaleString("ru")} · ` : ""}${m.edit_date ? "изм. " : ""}${m.pinned ? icon("pin") : ""}${fmtClock(m.date)}`;
  el.innerHTML = `
    <div class="actions">
      <button data-act="reply" title="Ответить">${icon("reply")}</button>
      ${m.out ? `<button data-act="edit" title="Изменить">${icon("edit")}</button>` : ""}
      ${m.text ? `<button data-act="copy" title="Копировать">${icon("copy")}</button>` : ""}
      <button data-act="pin" title="${m.pinned ? "Открепить" : "Закрепить"}">${icon("pin")}</button>
      <button data-act="delete" class="danger" title="Удалить">${icon("trash")}</button>
    </div>
    <div class="bubble">${showSender ? `<div class="sender" style="--sc:${peerColor(m.sender_id)}">${esc(m.sender_name)}</div>` : ""}${
      m.reply_to ? `<div class="quote" data-goto="${m.reply_to}">${esc(reply ? (reply.text || mediaLabel(reply.media?.type)).slice(0, 90) : "Ответ на сообщение")}</div>` : ""
    }<div class="media${spoiler ? " spoiler-media" : ""}">${mediaHtml(m)}${spoiler ? `<span class="spoiler-cover">${icon("eye")}Спойлер</span>` : ""}</div>${
      renderText(m.text, m.entities)}${web}<span class="meta">${meta}</span></div>${buttonsHtml(m)}`;
  el.querySelector(".actions").onclick = e => { const b = e.target.closest("button"); if (b) msgAction(b.dataset.act, m); };
  el.querySelector(".quote")?.addEventListener("click", () => flashMessage(m.reply_to));
  el.querySelector(".kb")?.addEventListener("click", e => {
    const b = e.target.closest("button.kb-btn"); if (b) pressButton(m, +b.dataset.row, +b.dataset.col, b);
  });
  el.addEventListener("click", e => {
    // Спойлер скрывает фото/текст до первого нажатия; ссылка под ним при этом не открывается
    const cover = e.target.closest(".spoiler-media:not(.revealed), .spoiler:not(.revealed)");
    if (cover) { e.preventDefault(); e.stopPropagation(); cover.classList.add("revealed"); return; }
    if (matchMedia("(max-width: 860px)").matches && !e.target.closest("a, button, video, audio")) el.classList.toggle("show-actions");
  }, true);
  return el;
}
function dayLabel(ts) {
  const d = new Date(ts * 1000), now = new Date();
  if (d.toDateString() === now.toDateString()) return "Сегодня";
  if (new Date(now - 864e5).toDateString() === d.toDateString()) return "Вчера";
  return d.toLocaleDateString("ru", { day: "numeric", month: "long", ...(d.getFullYear() !== now.getFullYear() && { year: "numeric" }) });
}
function renderMessages(scrollBottom) {
  const box = $("#messages");
  const prevHeight = box.scrollHeight, prevTop = box.scrollTop;
  box.innerHTML = "";
  if (!S.messages.length) { box.innerHTML = emptyState("msg", "Сообщений пока нет"); return; }
  if (S.messages.length >= 40 && !S.current.noMore) {
    const more = document.createElement("button");
    more.className = "btn load-more"; more.textContent = "Загрузить ранние сообщения";
    more.onclick = loadOlder;
    box.appendChild(more);
  }
  let lastDay = "";
  S.messages.forEach((m, i) => {
    const day = dayLabel(m.date);
    if (day !== lastDay) { box.insertAdjacentHTML("beforeend", `<div class="day-sep">${day}</div>`); lastDay = day; }
    box.appendChild(messageEl(m, i));
  });
  box.scrollTop = scrollBottom ? box.scrollHeight : box.scrollHeight - prevHeight + prevTop;
}
// Новое сообщение дописывается в конец без перерисовки ленты (видео и GIF не перезапускаются)
function appendMessage(m) {
  const box = $("#messages");
  if (!S.messages.length) box.innerHTML = "";
  S.messages.push(m);
  const i = S.messages.length - 1, prev = S.messages[i - 1];
  if (prev && sameGroup(prev, m)) {
    box.querySelector(`.msg[data-id="${prev.id}"]`)?.classList.remove("grp-last");
  }
  if (!prev || dayLabel(prev.date) !== dayLabel(m.date)) box.insertAdjacentHTML("beforeend", `<div class="day-sep">${dayLabel(m.date)}</div>`);
  box.appendChild(messageEl(m, i, true));
}
function replaceMessage(m) {
  const i = S.messages.findIndex(x => x.id === m.id);
  if (i < 0) return false;
  S.messages[i] = m;
  $(`#messages [data-id="${m.id}"]`)?.replaceWith(messageEl(m, i));
  return true;
}
async function loadOlder() {
  const c = S.current; if (!c || !S.messages.length) return;
  const btn = $(".load-more"); if (btn) { btn.disabled = true; btn.textContent = "Загрузка…"; }
  try {
    const older = await api(`${chatPath(c.account_id, c.id)}/messages?limit=40&offset_id=${S.messages[0].id}`);
    if (S.current !== c) return;
    if (older.length < 40) c.noMore = true;
    S.messages = [...older, ...S.messages];
    renderMessages(false);
  } catch (e) { toast(e.message, true); if (btn) { btn.disabled = false; btn.textContent = "Загрузить ранние сообщения"; } }
}
function flashMessage(id) {
  const el = $(`#messages [data-id="${id}"]`);
  if (!el) return toast("Сообщение выше — нажмите «Загрузить ранние сообщения»");
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1300);
}
function nearBottom() { const b = $("#messages"); return b.scrollHeight - b.scrollTop - b.clientHeight < 160; }
function scrollToBottom(smooth = false) { const b = $("#messages"); b.scrollTo({ top: b.scrollHeight, behavior: smooth ? "smooth" : "auto" }); }
function updateToBottom() {
  const btn = $("#to-bottom"), badge = btn.querySelector(".badge");
  btn.hidden = !S.current || nearBottom();
  if (!btn.hidden) { badge.hidden = !S.unseen; badge.textContent = S.unseen; }
  if (nearBottom()) S.unseen = 0;
}
// atBottom меняется только от прокрутки; если картинка догрузилась и вытянула ленту — держимся низа
let atBottom = true;
$("#messages").addEventListener("scroll", () => { atBottom = nearBottom(); updateToBottom(); }, { passive: true });
$("#messages").addEventListener("load", () => { if (atBottom) scrollToBottom(); }, true);
$("#messages").addEventListener("loadedmetadata", () => { if (atBottom) scrollToBottom(); }, true);
$("#to-bottom").onclick = () => { S.unseen = 0; scrollToBottom(true); };

async function msgAction(act, m) {
  const c = S.current, base = `${chatPath(c.account_id, c.id)}/messages/${m.id}`;
  try {
    if (act === "reply") { S.replyTo = m; S.editing = null; updateReplyBar(); $("#composer-text").focus(); }
    if (act === "edit") { S.editing = m; S.replyTo = null; $("#composer-text").value = m.text; updateReplyBar(); autoGrow(); $("#composer-text").focus(); }
    if (act === "copy") { await navigator.clipboard.writeText(m.text); toast("Текст скопирован"); }
    if (act === "pin") {
      await api(`${base}/pin?unpin=${m.pinned}`, { method: "POST" });
      replaceMessage({ ...m, pinned: !m.pinned });
      toast(m.pinned ? "Откреплено" : "Закреплено");
    }
    if (act === "delete") {
      if (!confirm("Удалить сообщение?")) return;
      const forAll = c.type === "channel" || c.type === "group" || confirm("Удалить у собеседника тоже? «Отмена» — удалить только у себя.");
      await api(`${base}?revoke=${forAll}`, { method: "DELETE" });
      S.messages = S.messages.filter(x => x.id !== m.id); renderMessages(false);
    }
  } catch (e) { toast(e.message, true); }
}
function updateReplyBar() {
  const m = S.editing || S.replyTo;
  $("#reply-bar").hidden = !m;
  if (!m) return;
  $(".reply-icon").innerHTML = icon(S.editing ? "edit" : "reply");
  $("#reply-label").textContent = S.editing ? "Редактирование" : `Ответ ${m.sender_name || ""}`;
  $("#reply-text").textContent = m.text || mediaLabel(m.media?.type);
}
$("#reply-cancel").onclick = () => { if (S.editing) { ta.value = ""; autoGrow(); } S.replyTo = S.editing = null; updateReplyBar(); };

// ---------- отправка ----------
const ta = $("#composer-text");
function autoGrow() { ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 200) + "px"; }
ta.addEventListener("input", autoGrow);
ta.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#composer").requestSubmit(); }
  if (e.key === "Escape") $("#reply-cancel").click();
});
$("#composer").addEventListener("submit", async e => {
  e.preventDefault();
  const c = S.current, text = ta.value.trim();
  if (!c || !text) return;
  const btn = $("#composer .send"); btn.disabled = true;
  try {
    if (S.editing) {
      upsertMessage(await api(`${chatPath(c.account_id, c.id)}/messages/${S.editing.id}`, { method: "PATCH", body: { text } }));
    } else {
      upsertMessage(await api(`${chatPath(c.account_id, c.id)}/messages`, { method: "POST", body: { text, reply_to: S.replyTo?.id ?? null } }), true);
    }
    ta.value = ""; autoGrow(); S.replyTo = S.editing = null; updateReplyBar();
  } catch (err) { toast(err.message, true); }
  btn.disabled = false; ta.focus();
});
$("#file-input").addEventListener("change", async e => {
  const c = S.current, files = [...e.target.files];
  e.target.value = "";
  if (!c) return;
  let caption = ta.value.trim();
  for (const f of files) {
    toast(`Отправка: ${f.name}`);
    const fd = new FormData();
    fd.append("file", f); fd.append("caption", caption);
    if (S.replyTo) fd.append("reply_to", S.replyTo.id);
    try { upsertMessage(await api(`${chatPath(c.account_id, c.id)}/files`, { method: "POST", form: fd }), true); }
    catch (err) { toast(err.message, true); return; }
    caption = "";
  }
  ta.value = ""; autoGrow(); S.replyTo = null; updateReplyBar(); toast(files.length > 1 ? `Отправлено файлов: ${files.length}` : "Отправлено");
});

function upsertMessage(m, own = false) {
  const c = S.current;
  if (!c || c.account_id !== m.account_id || c.id !== m.chat_id) return;
  if (replaceMessage(m)) return;
  const stick = own || nearBottom();
  if (S.messages.length && m.id < S.messages[S.messages.length - 1].id) {
    S.messages.push(m); S.messages.sort((a, b) => a.id - b.id); renderMessages(false);
  } else appendMessage(m);
  if (stick) scrollToBottom(own);
  else if (!m.out) S.unseen += 1;
  updateToBottom();
}

// ---------- realtime ----------
function connectWS() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  const ping = setInterval(() => ws.readyState === 1 && ws.send("ping"), 25000);
  ws.onmessage = e => onEvent(JSON.parse(e.data));
  ws.onclose = ev => { clearInterval(ping); if (ev.code !== 4401) setTimeout(connectWS, 3000); };
}
function onEvent(ev) {
  if (ev.type === "account") {
    const prev = S.accounts.get(ev.account.id);
    S.accounts.set(ev.account.id, ev.account);
    renderRail();
    if (ev.account.status === "online" && prev?.status !== "online") reloadDialogsSoon();
    return;
  }
  if (ev.type === "message") {
    const m = ev.message;
    const inScope = S.scope === "" || S.scope === m.account_id;
    const d = S.dialogs.find(x => x.account_id === m.account_id && x.id === m.chat_id);
    const open = S.current && S.current.account_id === m.account_id && S.current.id === m.chat_id;
    if (open) {
      upsertMessage(m);
      if (!S.ghost && !m.out && document.visibilityState === "visible") markRead(S.current);
    }
    if (d) {
      d.last_text = m.text; d.last_media = m.media?.type || null; d.last_action = m.action || "";
      d.last_out = m.out; d.date = m.date;
      if (!m.out && !(open && !S.ghost)) d.unread += 1;
      if (m.out) d.unread = 0;
      resortDialogs();
    } else if (inScope && shouldShowNewChat(m)) reloadDialogsSoon();
    if (!m.out && !open && !d?.muted && document.visibilityState !== "visible") notify(ev);
    return;
  }
  if (ev.type === "edit") { upsertMessage(ev.message); return; }
  if (ev.type === "delete") {
    const c = S.current;
    if (c && c.account_id === ev.account_id && (ev.chat_id == null || ev.chat_id === c.id)) {
      const ids = new Set(ev.ids);
      const before = S.messages.length;
      S.messages = S.messages.filter(x => !ids.has(x.id));
      if (S.messages.length !== before) renderMessages(false);
    }
  }
}
// Новый чат появился в Telegram: в «Архиве» его не ждём, в папке — только если он в неё добавлен
function shouldShowNewChat(m) {
  if (S.folder === "archive") return false;
  if (typeof S.folder === "number") {
    const f = S.folders.find(x => x.id === S.folder);
    return !!f && inFolder(f, { account_id: m.account_id, id: m.chat_id });
  }
  return true;
}
function notify(ev) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  const a = acc(ev.message.account_id), m = ev.message;
  new Notification(`${ev.chat_title} · ${a?.name || ""}`, { body: m.text || mediaLabel(m.media?.type), tag: key(m.account_id, m.chat_id) });
}

// ---------- модальные окна ----------
function modal(title, html, onMount) {
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = html;
  hydrateIcons($("#modal-body"));
  $("#modal").hidden = false;
  onMount?.($("#modal-body"));
}
function closeModal() { $("#modal").hidden = true; $("#modal-body").innerHTML = ""; }
$("#modal-close").onclick = closeModal;
$("#modal").addEventListener("mousedown", e => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#modal").hidden) closeModal(); });
function formSubmit(root, handler) {
  const form = root.querySelector("form");
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const btn = form.querySelector("[type=submit]"), err = form.querySelector(".error");
    if (err) err.textContent = "";
    btn.disabled = true;
    try { await handler(new FormData(form), form); }
    catch (ex) { if (err) err.textContent = ex.message; else toast(ex.message, true); }
    btn.disabled = false;
  });
}
const loadingHtml = `<div class="empty-list"><div class="skel" style="width:60%;height:14px"></div><div class="skel" style="width:40%;height:14px"></div></div>`;

// --- добавление аккаунта из tdata ---
function skipTdataFile(path, size) {
  const parts = path.split("/").slice(0, -1).map(p => p.toLowerCase());
  return parts.some(p => SKIP_DIRS.some(s => p.startsWith(s))) || size > 5 * 1024 * 1024;
}
$("#add-account").onclick = () => modal("Новый аккаунт", `
  <form class="form">
    <label>Имя в панели<input name="name" required placeholder="Например: Продажи 1" autocomplete="off"></label>
    <div class="drop" id="drop">
      <span class="drop-ico" data-icon="folder"></span>
      <div><b>Выберите папку tdata</b></div>
      <div class="small">или перетащите сюда zip-архив с ней</div>
    </div>
    <div class="row">
      <label class="btn">${icon("folder")} Папка<input type="file" id="pick-folder" webkitdirectory hidden></label>
      <label class="btn">${icon("zip")} ZIP-архив<input type="file" id="pick-zip" accept=".zip" hidden></label>
    </div>
    <label class="check"><input type="checkbox" name="new_session" value="true" checked>
      <span>Отдельный сеанс <span class="small">Панель войдёт как новое устройство, а tdata продолжит работать независимо. Рекомендуется.</span></span></label>
    <label id="pwd-2fa">Облачный пароль (2FA)<input name="password_2fa" type="password" placeholder="если включён" autocomplete="off"></label>
    <label>Локальный код-пароль Telegram Desktop<input name="passcode" type="password" placeholder="если установлен" autocomplete="off"></label>
    <label>Прокси<input name="proxy" placeholder="socks5://user:pass@host:port — необязательно" autocomplete="off"></label>
    <div class="error"></div>
    <button class="btn primary block" type="submit">Подключить аккаунт</button>
  </form>`, root => {
  let files = [];
  const drop = root.querySelector("#drop");
  const setFiles = (list, label) => {
    files = list;
    drop.classList.toggle("has", files.length > 0);
    drop.innerHTML = files.length
      ? `<span class="drop-ico">${icon("check")}</span><div><b>${esc(label)}</b></div><div class="small">${files.length} файл(ов) будет загружено</div>`
      : `<span class="drop-ico">${icon("alert")}</span><div><b>Файлы tdata не найдены</b></div>`;
  };
  root.querySelector("#pick-folder").onchange = e => {
    const all = [...e.target.files];
    const kept = all.filter(f => !skipTdataFile(f.webkitRelativePath, f.size)).map(f => [f, f.webkitRelativePath]);
    setFiles(kept, `Папка «${all[0]?.webkitRelativePath.split("/")[0] || ""}»`);
  };
  root.querySelector("#pick-zip").onchange = e => { const f = e.target.files[0]; if (f) setFiles([[f, f.name]], f.name); };
  drop.onclick = () => root.querySelector("#pick-folder").click();
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = e => {
    e.preventDefault(); drop.classList.remove("over");
    const f = [...e.dataTransfer.files].find(x => x.name.toLowerCase().endsWith(".zip"));
    if (f) setFiles([[f, f.name]], f.name); else toast("Перетащите zip-архив или выберите папку кнопкой", true);
  };
  root.querySelector("[name=new_session]").onchange = e => (root.querySelector("#pwd-2fa").hidden = !e.target.checked);
  root.querySelector("[name=name]").focus();
  formSubmit(root, async (fd, form) => {
    if (!files.length) throw new Error("Выберите папку tdata или zip-архив");
    const send = new FormData();
    for (const k of ["name", "passcode", "password_2fa", "proxy"]) send.append(k, fd.get(k) || "");
    send.append("new_session", fd.get("new_session") ? "true" : "false");
    for (const [f, path] of files) send.append("files", f, path);
    const btn = form.querySelector("[type=submit]");
    btn.textContent = "Подключение к Telegram…";
    try {
      const a = await api("/api/accounts/import", { method: "POST", form: send });
      S.accounts.set(a.id, a);
      closeModal();
      toast(a.updated ? `Сессия аккаунта «${a.name}» обновлена` : `Аккаунт «${a.name}» подключён`);
      setScope(a.id);
    } finally { btn.textContent = "Подключить аккаунт"; }
  });
});

// --- меню аккаунта ---
function accountMenu(aid) {
  const a = acc(aid); if (!a) return;
  const tiles = [
    ["newchat", "edit", "Написать"], ["channel", "channel", "Создать канал"], ["group", "group", "Создать группу"],
    ["join", "link", "Вступить по ссылке"], ["profile", "user", "Профиль Telegram"], ["settings", "sliders", "Настройки"],
    ["sessions", "monitor", "Сеансы"], ["reconnect", "refresh", "Переподключить"], ["remove", "trash", "Удалить", "danger"],
  ];
  modal("Аккаунт", `
    <div class="acc-head"><div id="acc-ava"></div><div class="info">
      <div class="name">${esc(a.name)}</div>
      <div class="muted small">${esc([a.full_name, accountLine(a)].filter(Boolean).join(" · "))}</div>
      <div class="status-line"><span class="dot" style="background:var(--${a.status === "online" ? "ok" : a.status === "error" ? "danger" : "warn"})"></span>${esc(statusText(a))}</div>
    </div></div>
    <div class="tiles">${tiles.map(([id, ic, label, cls]) =>
      `<button class="tile ${cls || ""}" data-a="${id}"><span class="ti">${icon(ic)}</span>${label}</button>`).join("")}</div>`, root => {
    root.querySelector("#acc-ava").appendChild(avatarEl(a.status === "online" ? a.id : null, "me", a.full_name || a.name, a.color, "lg"));
    root.querySelector(".tiles").onclick = e => {
      const b = e.target.closest("button"); if (!b) return;
      ({ newchat: () => newChatModal(aid), channel: () => channelModal(aid, "channel"), group: () => channelModal(aid, "group"),
         join: () => joinModal(aid), profile: () => profileModal(aid), settings: () => settingsModal(aid),
         sessions: () => sessionsModal(aid), reconnect: () => reconnect(aid), remove: () => removeModal(aid) })[b.dataset.a]();
    };
  });
}
async function reconnect(aid) {
  closeModal(); toast("Переподключение…");
  try { const a = await api(`/api/accounts/${aid}/reconnect`, { method: "POST" }); S.accounts.set(a.id, a); renderRail(); toast(statusText(a), a.status !== "online"); }
  catch (e) { toast(e.message, true); }
}
function pickAccountThen(fn) {
  if (S.scope !== "") return fn(S.scope);
  const online = [...S.accounts.values()].filter(a => a.status === "online");
  if (online.length === 1) return fn(online[0].id);
  modal("С какого аккаунта?", `<div class="menu-list">${online.map(a => `<button data-id="${a.id}"><span class="chip" style="--c:${a.color}">${esc(a.name)}</span><span class="muted small">${esc(accountLine(a))}</span></button>`).join("") || '<div class="muted">Нет подключённых аккаунтов</div>'}</div>`,
    root => root.querySelector(".menu-list").onclick = e => { const b = e.target.closest("button"); if (b) fn(Number(b.dataset.id)); });
}
$("#new-chat").onclick = () => pickAccountThen(newChatModal);

function newChatModal(aid) {
  modal(`Найти · ${acc(aid).name}`, `
    <form class="form"><label class="search"><span data-icon="search"></span><input name="q" placeholder="@username, имя или +79991234567" required autocomplete="off"></label>
    <button class="btn primary block" type="submit">Найти</button><div class="error"></div></form>
    <div id="search-results" style="margin-top:12px;display:grid;gap:2px"></div>`, root => {
    root.querySelector("input").focus();
    formSubmit(root, async fd => {
      const res = await api(`/api/accounts/${aid}/search?q=${encodeURIComponent(fd.get("q"))}`);
      const box = root.querySelector("#search-results");
      box.innerHTML = res.length ? "" : emptyState("search", "Ничего не найдено");
      for (const r of res) {
        const el = document.createElement("div");
        el.className = "list-item";
        el.appendChild(avatarEl(aid, r.id, r.title, peerColor(r.id), "sm"));
        el.insertAdjacentHTML("beforeend", `<div><b>${esc(r.title)}</b><div class="small muted">${r.username ? "@" + esc(r.username) + " · " : ""}${esc({ user: "пользователь", bot: "бот", group: "группа", channel: "канал" }[r.type] || r.type)}</div></div>`);
        el.onclick = () => { closeModal(); openChat({ account_id: aid, id: r.id, title: r.title, type: r.type, unread: 0 }); };
        box.appendChild(el);
      }
    });
  });
}
function channelModal(aid, kind) {
  const word = kind === "channel" ? "канал" : "группу";
  modal(`Создать ${word}`, `
    <form class="form">
      <label>Название<input name="title" required maxlength="128" autocomplete="off"></label>
      <label>Описание<textarea name="about" rows="3" maxlength="255"></textarea></label>
      <label>Публичная ссылка t.me/…<input name="username" placeholder="пусто — будет приватный" autocomplete="off"></label>
      <div class="error"></div><button class="btn primary block" type="submit">Создать</button>
    </form>`, root => formSubmit(root, async fd => {
    const r = await api(`/api/accounts/${aid}/channels`, { method: "POST", body: { title: fd.get("title"), about: fd.get("about"), username: fd.get("username"), kind } });
    closeModal();
    toast(r.warning || `Создано: ${r.title}`, !!r.warning);
    openChat({ account_id: aid, id: r.id, title: r.title, type: r.type, unread: 0, is_admin: true, is_creator: true });
    reloadDialogsSoon();
  }));
}
function joinModal(aid) {
  modal("Вступить по ссылке", `
    <form class="form"><label>Ссылка или @username<input name="link" required placeholder="https://t.me/+AbCd… или @channel" autocomplete="off"></label>
    <div class="error"></div><button class="btn primary block" type="submit">Вступить</button></form>`, root => formSubmit(root, async fd => {
    const r = await api(`/api/accounts/${aid}/join`, { method: "POST", body: { link: fd.get("link") } });
    closeModal(); toast(`Готово: ${r.title}`);
    openChat({ account_id: aid, id: r.id, title: r.title, type: r.type, unread: 0 });
    reloadDialogsSoon();
  }));
}
async function profileModal(aid) {
  modal("Профиль Telegram", loadingHtml);
  let p;
  try { p = await api(`/api/accounts/${aid}/profile`); } catch (e) { return $("#modal-body").innerHTML = emptyState("alert", e.message); }
  modal("Профиль Telegram", `
    <form class="form">
      <div class="acc-head"><div id="me-ava"></div><div class="info">
        <div class="name">${esc([p.first_name, p.last_name].filter(Boolean).join(" "))}</div>
        <div class="muted small">+${esc(p.phone)}${p.premium ? " · Premium" : ""}</div></div></div>
      <div class="row"><label>Имя<input name="first_name" value="${esc(p.first_name)}" required></label>
        <label>Фамилия<input name="last_name" value="${esc(p.last_name)}"></label></div>
      <label>Имя пользователя<input name="username" value="${esc(p.username)}" placeholder="без @"></label>
      <label>О себе<textarea name="about" rows="3" maxlength="140">${esc(p.about)}</textarea></label>
      <div class="error"></div><button class="btn primary block" type="submit">Сохранить</button>
    </form>`, root => {
    const box = root.querySelector("#me-ava");
    box.appendChild(editableAvatar(avatarEl(aid, "me", p.first_name, acc(aid).color, "lg"), async f => {
      const fd = new FormData(); fd.append("file", f);
      await api(`/api/accounts/${aid}/photo`, { method: "POST", form: fd });
      bumpAvatar(aid, "me");
      box.querySelector(".avatar").replaceWith(avatarEl(aid, "me", p.first_name, acc(aid).color, "lg"));
      renderRail();
      toast("Аватар обновлён");
    }));
    formSubmit(root, async fd => {
      await api(`/api/accounts/${aid}/profile`, { method: "POST", body: Object.fromEntries(fd) });
      toast("Профиль сохранён"); closeModal(); loadAccounts();
    });
  });
}
function settingsModal(aid) {
  const a = acc(aid);
  modal("Настройки аккаунта", `
    <form class="form">
      <label>Имя в панели<input name="name" value="${esc(a.name)}" required></label>
      <label>Цвет метки</label>
      <div class="colors">${COLORS.map(c => `<button type="button" data-c="${c}" style="--c:${c}" class="${c === a.color ? "on" : ""}"></button>`).join("")}</div>
      <label>Прокси<input name="proxy" value="${esc(a.proxy)}" placeholder="socks5://user:pass@host:port"></label>
      <p class="hint">При смене прокси аккаунт переподключится.</p>
      <div class="error"></div><button class="btn primary block" type="submit">Сохранить</button>
    </form>`, root => {
    let color = a.color;
    root.querySelector(".colors").onclick = e => {
      const b = e.target.closest("button"); if (!b) return;
      color = b.dataset.c; root.querySelectorAll(".colors button").forEach(x => x.classList.toggle("on", x === b));
    };
    formSubmit(root, async fd => {
      const body = { name: fd.get("name"), color };
      if (fd.get("proxy") !== a.proxy) body.proxy = fd.get("proxy");
      const upd = await api(`/api/accounts/${aid}`, { method: "PATCH", body });
      S.accounts.set(aid, { ...a, ...upd });
      closeModal(); renderRail(); renderDialogs();
      toast("Сохранено");
    });
  });
}
async function sessionsModal(aid) {
  modal("Активные сеансы", loadingHtml);
  try {
    const list = await api(`/api/accounts/${aid}/authorizations`);
    modal("Активные сеансы", `<div class="form">${list.map(s => `
      <div class="session-item"><span class="si">${icon(s.current ? "check" : "monitor")}</span><div><b>${esc(s.device)}</b> ${s.current ? '<span class="chip" style="--c:var(--ok)">эта панель</span>' : ""}
        <div class="small muted">${esc(s.app)} · ${esc(s.platform)} ${esc(s.system)}<br>${esc(s.ip)} ${esc(s.country)} · ${fmtTime(s.active)}</div></div>
        ${s.current ? "" : `<button class="btn danger" data-hash="${s.hash}">Завершить</button>`}</div>`).join("")}</div>`, root => {
      root.onclick = async e => {
        const b = e.target.closest("[data-hash]"); if (!b || !confirm("Завершить этот сеанс?")) return;
        try { await api(`/api/accounts/${aid}/authorizations/${b.dataset.hash}`, { method: "DELETE" }); b.closest(".session-item").remove(); toast("Сеанс завершён"); }
        catch (ex) { toast(ex.message, true); }
      };
    });
  } catch (e) { $("#modal-body").innerHTML = emptyState("alert", e.message); }
}
function removeModal(aid) {
  const a = acc(aid);
  modal(`Удалить «${a.name}»`, `
    <div class="form">
      <p style="margin:0"><b>Удалить из панели</b> — сессия стирается только отсюда, аккаунт в Telegram остаётся.</p>
      <p class="muted small" style="margin:0"><b>Выйти и удалить</b> — сеанс завершается в Telegram. Если аккаунт подключён без «отдельного сеанса», tdata тоже перестанет работать.</p>
      <div class="row"><button class="btn" data-logout="0">Удалить из панели</button><button class="btn danger" data-logout="1">Выйти и удалить</button></div>
    </div>`, root => root.onclick = async e => {
    const b = e.target.closest("[data-logout]"); if (!b) return;
    try {
      await api(`/api/accounts/${aid}?logout=${b.dataset.logout === "1"}`, { method: "DELETE" });
      S.accounts.delete(aid); closeModal();
      if (S.current?.account_id === aid) { S.current = null; $("#chat").classList.add("empty"); }
      setScope(""); toast("Аккаунт удалён");
    } catch (ex) { toast(ex.message, true); }
  });
}

// --- информация о чате ---
const isOpen = c => S.current && S.current.account_id === c.account_id && S.current.id === c.id;
$("#chat-info").onclick = () => S.current && chatInfoModal(S.current);
// Из меню чата: чат может быть не открыт, поэтому сначала догружаем описание
async function openChatInfo(d) {
  if (isOpen(d)) return chatInfoModal(S.current);
  modal("Загрузка…", loadingHtml);
  try { chatInfoModal({ ...d, ...(await api(chatPath(d.account_id, d.id))) }); }
  catch (e) { $("#modal-body").innerHTML = emptyState("alert", e.message); }
}
function chatInfoModal(c) {
  const editable = (c.type === "channel" || c.type === "group") && c.is_admin;
  const kind = { user: "Пользователь", bot: "Бот", group: "Группа", channel: "Канал" }[c.type] || "";
  modal(kind, `
    <div class="acc-head"><div id="chat-ava"></div><div class="info">
      <div class="name">${esc(c.title)}</div>
      <div class="muted small">${c.members ? `${c.members.toLocaleString("ru")} участников` : esc(kind)}</div>
    </div></div>
    <div class="info-list">
      ${c.username ? `<div class="info-row"><span data-icon="at"></span><a class="val" href="https://t.me/${esc(c.username)}" target="_blank">t.me/${esc(c.username)}</a></div>` : ""}
      ${c.phone ? `<div class="info-row"><span data-icon="phone"></span><span class="val">+${esc(c.phone)}</span></div>` : ""}
      ${c.about ? `<div class="info-row"><span data-icon="info"></span><span class="val">${linkify(c.about)}</span></div>` : ""}
      <div class="info-row"><span data-icon="hash"></span><span class="val muted small">ID ${c.id} · аккаунт «${esc(acc(c.account_id)?.name || "")}»</span></div>
    </div>
    ${editable ? `
      <div class="section-title">Управление</div>
      <form class="form">
        <label>Название<input name="title" value="${esc(c.title)}"></label>
        <label>Описание<textarea name="about" rows="3">${esc(c.about || "")}</textarea></label>
        <label>Публичная ссылка<input name="username" value="${esc(c.username || "")}" placeholder="пусто — приватный"></label>
        <div class="error"></div>
        <div class="row compact"><button class="btn primary sm" type="submit">Сохранить</button>
          <button class="btn sm" type="button" id="make-invite">${icon("link")} Приглашение</button></div>
      </form>` : ""}
    <div class="section-title">Действия</div>
    <div class="menu-list">
      ${S.ghost ? `<button data-a="read">${icon("check")} Отметить прочитанным</button>` : ""}
      <button data-a="leave" class="danger">${icon(c.type === "user" || c.type === "bot" ? "trash" : "door")} ${c.type === "user" || c.type === "bot" ? "Удалить чат" : "Покинуть"}</button>
    </div>`, root => {
    const avaBox = root.querySelector("#chat-ava");
    const chatAvatar = () => avatarEl(c.account_id, c.id, c.title, peerColor(c.id), "lg");
    if (editable) {
      avaBox.appendChild(editableAvatar(chatAvatar(), async f => {
        const fd = new FormData(); fd.append("file", f);
        await api(`${chatPath(c.account_id, c.id)}/photo`, { method: "POST", form: fd });
        bumpAvatar(c.account_id, c.id);
        avaBox.querySelector(".avatar").replaceWith(chatAvatar());
        if (isOpen(c)) renderChatHead();
        renderDialogs();
        toast("Аватар обновлён");
      }));
      formSubmit(root, async fd => {
        const info = await api(`${chatPath(c.account_id, c.id)}/edit`, { method: "POST", body: Object.fromEntries(fd) });
        Object.assign(c, info);
        if (isOpen(c)) { Object.assign(S.current, info); renderChatHead(); }
        closeModal(); toast("Сохранено"); reloadDialogsSoon();
      });
      root.querySelector("#make-invite").onclick = async () => {
        try {
          const { link } = await api(`${chatPath(c.account_id, c.id)}/invite`, { method: "POST" });
          await navigator.clipboard.writeText(link).catch(() => {});
          toast(`Ссылка скопирована: ${link}`);
        } catch (ex) { toast(ex.message, true); }
      };
    } else avaBox.appendChild(chatAvatar());
    root.querySelector(".menu-list").onclick = async e => {
      const b = e.target.closest("button"); if (!b) return;
      if (b.dataset.a === "read") { await markRead(c); closeModal(); toast("Отмечено прочитанным"); }
      if (b.dataset.a === "leave" && confirm("Точно?")) {
        try {
          await api(`${chatPath(c.account_id, c.id)}/leave`, { method: "POST" });
          closeModal();
          if (isOpen(c)) { S.current = null; $("#chat").classList.add("empty"); }
          reloadDialogsSoon();
        } catch (ex) { toast(ex.message, true); }
      }
    };
  });
}

// ---------- меню чата (правый клик / долгое нажатие) ----------
let ctxEl = null;
function closeCtx() { ctxEl?.remove(); ctxEl = null; }
document.addEventListener("mousedown", e => { if (ctxEl && !ctxEl.contains(e.target)) closeCtx(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeCtx(); });
window.addEventListener("resize", closeCtx);
$("#dialog-list").addEventListener("scroll", closeCtx, { passive: true });

// items: [{icon, label, run, danger, checked, keepOpen}] или "sep"
function ctxMenu(x, y, items, title = "") {
  closeCtx();
  ctxEl = document.createElement("div");
  ctxEl.className = "ctx-menu";
  ctxEl.setAttribute("role", "menu");
  fillCtx(items, title);
  document.body.appendChild(ctxEl);
  // не даём меню уехать за край экрана
  const r = ctxEl.getBoundingClientRect();
  ctxEl.style.left = `${Math.max(8, Math.min(x, innerWidth - r.width - 8))}px`;
  ctxEl.style.top = `${Math.max(8, Math.min(y, innerHeight - r.height - 8))}px`;
}
function fillCtx(items, title = "") {
  ctxEl.innerHTML = (title ? `<div class="ctx-title">${esc(title)}</div>` : "") + items.map((it, i) => it === "sep"
    ? '<div class="ctx-sep"></div>'
    : `<button class="ctx-item${it.danger ? " danger" : ""}" data-i="${i}" role="menuitem">
        <span class="ctx-ic">${icon(it.icon)}</span><span class="ctx-label">${esc(it.label)}</span>
        ${it.checked ? `<span class="ctx-check">${icon("check")}</span>` : it.more ? `<span class="ctx-more">${icon("chevron")}</span>` : ""}
      </button>`).join("");
  ctxEl.onclick = async e => {
    const b = e.target.closest(".ctx-item"); if (!b) return;
    const it = items[+b.dataset.i];
    if (!it.keepOpen) closeCtx();
    try { await it.run(); } catch (ex) { toast(ex.message, true); }
  };
}

const KIND_ABOUT = { channel: "О канале", group: "О группе", bot: "О боте", user: "О пользователе" };
function findDialog(d) { return S.dialogs.find(x => x.account_id === d.account_id && x.id === d.id) || d; }
function resortDialogs() {
  S.dialogs.sort((a, b) => (b.pinned - a.pinned) || b.date - a.date);
  renderDialogs(); renderRail();
}
function dialogMenu(d, x, y) { ctxMenu(x, y, dialogMenuItems(d), d.title); }
function dialogMenuItems(d) {
  const folderId = typeof S.folder === "number" ? S.folder : null;
  const folder = folderId && S.folders.find(f => f.id === folderId);
  return [
    { icon: "check", label: "Прочитать всё", run: () => markRead(d).then(() => toast("Прочитано")) },
    { icon: "info", label: KIND_ABOUT[d.type] || "О чате", run: () => openChatInfo(d) },
    "sep",
    { icon: "pin", label: d.pinned ? "Открепить" : "Закрепить", run: () => togglePin(d) },
    { icon: d.muted ? "bell" : "muted", label: d.muted ? "Включить уведомления" : "Выключить уведомления", run: () => toggleMute(d) },
    { icon: "folderPlus", label: "Добавить в папку", more: true, keepOpen: true, run: () => folderPicker(d) },
    ...(folder ? [{ icon: "x", label: `Убрать из «${folder.name}»`, run: () => removeFromFolder(folder, d) }] : []),
    { icon: "archive", label: d.archived ? "Вернуть из архива" : "Архивировать", run: () => toggleArchive(d) },
  ];
}
async function togglePin(d) {
  const pinned = !d.pinned;
  await api(`${chatPath(d.account_id, d.id)}/pin`, { method: "POST", body: { pinned } });
  findDialog(d).pinned = pinned;
  resortDialogs();
  toast(pinned ? "Чат закреплён" : "Чат откреплён");
}
async function toggleMute(d) {
  const muted = !d.muted;
  await api(`${chatPath(d.account_id, d.id)}/mute`, { method: "POST", body: { muted } });
  findDialog(d).muted = muted;
  renderDialogs(); renderRail();
  toast(muted ? "Уведомления выключены" : "Уведомления включены");
}
async function toggleArchive(d) {
  const archived = !d.archived;
  await api(`${chatPath(d.account_id, d.id)}/archive`, { method: "POST", body: { archived } });
  // в «Чатах» архивный чат пропадает, в «Архиве» — возвращённый; в папках остаётся
  if (S.folder === "main" || S.folder === "unread" || S.folder === "archive") {
    S.dialogs = S.dialogs.filter(x => !(x.account_id === d.account_id && x.id === d.id));
  } else findDialog(d).archived = archived;
  renderDialogs(); renderRail();
  toast(archived ? "Чат в архиве" : "Чат возвращён из архива");
}

// ---------- папки ----------
async function loadFolders() {
  S.folders = await api("/api/folders");
  if (typeof S.folder === "number" && !S.folders.some(f => f.id === S.folder)) S.folder = "main";
  renderFolderTabs();
}
const inFolder = (f, d) => f.items.some(i => i.account_id === d.account_id && i.chat_id === d.id);
function folderPicker(d) {
  const items = [
    { icon: "back", label: "Назад", keepOpen: true, run: () => fillCtx(dialogMenuItems(d), d.title) },
    "sep",
    ...S.folders.map(f => ({
      icon: "folder", label: f.name, checked: inFolder(f, d), keepOpen: true,
      run: async () => {
        const has = inFolder(f, d);
        const upd = has
          ? await api(`/api/folders/${f.id}/items?account_id=${d.account_id}&chat_id=${d.id}`, { method: "DELETE" })
          : await api(`/api/folders/${f.id}/items`, { method: "POST", body: { account_id: d.account_id, chat_id: d.id } });
        Object.assign(f, upd);
        renderFolderTabs();
        if (S.folder === f.id) reloadDialogsSoon();
        toast(has ? `Убрано из «${f.name}»` : `Добавлено в «${f.name}»`);
        folderPicker(d);
      },
    })),
    ...(S.folders.length ? ["sep"] : []),
    { icon: "plus", label: "Новая папка…", run: () => folderNameModal(null, d) },
  ];
  fillCtx(items, "Папки");
}
async function removeFromFolder(f, d) {
  Object.assign(f, await api(`/api/folders/${f.id}/items?account_id=${d.account_id}&chat_id=${d.id}`, { method: "DELETE" }));
  S.dialogs = S.dialogs.filter(x => !(x.account_id === d.account_id && x.id === d.id));
  renderFolderTabs(); renderDialogs();
  toast(`Убрано из «${f.name}»`);
}
function folderNameModal(folder, addChat) {
  modal(folder ? "Переименовать папку" : "Новая папка", `
    <form class="form">
      <label>Название<input name="name" value="${esc(folder?.name || "")}" maxlength="40" required autocomplete="off" placeholder="Например: Модели"></label>
      ${addChat ? `<p class="hint">«${esc(addChat.title)}» сразу попадёт в эту папку.</p>` : ""}
      <div class="error"></div><button class="btn primary block" type="submit">${folder ? "Сохранить" : "Создать"}</button>
    </form>`, root => {
    root.querySelector("input").focus();
    formSubmit(root, async fd => {
      let f;
      if (folder) f = await api(`/api/folders/${folder.id}`, { method: "PATCH", body: { name: fd.get("name") } });
      else {
        f = await api("/api/folders", { method: "POST", body: { name: fd.get("name") } });
        if (addChat) f = await api(`/api/folders/${f.id}/items`, { method: "POST", body: { account_id: addChat.account_id, chat_id: addChat.id } });
      }
      closeModal();
      await loadFolders();
      toast(folder ? "Папка переименована" : `Папка «${f.name}» создана`);
    });
  });
}
function folderMenu(f, x, y) {
  ctxMenu(x, y, [
    { icon: "edit", label: "Переименовать", run: () => folderNameModal(f) },
    { icon: "trash", label: "Удалить папку", danger: true, run: async () => {
      if (!confirm(`Удалить папку «${f.name}»? Чаты останутся, пропадёт только папка.`)) return;
      await api(`/api/folders/${f.id}`, { method: "DELETE" });
      if (S.folder === f.id) setFolder("main");
      await loadFolders();
      toast("Папка удалена");
    } },
  ], f.name);
}
function renderFolderTabs() {
  const tabs = [
    { id: "main", label: "Все чаты" },
    { id: "unread", label: "Непрочитанные" },
    ...S.folders.map(f => ({ id: f.id, label: f.name, count: f.items.length, folder: f })),
    { id: "archive", label: "Архив" },
  ];
  const box = $("#folder-tabs");
  box.innerHTML = tabs.map((t, i) => `<button class="ftab${S.folder === t.id ? " active" : ""}" data-i="${i}" role="tab">${
    t.folder ? icon("folder") : ""}${esc(t.label)}${t.count ? `<span class="ftab-n">${t.count}</span>` : ""}</button>`).join("")
    + `<button class="ftab add" title="Новая папка">${icon("plus")}</button>`;
  box.querySelectorAll(".ftab[data-i]").forEach(b => {
    const t = tabs[+b.dataset.i];
    b.onclick = () => setFolder(t.id);
    if (t.folder) b.oncontextmenu = e => { e.preventDefault(); folderMenu(t.folder, e.clientX, e.clientY); };
  });
  box.querySelector(".ftab.add").onclick = () => folderNameModal(null);
  box.querySelector(".ftab.active")?.scrollIntoView({ block: "nearest", inline: "nearest" });
}
function setFolder(id) {
  const prev = S.folder;
  S.folder = id;
  renderFolderTabs();
  const light = v => v === "main" || v === "unread";
  // «Все чаты» ↔ «Непрочитанные» — тот же список, остальное грузим заново
  if (light(prev) && light(id)) renderDialogs();
  else { S.dialogs = []; loadDialogs(); }
}

// ---------- невидимка и тема ----------
function renderGhost() {
  const b = $("#toggle-ghost");
  b.innerHTML = icon(S.ghost ? "ghost" : "eye");
  b.classList.toggle("on", S.ghost);
  b.dataset.tip = S.ghost ? "Невидимка включена\nсообщения не отмечаются прочитанными" : "Невидимка выключена\nоткрытые чаты отмечаются прочитанными";
}
$("#toggle-ghost").onclick = () => { S.ghost = !S.ghost; writePref("ghost", S.ghost ? "1" : "0"); renderGhost(); toast(S.ghost ? "Невидимка включена" : "Невидимка выключена"); };
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  writePref("theme", t);
  $("#toggle-theme").innerHTML = icon(t === "light" ? "moon" : "sun");
  $('meta[name="theme-color"]').content = t === "light" ? "#eef2f8" : "#0b1220";
}
$("#toggle-theme").onclick = () => applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");

// ---------- старт ----------
hydrateIcons();
applyTheme(readPref("theme", "dark"));
renderGhost();
let started = false;
async function start() {
  let sess;
  try { sess = await api("/api/session"); } catch { return showLogin(); }
  $("#login").hidden = true; $("#app").hidden = false;
  $("#logout").hidden = !sess.auth;
  setupLan(sess.lan_panel);
  await Promise.all([loadAccounts(), loadFolders()]);
  await loadDialogs();
  if (!started) {
    started = true;
    connectWS();
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  }
}
start();
