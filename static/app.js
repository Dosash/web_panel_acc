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
  dollar: '<path d="M12 2v20"/><path d="M17 6.5c-.8-1.5-2.6-2.5-5-2.5-3 0-5 1.5-5 3.8 0 5.2 10.4 2.8 10.4 8.2 0 2.4-2.2 4-5.4 4-2.6 0-4.6-1.1-5.4-2.8"/>',
  heart: '<path d="M12 20.5s-8-4.8-8-11A4.5 4.5 0 0 1 12 6.3a4.5 4.5 0 0 1 8 3.2c0 6.2-8 11-8 11z"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  tv: '<rect x="3" y="5" width="18" height="13" rx="2"/><path d="M8 21h8M10 9.5v5l4-2.5z"/>',
  play: '<rect x="2.5" y="5" width="19" height="14" rx="4"/><path d="m10 9 5 3-5 3z"/>',
  star: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/>',
  bug: '<rect x="7" y="8" width="10" height="12" rx="5"/><path d="M12 12v8M9 5l1.5 3M15 5l-1.5 3M3 13h4M17 13h4M4 8l3 2M20 8l-3 2M4 19l3-2M20 19l-3-2"/>',
  card: '<rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M2.5 10h19M6.5 15h4"/>',
  wallet: '<path d="M19 7V5.5A1.5 1.5 0 0 0 17.5 4h-12A2.5 2.5 0 0 0 3 6.5v11A2.5 2.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V15"/><path d="M21 9h-5a3 3 0 0 0 0 6h5z"/><path d="M16 12h.01"/>',
  external: '<path d="M14 3h7v7"/><path d="M21 3l-9 9"/><path d="M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/>',
  sparkles: '<path d="M10 3.5 11.6 8a3 3 0 0 0 1.9 1.9L18 11.5l-4.5 1.6a3 3 0 0 0-1.9 1.9L10 19.5 8.4 15a3 3 0 0 0-1.9-1.9L2 11.5l4.5-1.6A3 3 0 0 0 8.4 8z"/><path d="M19 2v4M17 4h4M19 17v4M17 19h4"/>',
  bold: '<path d="M7 5h6a3.5 3.5 0 0 1 0 7H7zM7 12h7a3.5 3.5 0 0 1 0 7H7z"/>',
  italic: '<path d="M19 4h-9M14 20H5M15 4 9 20"/>',
  underline: '<path d="M6 4v7a6 6 0 0 0 12 0V4M4 21h16"/>',
  strike: '<path d="M16 6.5C15.3 5 13.8 4 12 4c-2.5 0-4.5 1.5-4.5 3.6 0 1.6 1 2.6 2.7 3.4M4 12h16M15.5 14.5c.7.6 1 1.3 1 2.2 0 2-2 3.3-4.5 3.3-2 0-3.7-.9-4.5-2.5"/>',
  code: '<path d="m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>',
  quote: '<path d="M10 7H6a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h3v1a3 3 0 0 1-3 3M20 7h-4a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h3v1a3 3 0 0 1-3 3"/>',
  smile: '<circle cx="12" cy="12" r="9"/><path d="M8.5 14.5a4.5 4.5 0 0 0 7 0M9 9.5h.01M15 9.5h.01"/>',
  eraser: '<path d="m7 21-4-4a2 2 0 0 1 0-2.8L13.2 4a2 2 0 0 1 2.8 0l4 4a2 2 0 0 1 0 2.8L10 21z"/><path d="M21 21H7M9 11l6 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  arrowL: '<path d="M19 12H5M11 18l-6-6 6-6"/>',
  arrowR: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  update: '<circle cx="12" cy="12" r="9"/><path d="M12 16.5v-9M8 11.5l4-4 4 4"/>',
  newspaper: '<path d="M4 4h13v15a2 2 0 0 0 2 2H6a2 2 0 0 1-2-2z"/><path d="M17 8h3v11a2 2 0 0 1-4 0"/><path d="M8 8h5M8 12h5M8 16h3"/>',
  megaphone: '<path d="M3 10v4a1 1 0 0 0 1 1h3l6 4V5L7 9H4a1 1 0 0 0-1 1z"/><path d="M17 8a5 5 0 0 1 0 8"/><path d="M8 15l1 5h2"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  power: '<path d="M12 3v9"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
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
      // цитата и блок кода сами переносят строку — «\n» после них иначе дал бы лишнюю пустую строку
      if ((e.type === "quote" || e.type === "pre") && text[pos] === "\n" && pos < end) pos++;
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
  clearTimeout(toast.timer); clearTimeout(toast.hideTimer);
  toast.timer = setTimeout(() => {
    t.classList.add("out");
    toast.hideTimer = setTimeout(() => { t.hidden = true; t.classList.remove("out"); }, 220);
  }, err ? 6000 : 2800);
}

// navigator.clipboard есть только на https и localhost, а панель в локальной сети открыта по http —
// тогда копируем по-старому, через скрытое поле
async function copyText(text) {
  if (window.isSecureContext && navigator.clipboard) {
    try { await navigator.clipboard.writeText(text); return true; } catch { /* ниже запасной способ */ }
  }
  const area = document.createElement("textarea");
  area.value = text; area.setAttribute("readonly", "");
  area.style.cssText = "position:fixed;top:0;left:0;opacity:0";
  const focused = document.activeElement;
  document.body.appendChild(area); area.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  area.remove(); focused?.focus?.();
  return ok;
}

// ---------- подсказки ----------
let tipEl = null;
document.addEventListener("mouseover", e => {
  const host = e.target.closest("[data-tip]");
  if (!host || ctxEl) { tipEl?.remove(); tipEl = null; return; }   // при открытом меню подсказки не нужны
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
  if (r.status === 401 && !path.startsWith("api/login")) { showLogin(); throw new Error("Нужен вход"); }
  const data = r.headers.get("content-type")?.includes("json") ? await r.json() : null;
  if (!r.ok) {
    const d = data?.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map(x => x.msg).join("; ") : `Ошибка ${r.status}`);
  }
  return data;
}
const acc = id => S.accounts.get(Number(id));
const chatPath = (aid, cid) => `api/accounts/${aid}/chats/${cid}`;
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
    el.dataset.src = `api/accounts/${aid}/avatar/${peer}${v ? `?v=${v}` : ""}`;
    if (!avatarMissing.has(el.dataset.src)) avatarObserver.observe(el);
  }
  return el;
}
// Браузер кэширует аватар на час — после смены фото добавляем к адресу версию
const avatarVersion = new Map();
function bumpAvatar(aid, peer) {
  avatarMissing.delete(`api/accounts/${aid}/avatar/${peer}`);
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
    await api("api/login", { method: "POST", body: { password: $("#login-password").value } });
    $("#login-password").value = "";
    start();
  } catch (err) { $("#login-error").textContent = err.message; }
});
$("#logout").onclick = async () => { await api("api/logout", { method: "POST" }); location.reload(); };

// ---------- аккаунты (рейка) ----------
async function loadAccounts() {
  const list = await api("api/accounts");
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
    b.className = "rail-item acc" + (String(S.scope) === String(a.id) && !BOTS.current ? " active" : "");
    b.dataset.tip = `${a.name}\n${accountLine(a) || a.full_name || ""}\n${statusText(a)}`.replace(/\n+/g, "\n").trim();
    b.style.setProperty("--c", a.color);
    b.appendChild(avatarEl(a.status === "online" ? a.id : null, "me", a.full_name || a.name, a.color));
    b.insertAdjacentHTML("beforeend", `<span class="dot ${a.status}"></span>`);
    const unread = S.dialogs.filter(d => d.account_id === a.id && d.unread && !d.muted).length;
    if (unread && S.scope === "") b.insertAdjacentHTML("beforeend", `<span class="badge">${unread > 99 ? "99+" : unread}</span>`);
    b.onclick = () => setScope(a.id);
    b.oncontextmenu = e => { e.preventDefault(); accountCtxMenu(a, e.clientX, e.clientY); };
    box.appendChild(b);
  }
  $(".rail-item.all").classList.toggle("active", S.scope === "" && !BOTS.current);
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
  closeBotView();
  S.scope = id === "" ? "" : Number(id);
  S.dialogs = [];
  renderRail();
  loadDialogs();
}
$("#account-menu").onclick = () => accountMenu(S.scope);

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
  const fresh = !S.dialogs.length;   // первая загрузка или смена вкладки — список появляется «лесенкой»
  if (fresh) $("#dialog-list").innerHTML = skeletonDialogs();
  try {
    const list = await api(`api/dialogs?${params}`);
    if (req !== dialogsReq) return;
    S.dialogs = list;
    S.animList = fresh;
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
  const animate = S.animList; S.animList = false;
  let n = 0;
  for (const d of list) {
    const a = acc(d.account_id) || { color: "#888", name: "?" };
    const el = document.createElement("div");
    const active = S.current && key(S.current.account_id, S.current.id) === key(d.account_id, d.id);
    el.className = "dialog" + (active ? " active" : "") + (d.unread ? " has-unread" : "") + (animate ? " in" : "");
    if (animate) el.style.setProperty("--i", Math.min(n++, 14));
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
  closeBotView();   // чат из окна (поиск, ссылка t.me) мог открыться, пока на экране бот
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
    if (d.post) setTimeout(() => flashMessage(d.post), 100);
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
  // канал или группа, открытые по ссылке без подписки: смотреть можно, писать — нет
  const guest = c.joined === false && (c.type === "channel" || c.type === "group");
  $("#composer").hidden = !c.can_send || guest;
  const bar = $("#readonly-bar");
  bar.hidden = c.can_send && !guest;
  bar.innerHTML = guest
    ? `${icon("eye")}<span>Просмотр без подписки</span><button class="btn primary sm" type="button" id="join-current">${c.type === "channel" ? "Подписаться" : "Вступить"}</button>`
    : `${icon("lock")} Только чтение — вы не администратор канала`;
  bar.querySelector("#join-current")?.addEventListener("click", () => joinCurrent(c));
  $("#post-btn").hidden = !(c.is_admin && (c.type === "channel" || c.type === "group"));
  const app = $("#bot-app");
  app.hidden = !c.webapp;
  if (c.webapp) app.querySelector(".t").textContent = c.webapp.text || "Приложение";
}
$("#bot-app").onclick = () => {
  const c = S.current; if (!c?.webapp) return;
  openWebApp(c.account_id, { bot: String(c.id), mode: c.webapp.mode, url: c.webapp.url, title: c.title });
};
async function joinCurrent(c) {
  const btn = $("#join-current"); if (btn) btn.disabled = true;
  try {
    await api(`api/accounts/${c.account_id}/join`, { method: "POST", body: c.invite ? { link: c.invite } : { chat_id: c.id } });
    c.joined = true; c.can_send = c.type !== "channel" || c.is_admin;
    if (isOpen(c)) renderChatHead();
    toast(c.type === "channel" ? "Вы подписались" : "Вы вступили в группу");
    reloadDialogsSoon();
  } catch (e) { toast(e.message, true); if (btn) btn.disabled = false; }
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
// Цвет кнопки задаёт бот: primary — синяя, success — зелёная, danger — красная
const KB_STYLES = new Set(["primary", "success", "danger"]);
const BUTTON_ICON = { url: "link", webview: "grid", copy: "copy", switch: "reply", profile: "user" };
function buttonsHtml(m) {
  if (!m.buttons?.length) return "";
  return `<div class="kb">${m.buttons.map((row, r) => `<div class="kb-row">${row.map((b, c) => {
    const ic = BUTTON_ICON[b.kind] ? `<span class="kb-ic">${icon(BUTTON_ICON[b.kind])}</span>` : "";
    const href = b.kind === "url" && safeUrl(b.url);
    const cls = `kb-btn${KB_STYLES.has(b.style) ? ` st st-${b.style}` : ""}`;
    return href
      ? `<a class="${cls}" href="${esc(href)}" target="_blank" rel="noopener noreferrer" title="${esc(b.url)}">${esc(b.text)}${ic}</a>`
      : `<button class="${cls}" data-row="${r}" data-col="${c}"${b.kind === "disabled" ? " disabled" : ""}>${esc(b.text)}${ic}</button>`;
  }).join("")}</div>`).join("")}</div>`;
}
async function pressButton(m, row, col, btnEl) {
  const b = m.buttons?.[row]?.[col];
  if (!b) return;
  if (b.kind === "copy") return (await copyText(b.copy || "")) ? toast("Скопировано") : toast("Не удалось скопировать", true);
  if (b.kind === "switch") return toast("Inline-режим бота пока не поддерживается", true);
  if (b.kind === "profile" || b.kind === "buy" || b.kind === "other") return toast("Эта кнопка работает только в приложении Telegram", true);
  btnEl.disabled = true; btnEl.classList.add("loading");
  try {
    const res = await api(`${chatPath(m.account_id, m.chat_id)}/messages/${m.id}/click`, { method: "POST", body: { row, col } });
    if (res.webapp) openWebApp(m.account_id, { ...res.webapp, chat_id: m.chat_id });
    else if (res.url) window.open(safeUrl(res.url), "_blank", "noopener");
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
    if (act === "copy") (await copyText(m.text)) ? toast("Текст скопирован") : toast("Не удалось скопировать", true);
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

// ---------- красивый пост ----------
// Редактор для админов канала: оформление текста, медиа, цветные кнопки, предпросмотр как в ленте.
// Inline-кнопки Telegram показывает только у сообщений ботов — пост с кнопками публикует бот канала.
const POST_STYLES = [["", "Обычная"], ["primary", "Синяя"], ["success", "Зелёная"], ["danger", "Красная"]];
const POST_EMOJI = "🔥 ✅ ❗️ ⚡️ 🚀 🎁 💎 📌 📢 👉 👇 ⭐️ ❤️ 👍 🎉 💬 📈 💰 🕒 📅 🏆 ✨ 🔔 ⚠️ ❌ ➡️ 🆕 💡 🎯 📲 🤝 😍 🙌 💯 🔗".split(" ");
const POST_TOOLS = [
  ["bold", "Жирный", "Ctrl+B"], ["italic", "Курсив", "Ctrl+I"], ["underline", "Подчёркнутый", "Ctrl+U"],
  ["strike", "Зачёркнутый", "Ctrl+Shift+X"], "|", ["spoiler", "Спойлер", "Ctrl+Shift+P"],
  ["code", "Моноширинный (копируется по нажатию)", "Ctrl+Shift+M"], ["quote", "Цитата", "Ctrl+Shift+."], "|",
  ["link", "Ссылка", "Ctrl+K"], ["smile", "Эмодзи", ""], "|", ["eraser", "Убрать оформление", "Ctrl+Shift+N"],
];
const TOOL_ICON = { spoiler: "eye" };
const postFiles = new Map();   // прикреплённый файл живёт в памяти до перезагрузки страницы, текст — в черновике
const draftKey = c => `post:${c.account_id}:${c.id}`;
let P = null;                  // открытый редактор

// --- текст редактора ⇄ text + entities (смещения в UTF-16, как у Telegram и JavaScript) ---
const BLOCK_TAGS = new Set(["DIV", "P", "BLOCKQUOTE", "PRE"]);
function nodeEntity(el) {
  const t = el.tagName, st = el.style || {};
  if (t === "B" || t === "STRONG" || Number(st.fontWeight) >= 600 || st.fontWeight === "bold") return { type: "bold" };
  if (t === "I" || t === "EM" || st.fontStyle === "italic") return { type: "italic" };
  if (t === "U" || t === "INS" || /underline/.test(st.textDecoration || "")) return { type: "underline" };
  if (t === "S" || t === "STRIKE" || t === "DEL" || /line-through/.test(st.textDecoration || "")) return { type: "strike" };
  if (t === "CODE" && el.parentElement?.tagName !== "PRE") return { type: "code" };
  if (t === "PRE") return { type: "pre" };
  if (t === "BLOCKQUOTE") return { type: "quote" };
  if (t === "A" && el.getAttribute("href")) return { type: "link", url: el.getAttribute("href") };
  if (el.classList?.contains("spoiler")) return { type: "spoiler" };
  return null;
}
function editorValue(root) {
  let text = "";
  const entities = [];
  const newline = () => { if (text && !text.endsWith("\n")) text += "\n"; };
  (function walk(node) {
    if (node.nodeType === 3) { text += node.nodeValue.replace(/\u200b/g, "").replace(/\u00a0/g, " "); return; }
    if (node.nodeType !== 1) return;
    if (node.tagName === "BR") {
      // последний <br> в непустой строке — заглушка браузера, а не перевод строки
      const p = node.parentElement;
      if (!(node === p.lastChild && p !== root && BLOCK_TAGS.has(p.tagName) && p.childNodes.length > 1)) text += "\n";
      return;
    }
    const block = BLOCK_TAGS.has(node.tagName) && node !== root;
    if (block) newline();
    const start = text.length, ent = node === root ? null : nodeEntity(node);
    node.childNodes.forEach(walk);
    let end = text.length;
    while (end > start && text[end - 1] === "\n") end--;
    if (ent && end > start) entities.push({ ...ent, offset: start, length: end - start });
    if (block) newline();
  })(root);
  const trimmed = text.replace(/\s+$/, "");
  const clean = entities.map(e => ({ ...e, length: Math.min(e.offset + e.length, trimmed.length) - e.offset }))
    .filter(e => e.length > 0).sort((a, b) => a.offset - b.offset || b.length - a.length);
  return { text: trimmed, entities: clean };
}
function editorLoad(root, text, entities) {
  root.innerHTML = entities?.length ? renderText(text, entities) : esc(text || "");
  root.querySelectorAll("a").forEach(a => a.removeAttribute("target"));
}

// --- команды панели ---
function edRange() {
  const s = getSelection();
  if (!s.rangeCount || !P?.ed.contains(s.getRangeAt(0).commonAncestorContainer)) return null;
  return s.getRangeAt(0);
}
function closestIn(node, selector) {
  const el = node?.nodeType === 1 ? node : node?.parentElement;
  const hit = el?.closest(selector);
  return hit && P.ed.contains(hit) && hit !== P.ed ? hit : null;
}
function unwrap(el) { el.replaceWith(...el.childNodes); }
function selectNode(el) { const r = document.createRange(); r.selectNodeContents(el); const s = getSelection(); s.removeAllRanges(); s.addRange(r); }
function toggleWrap(selector, make) {
  const r = edRange(); if (!r) return;
  const host = closestIn(r.commonAncestorContainer, selector);
  if (host) { unwrap(host); return postChanged(); }
  if (r.collapsed) return toast("Сначала выделите текст", true);
  const el = make();
  el.appendChild(r.extractContents());
  r.insertNode(el);
  el.querySelectorAll(selector).forEach(unwrap);   // вложенный спойлер в спойлере не нужен
  selectNode(el); postChanged();
}
function toggleQuote() {
  const r = edRange(); if (!r) return;
  const host = closestIn(r.commonAncestorContainer, "blockquote");
  if (host) { unwrap(host); return postChanged(); }
  const bq = document.createElement("blockquote");
  if (r.collapsed) bq.innerHTML = "<br>"; else bq.appendChild(r.extractContents());
  r.insertNode(bq);
  if (!bq.nextSibling) bq.after(document.createElement("br"));   // чтобы было куда поставить курсор после цитаты
  const s = getSelection(), nr = document.createRange();
  nr.selectNodeContents(bq); if (r.collapsed) nr.collapse(true);
  s.removeAllRanges(); s.addRange(nr); postChanged();
}
function clearFormat() {
  const r = edRange(); if (!r) return;
  document.execCommand("removeFormat"); document.execCommand("unlink");
  P.ed.querySelectorAll(".spoiler, blockquote, code, pre").forEach(el => { if (r.intersectsNode(el)) unwrap(el); });
  postChanged();
}
function postTool(name) {
  P.ed.focus();
  if (P.savedRange) { const s = getSelection(); s.removeAllRanges(); s.addRange(P.savedRange); }
  const cmd = { bold: "bold", italic: "italic", underline: "underline", strike: "strikeThrough" }[name];
  if (cmd) { document.execCommand(cmd); return postChanged(); }
  if (name === "spoiler") return toggleWrap(".spoiler", () => Object.assign(document.createElement("span"), { className: "spoiler" }));
  if (name === "code") return toggleWrap("code", () => document.createElement("code"));
  if (name === "quote") return toggleQuote();
  if (name === "eraser") return clearFormat();
  if (name === "link") return openLinkRow();
  if (name === "smile") { P.root.querySelector(".pe-emoji").hidden ^= true; P.root.querySelector(".pe-link").hidden = true; }
}
function openLinkRow() {
  const r = edRange(); if (!r) return toast("Поставьте курсор в текст", true);
  const a = closestIn(r.commonAncestorContainer, "a");
  if (!a && r.collapsed) return toast("Выделите слова, которые станут ссылкой", true);
  P.savedRange = r.cloneRange();
  const row = P.root.querySelector(".pe-link"), input = row.querySelector("input");
  P.root.querySelector(".pe-emoji").hidden = true;
  row.hidden = false; row.querySelector("[data-l=remove]").hidden = !a;
  input.value = a?.getAttribute("href") || ""; input.focus();
}
function applyLink(remove) {
  const row = P.root.querySelector(".pe-link"), raw = row.querySelector("input").value.trim();
  const url = remove ? "" : safeUrl(raw);
  if (!remove && !url) return toast("Ссылка должна начинаться с https://, t.me/ или tg://", true);
  P.ed.focus();
  const s = getSelection(); s.removeAllRanges(); if (P.savedRange) s.addRange(P.savedRange);
  const a = closestIn(P.savedRange?.commonAncestorContainer, "a");
  if (remove) { if (a) unwrap(a); }
  else if (a) a.setAttribute("href", url);
  else document.execCommand("createLink", false, url);
  row.hidden = true; P.savedRange = null; postChanged();
}
// Код, спойлер и ссылка не растягиваются на текст, который печатают сразу после них (как в Telegram)
const CLOSED_INLINE = "code, .spoiler, a";
function inlineHostAtCaret() {
  const r = edRange();
  if (!r || !r.collapsed) return null;
  const host = closestIn(r.endContainer, CLOSED_INLINE);
  return host && caretAtEnd(host) ? host : null;
}
function caretAfter(node) {
  const r = document.createRange(); r.setStartAfter(node); r.collapse(true);
  getSelection().removeAllRanges(); getSelection().addRange(r);
}
function postBeforeInput(e) {
  if (e.inputType !== "insertText" || !e.data) return;
  const host = inlineHostAtCaret(); if (!host) return;
  e.preventDefault();
  const t = document.createTextNode(e.data);
  host.after(t); caretAfter(t); postChanged();
}
function postKeydown(e) {
  const mod = e.ctrlKey || e.metaKey;
  if (mod && e.key === "Enter") { e.preventDefault(); return sendPost(); }
  if (mod && e.shiftKey) {
    // Period — «.» в английской раскладке, Slash — та же клавиша «.» в русской
    const tool = { KeyX: "strike", KeyP: "spoiler", KeyM: "code", Period: "quote", Slash: "quote", KeyN: "eraser" }[e.code]
      || (e.key === "." || e.key === ">" ? "quote" : "");
    if (tool) { e.preventDefault(); return postTool(tool); }
  }
  if (mod && !e.shiftKey && e.code === "KeyK") { e.preventDefault(); return openLinkRow(); }
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    const r = edRange(), bq = r && closestIn(r.endContainer, "blockquote");
    if (bq && P.enterQuote === bq && caretAtEnd(bq)) {
      // двойной Enter в конце цитаты — выход из неё на новую строку
      // убираем пустые строки в конце цитаты: <br> или «\n» — смотря как браузер вставил перевод строки
      while (bq.lastChild) {
        const n = bq.lastChild;
        if (n.nodeName === "BR" || !n.textContent.replace(/[\u200b\n]/g, "")) { n.remove(); continue; }
        if (n.nodeType === 3) n.nodeValue = n.nodeValue.replace(/[\u200b\n]+$/, "");
        break;
      }
      const line = document.createElement("div"); line.innerHTML = "<br>";
      bq.after(line);
      const nr = document.createRange(); nr.setStart(line, 0); nr.collapse(true);
      getSelection().removeAllRanges(); getSelection().addRange(nr);
      P.enterQuote = null; return postChanged();
    }
    const host = inlineHostAtCaret();
    if (host) { const t = document.createTextNode("\u200b"); host.after(t); caretAfter(t); }
    document.execCommand("insertLineBreak");
    P.enterQuote = bq && caretAtEnd(bq) ? bq : null;
    return;
  }
  P.enterQuote = null;
}
function caretAtEnd(el) {
  const r = edRange(); if (!r) return false;
  const rest = document.createRange(); rest.selectNodeContents(el); rest.setStart(r.endContainer, r.endOffset);
  return !rest.toString().replace(/[\u200b\n]/g, "");   // хвостовой «\n» — заглушка браузера для пустой строки
}

// --- состояние, черновик, предпросмотр ---
function postState() {
  const { text, entities } = editorValue(P.ed), f = P.root.querySelector(".pe-opts");
  return {
    text, entities, buttons: P.buttons.map(row => row.map(b => ({ text: b.text, style: b.style, ...(b.kind === "copy" ? { copy: b.copy } : { url: b.url }) }))),
    silent: f.silent.checked, no_preview: f.no_preview.checked, invert: f.invert.checked, spoiler: f.spoiler.checked,
    schedule: f.schedule_on.checked && f.schedule.value ? new Date(f.schedule.value).getTime() / 1000 : null,
  };
}
function savePostDraft() {
  clearTimeout(P.saveTimer);
  if (P.sent) return;
  writePref(draftKey(P.c), JSON.stringify({ ...postState(), kinds: P.buttons.map(r => r.map(b => b.kind)), schedule: null }));
}
function postChanged() {
  if (!P) return;
  clearTimeout(P.saveTimer);
  P.saveTimer = setTimeout(savePostDraft, 400);
  P.ed.classList.toggle("is-empty", !P.ed.textContent.replace(/\u200b/g, "") && !P.ed.querySelector("blockquote"));
  renderPostPreview();
}
function postLimit() { return P.file ? 1024 : 4096; }
function renderPostPreview() {
  const st = postState(), box = P.root.querySelector(".pe-preview");
  const f = P.file, kind = f ? (f.type.startsWith("image/") ? "photo" : f.type.startsWith("video/") ? "video" : "file") : "";
  const media = !f ? "" : kind === "photo" ? `<img src="${P.fileUrl}" alt="">`
    : kind === "video" ? `<video src="${P.fileUrl}" muted playsinline preload="metadata"></video>`
    : `<div class="file"><span class="ico">${icon("file")}</span><span><b>${esc(f.name)}</b><span class="small" style="opacity:.75">${fmtSize(f.size)}</span></span></div>`;
  const spoiler = st.spoiler && (kind === "photo" || kind === "video");
  const mediaBlock = media ? `<div class="media${spoiler ? " spoiler-media" : ""}">${media}${spoiler ? `<span class="spoiler-cover">${icon("eye")}Спойлер</span>` : ""}</div>` : "";
  const textBlock = st.text ? renderText(st.text, st.entities) : (media ? "" : `<span class="muted">Текст поста появится здесь</span>`);
  const kb = buttonsHtml({ buttons: P.buttons.map(r => r.map(b => ({ ...b, kind: b.kind === "copy" ? "copy" : "url", url: b.url || "#" }))) });
  const time = st.schedule ? new Date(st.schedule * 1000) : new Date();
  box.innerHTML = `<div class="msg grp-first grp-last${media && !st.text ? " media-only" : ""}"><div class="bubble">${
    st.invert ? textBlock + mediaBlock : mediaBlock + textBlock}<span class="meta">${icon("eye")}1 · ${
    st.schedule ? icon("clock") : ""}${time.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" })}</span></div>${kb}</div>`;
  box.querySelectorAll(".kb-btn").forEach(b => { b.removeAttribute("href"); b.tabIndex = -1; });
  const len = st.text.length, lim = postLimit(), cnt = P.root.querySelector(".pe-count");
  cnt.textContent = `${len.toLocaleString("ru")} / ${lim.toLocaleString("ru")}`;
  cnt.classList.toggle("over", len > lim);
  const hasButtons = P.buttons.some(r => r.length);
  P.root.querySelector(".pe-bot").hidden = !hasButtons;
  const sch = P.root.querySelector(".pe-opts [name=schedule_on]");
  sch.disabled = hasButtons;
  if (hasButtons && sch.checked) { sch.checked = false; P.root.querySelector(".pe-opts [name=schedule]").hidden = true; }
  sch.closest("label").title = hasButtons ? "Пост с кнопками публикует бот, а боты не умеют отложенную отправку" : "";
  const send = P.root.querySelector(".pe-send");
  send.innerHTML = `${icon(st.schedule ? "clock" : "send")}${st.schedule ? "Запланировать" : "Опубликовать"}`;
  P.root.querySelector(".pe-via").textContent = hasButtons
    ? (P.info?.bot ? `Опубликует бот @${P.info.bot.username}` : "Нужен бот для кнопок") : `От имени канала · ${acc(P.c.account_id)?.name || ""}`;
}

// --- медиа ---
function setPostFile(file) {
  if (P.fileUrl) URL.revokeObjectURL(P.fileUrl);
  P.file = file || null; P.fileUrl = file ? URL.createObjectURL(file) : "";
  if (file) postFiles.set(draftKey(P.c), file); else postFiles.delete(draftKey(P.c));
  const box = P.root.querySelector(".pe-media"), visual = file && /^(image|video)\//.test(file.type);
  box.innerHTML = file
    ? `<div class="pe-file">${visual && file.type.startsWith("image/") ? `<img src="${P.fileUrl}" alt="">` : `<span class="ico">${icon(visual ? "play" : "file")}</span>`}
        <span class="grow"><b>${esc(file.name)}</b><span class="small muted">${fmtSize(file.size)}</span></span>
        <button class="icon-btn sm" type="button" data-m="remove" title="Убрать">${icon("x")}</button></div>`
    : `<label class="btn sm pe-attach">${icon("image")}Фото, видео или файл<input type="file" hidden></label>`;
  box.querySelector("input")?.addEventListener("change", e => e.target.files[0] && setPostFile(e.target.files[0]));
  box.querySelector("[data-m=remove]")?.addEventListener("click", () => setPostFile(null));
  P.root.querySelector(".pe-opts [name=spoiler]").closest("label").hidden = !visual;
  P.root.querySelector(".pe-opts [name=invert]").nextElementSibling.firstChild.textContent = file ? "Текст над медиа" : "Превью ссылки над текстом";
  renderPostPreview();
}

// --- кнопки ---
function renderPostButtons() {
  const box = P.root.querySelector(".pe-rows"), sel = P.sel;
  box.innerHTML = P.buttons.map((row, r) => `<div class="pe-row">${row.map((b, c) =>
    `<button type="button" class="kb-btn${KB_STYLES.has(b.style) ? ` st st-${b.style}` : ""}${sel && sel[0] === r && sel[1] === c ? " sel" : ""}" data-r="${r}" data-c="${c}">${esc(b.text || "Без текста")}</button>`).join("")
    }${row.length < 8 ? `<button type="button" class="pe-add-btn" data-add="${r}" title="Кнопка в этот ряд">${icon("plus")}</button>` : ""}</div>`).join("");
  const form = P.root.querySelector(".pe-btn-form"), b = sel && P.buttons[sel[0]]?.[sel[1]];
  form.hidden = !b;
  if (b) {
    form.querySelector("[name=text]").value = b.text;
    form.querySelector("[name=url]").value = b.url || "";
    form.querySelector("[name=copy]").value = b.copy || "";
    form.querySelectorAll("[data-kind]").forEach(x => x.classList.toggle("active", x.dataset.kind === b.kind));
    form.querySelector(".pe-url").hidden = b.kind === "copy";
    form.querySelector(".pe-copy").hidden = b.kind !== "copy";
    form.querySelectorAll("[data-style]").forEach(x => x.classList.toggle("on", x.dataset.style === (b.style || "")));
    form.querySelector("[data-move=left]").disabled = sel[1] === 0;
    form.querySelector("[data-move=right]").disabled = sel[1] === P.buttons[sel[0]].length - 1;
  }
  P.root.querySelector(".pe-add-row").innerHTML = `${icon("plus")}${P.buttons.length ? "Новый ряд кнопок" : "Добавить кнопку"}`;
  renderPostPreview();
}
function addPostButton(r) {
  if (P.info && !P.info.buttons_supported) return toast("Кнопки под постами работают только в каналах и супергруппах", true);
  if (r == null) { P.buttons.push([]); r = P.buttons.length - 1; }
  P.buttons[r].push({ text: "", url: "", copy: "", kind: "url", style: "" });
  P.sel = [r, P.buttons[r].length - 1];
  renderPostButtons(); postChanged();
  P.root.querySelector(".pe-btn-form [name=text]").focus();
}
function editPostButton(patch) {
  const b = P.sel && P.buttons[P.sel[0]]?.[P.sel[1]]; if (!b) return;
  Object.assign(b, patch);
  const el = P.root.querySelector(`.pe-rows [data-r="${P.sel[0]}"][data-c="${P.sel[1]}"]`);
  if (el && "text" in patch && Object.keys(patch).length === 1) { el.textContent = b.text || "Без текста"; renderPostPreview(); }
  else renderPostButtons();
  postChanged();
}
function movePostButton(dir) {
  const [r, c] = P.sel, row = P.buttons[r], to = c + dir;
  if (to < 0 || to >= row.length) return;
  [row[c], row[to]] = [row[to], row[c]]; P.sel = [r, to];
  renderPostButtons(); postChanged();
}
function deletePostButton() {
  const [r, c] = P.sel;
  P.buttons[r].splice(c, 1);
  if (!P.buttons[r].length) P.buttons.splice(r, 1);
  P.sel = null; renderPostButtons(); postChanged();
}

// --- бот для кнопок ---
function renderPostBot() {
  const box = P.root.querySelector(".pe-bot"), info = P.info;
  if (!info) { box.innerHTML = `<div class="muted small">Проверяю бота канала…</div>`; return; }
  if (!info.buttons_supported) { box.innerHTML = `<div class="pe-note warn">${icon("alert")}<span>В обычных группах кнопки не работают — только в каналах и супергруппах.</span></div>`; return; }
  const bot = info.bot;
  if (bot && bot.admin !== false) {
    box.innerHTML = `<div class="pe-note ok">${icon("bot")}<span>Пост с кнопками опубликует <b>@${esc(bot.username)}</b> — он администратор канала.</span>
      <button class="btn sm" type="button" data-b="off">Отключить</button></div>`;
  } else if (bot) {
    box.innerHTML = `<div class="pe-note warn">${icon("alert")}<span><b>@${esc(bot.username)}</b> не может публиковать: он не администратор канала${info.can_promote ? "" : ". Добавьте его вручную с правом «Публикация сообщений»"}.</span>
      ${info.can_promote ? `<button class="btn sm primary" type="button" data-b="promote">Назначить админом</button>` : ""}<button class="btn sm" type="button" data-b="off">Другой бот</button></div>`;
  } else {
    box.innerHTML = `<div class="pe-note">${icon("bot")}<span>Telegram показывает кнопки только у сообщений ботов, поэтому такой пост опубликует ваш бот.
        Создайте его в <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer">@BotFather</a> командой <code>/newbot</code> и вставьте токен —
        ${info.can_promote ? "панель сама назначит бота админом канала с правом публикации." : "затем добавьте бота админом канала с правом «Публикация сообщений»."}</span></div>
      <form class="pe-token"><input name="token" placeholder="123456789:AAH…" autocomplete="off" spellcheck="false"><button class="btn sm primary" type="submit">Подключить</button></form>`;
  }
  box.querySelector(".pe-token")?.addEventListener("submit", e => { e.preventDefault(); connectPostBot(e.target.token.value.trim(), e.submitter); });
  box.querySelector("[data-b=promote]")?.addEventListener("click", e => connectPostBot("", e.currentTarget));
  box.querySelector("[data-b=off]")?.addEventListener("click", async () => {
    try { await api(`${chatPath(P.c.account_id, P.c.id)}/post/bot`, { method: "DELETE" }); P.info.bot = null; renderPostBot(); renderPostPreview(); }
    catch (e) { toast(e.message, true); }
  });
}
async function connectPostBot(token, btn) {
  if (btn) btn.disabled = true;
  try {
    P.info = await api(`${chatPath(P.c.account_id, P.c.id)}/post/bot`, { method: "POST", body: { token } });
    toast(`Бот @${P.info.bot.username} подключён`);
  } catch (e) {
    toast(e.message, true);
    try { P.info = await api(`${chatPath(P.c.account_id, P.c.id)}/post`); } catch { /* оставляем как было */ }
  }
  if (P) { renderPostBot(); renderPostPreview(); }
}

// --- отправка ---
async function sendPost() {
  const st = postState(), c = P.c;
  if (!st.text && !P.file) return toast("Пост пустой: напишите текст или прикрепите медиа", true);
  if (st.text.length > postLimit()) return toast(`Слишком длинно: ${st.text.length} из ${postLimit()} символов`, true);
  const empty = P.buttons.flat().find(b => !b.text.trim() || (b.kind === "copy" ? !b.copy.trim() : !safeUrl(b.url)));
  if (empty) return toast(empty.text.trim() ? `Кнопка «${empty.text}»: ${empty.kind === "copy" ? "укажите текст для копирования" : "укажите ссылку"}` : "У кнопки нет текста", true);
  const btn = P.root.querySelector(".pe-send"); btn.disabled = true; btn.classList.add("loading");
  const fd = new FormData();
  fd.append("data", JSON.stringify(st));
  if (P.file) fd.append("file", P.file);
  try {
    const res = await api(`${chatPath(c.account_id, c.id)}/post`, { method: "POST", form: fd });
    P.sent = true;
    try { localStorage.removeItem(draftKey(c)); } catch { /* приватный режим */ }
    postFiles.delete(draftKey(c));
    closeModal();
    if (res.scheduled) toast(`Пост запланирован на ${new Date(st.schedule * 1000).toLocaleString("ru", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })}`);
    else { upsertMessage(res, true); toast("Пост опубликован"); }
  } catch (e) {
    toast(e.message, true);
    if (P) { btn.disabled = false; btn.classList.remove("loading"); }
  }
}

const POST_HINTS = `
  <h4>Оформление</h4>
  <ul>
    <li>Выделите текст и нажмите кнопку на панели. Повторное нажатие снимает оформление.</li>
    <li><kbd>Ctrl+B</kbd> жирный, <kbd>Ctrl+I</kbd> курсив, <kbd>Ctrl+U</kbd> подчёркнутый, <kbd>Ctrl+Shift+X</kbd> зачёркнутый.</li>
    <li><kbd>Ctrl+Shift+P</kbd> спойлер, <kbd>Ctrl+Shift+M</kbd> моноширинный, <kbd>Ctrl+Shift+.</kbd> цитата, <kbd>Ctrl+K</kbd> ссылка, <kbd>Ctrl+Shift+N</kbd> убрать всё.</li>
    <li>Из цитаты выходят двойным <kbd>Enter</kbd>. <kbd>Ctrl+Enter</kbd> — опубликовать.</li>
    <li>Вставленный текст очищается от чужого оформления — форматируйте здесь.</li>
  </ul>
  <h4>Как сделать пост красивым</h4>
  <ul>
    <li>Первая строка — заголовок: коротко, жирным, можно с эмодзи.</li>
    <li>Абзацы по 2–3 строки, между ними пустая строка — так пост легко читать с телефона.</li>
    <li>Эмодзи — вместо маркеров списка (✅ 👉 📌), не больше одного-двух на строку.</li>
    <li>Главную мысль — в цитату, ответ или интригу — под спойлер.</li>
    <li>Промокоды и команды — моноширинным: в Telegram они копируются нажатием.</li>
    <li>Прячьте ссылки в слова вместо длинных адресов.</li>
    <li>Фото или видео делает пост заметнее в ленте; «Текст над медиа» — когда текст важнее картинки.</li>
  </ul>
  <h4>Кнопки</h4>
  <ul>
    <li>Кнопки Telegram показывает только у сообщений ботов — пост с кнопками опубликует бот, который админ канала.</li>
    <li>Синяя — главное действие, зелёная — «Купить», «Подписаться», «Участвовать», красная — срочное или важное.</li>
    <li>Цветными лучше делать 1–2 кнопки, остальные — обычными, иначе цвет перестаёт выделять главное.</li>
    <li>Текст кнопки — 1–3 слова. В ряд до 8 кнопок, но на телефоне удобнее 1–2.</li>
    <li>«Копировать текст» — кнопка кладёт промокод или адрес кошелька в буфер обмена.</li>
    <li>Старые версии Telegram покажут цветные кнопки обычными.</li>
  </ul>
  <h4>Ограничения</h4>
  <ul>
    <li>Текст — до 4096 символов, подпись к фото или видео — до 1024.</li>
    <li>Отложить можно только пост без кнопок: боты не умеют отложенную отправку.</li>
    <li>Пост с кнопками потом редактирует тот же бот — правка из панели меняет только текст.</li>
  </ul>`;

function postEditor() {
  const c = S.current; if (!c) return;
  let draft = {};
  try { draft = JSON.parse(readPref(draftKey(c), "{}")) || {}; } catch { draft = {}; }
  const tools = POST_TOOLS.map(t => t === "|" ? `<span class="pe-sep"></span>`
    : `<button type="button" class="pe-tool" data-tool="${t[0]}" title="${esc(t[1])}${t[2] ? ` (${t[2]})` : ""}">${icon(TOOL_ICON[t[0]] || t[0])}</button>`).join("");
  modal("Оформленный пост", `
    <div class="post-ed">
      <div class="pe-main">
        <div class="pe-box">
          <div class="pe-toolbar">${tools}</div>
          <div class="pe-link" hidden><input placeholder="https://… или t.me/…" spellcheck="false"><button class="btn sm primary" type="button" data-l="ok">Готово</button><button class="btn sm" type="button" data-l="remove">Убрать</button></div>
          <div class="pe-emoji" hidden>${POST_EMOJI.map(e => `<button type="button">${e}</button>`).join("")}</div>
          <div class="pe-text" contenteditable="true" spellcheck="true" data-placeholder="Заголовок поста&#10;&#10;Текст: выделите слова и выберите оформление на панели сверху"></div>
          <div class="pe-count small"></div>
        </div>
        <section class="pe-sec"><div class="pe-sec-head"><b>Медиа</b><span class="muted small">одно фото, видео или файл</span></div><div class="pe-media"></div></section>
        <section class="pe-sec">
          <div class="pe-sec-head"><b>Кнопки</b><span class="muted small">под постом, можно цветные</span></div>
          <div class="pe-rows"></div>
          <button class="btn sm pe-add-row" type="button"></button>
          <div class="pe-btn-form form" hidden>
            <label>Текст кнопки<input name="text" maxlength="64" placeholder="Например: Подписаться"></label>
            <div class="segmented"><button type="button" class="seg" data-kind="url">${icon("link")}Ссылка</button><button type="button" class="seg" data-kind="copy">${icon("copy")}Копировать текст</button></div>
            <label class="pe-url">Ссылка<input name="url" placeholder="https://… или t.me/канал" spellcheck="false"></label>
            <label class="pe-copy">Что копировать<input name="copy" maxlength="256" placeholder="Промокод, адрес, номер карты…"></label>
            <div class="pe-styles"><span class="muted small">Цвет</span>${POST_STYLES.map(([v, t]) => `<button type="button" data-style="${v}" class="pe-style st-${v || "default"}" title="${t}"><i></i>${t}</button>`).join("")}</div>
            <div class="pe-btn-actions">
              <button class="icon-btn sm" type="button" data-move="left" title="Левее">${icon("arrowL")}</button>
              <button class="icon-btn sm" type="button" data-move="right" title="Правее">${icon("arrowR")}</button>
              <span class="grow"></span>
              <button class="btn sm danger" type="button" data-del>${icon("trash")}Удалить</button>
              <button class="btn sm" type="button" data-done>Готово</button>
            </div>
          </div>
          <div class="pe-bot" hidden></div>
        </section>
        <section class="pe-sec">
          <div class="pe-sec-head"><b>Публикация</b></div>
          <div class="form"><form class="pe-opts checks" onsubmit="return false">
            <label class="opt"><input type="checkbox" name="silent"><span>Без звука<span class="small muted"> — подписчики получат уведомление без звука</span></span></label>
            <label class="opt"><input type="checkbox" name="no_preview"><span>Без превью ссылок</span></label>
            <label class="opt"><input type="checkbox" name="invert"><span><span>Превью ссылки над текстом</span></span></label>
            <label class="opt" hidden><input type="checkbox" name="spoiler"><span>Скрыть медиа под спойлером</span></label>
            <label class="opt"><input type="checkbox" name="schedule_on"><span>Отложить публикацию</span></label>
            <input type="datetime-local" name="schedule" hidden>
          </form></div>
        </section>
      </div>
      <aside class="pe-side">
        <div class="pe-side-label muted small">Предпросмотр</div>
        <div class="pe-preview"></div>
        <details class="pe-hints"><summary>${icon("info")}Подсказки по оформлению</summary>${POST_HINTS}</details>
      </aside>
    </div>
    <footer class="pe-foot">
      <button class="btn sm" type="button" data-clear>${icon("trash")}Очистить</button>
      <span class="pe-via muted small"></span>
      <button class="btn primary pe-send" type="button"></button>
    </footer>`, root => {
    $("#modal .modal-card").classList.add("wide");
    P = { c, root, ed: root.querySelector(".pe-text"), buttons: [], sel: null, file: null, fileUrl: "", info: null, savedRange: null };
    document.execCommand("styleWithCSS", false, false);
    editorLoad(P.ed, draft.text, draft.entities);
    P.buttons = (draft.buttons || []).map((row, r) => row.map((b, i) => ({
      text: b.text || "", url: b.url || "", copy: b.copy || "", style: b.style || "", kind: draft.kinds?.[r]?.[i] || (b.copy ? "copy" : "url") })));
    const opts = root.querySelector(".pe-opts");
    ["silent", "no_preview", "invert", "spoiler"].forEach(k => { opts[k].checked = !!draft[k]; });
    // панель инструментов не забирает фокус у текста, иначе пропадёт выделение
    root.querySelector(".pe-toolbar").addEventListener("mousedown", e => e.preventDefault());
    root.querySelector(".pe-toolbar").addEventListener("click", e => { const b = e.target.closest("[data-tool]"); if (b) { P.savedRange = null; postTool(b.dataset.tool); } });
    root.querySelector(".pe-emoji").addEventListener("mousedown", e => e.preventDefault());
    root.querySelector(".pe-emoji").addEventListener("click", e => {
      const b = e.target.closest("button"); if (!b) return;
      if (!edRange()) { P.ed.focus(); const r = document.createRange(); r.selectNodeContents(P.ed); r.collapse(false); getSelection().removeAllRanges(); getSelection().addRange(r); }
      document.execCommand("insertText", false, b.textContent); postChanged();
    });
    const link = root.querySelector(".pe-link");
    link.querySelector("[data-l=ok]").onclick = () => applyLink(false);
    link.querySelector("[data-l=remove]").onclick = () => applyLink(true);
    link.querySelector("input").addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); applyLink(false); }
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); link.hidden = true; P.ed.focus(); }
    });
    P.ed.addEventListener("input", postChanged);
    P.ed.addEventListener("keydown", postKeydown);
    P.ed.addEventListener("beforeinput", postBeforeInput);
    P.ed.addEventListener("paste", e => {
      e.preventDefault();
      document.execCommand("insertText", false, e.clipboardData.getData("text/plain"));
    });
    P.ed.addEventListener("drop", e => {
      const f = e.dataTransfer?.files?.[0];
      if (f) { e.preventDefault(); setPostFile(f); }
    });
    // кнопки
    root.querySelector(".pe-rows").addEventListener("click", e => {
      const add = e.target.closest("[data-add]"); if (add) return addPostButton(Number(add.dataset.add));
      const b = e.target.closest("[data-r]"); if (!b) return;
      P.sel = [Number(b.dataset.r), Number(b.dataset.c)]; renderPostButtons();
    });
    root.querySelector(".pe-add-row").onclick = () => addPostButton(null);
    const form = root.querySelector(".pe-btn-form");
    form.querySelector("[name=text]").addEventListener("input", e => editPostButton({ text: e.target.value }));
    form.querySelector("[name=url]").addEventListener("input", e => { P.buttons[P.sel[0]][P.sel[1]].url = e.target.value; postChanged(); });
    form.querySelector("[name=copy]").addEventListener("input", e => { P.buttons[P.sel[0]][P.sel[1]].copy = e.target.value; postChanged(); });
    form.querySelectorAll("[data-kind]").forEach(x => x.onclick = () => editPostButton({ kind: x.dataset.kind }));
    form.querySelectorAll("[data-style]").forEach(x => x.onclick = () => editPostButton({ style: x.dataset.style }));
    form.querySelector("[data-move=left]").onclick = () => movePostButton(-1);
    form.querySelector("[data-move=right]").onclick = () => movePostButton(1);
    form.querySelector("[data-del]").onclick = deletePostButton;
    form.querySelector("[data-done]").onclick = () => { P.sel = null; renderPostButtons(); };
    form.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); P.sel = null; renderPostButtons(); } });
    // настройки
    opts.addEventListener("change", e => {
      if (e.target.name === "schedule_on") {
        const dt = opts.schedule; dt.hidden = !e.target.checked;
        if (e.target.checked && !dt.value) {
          const d = new Date(Date.now() + 3600e3); d.setMinutes(0, 0, 0);
          dt.value = new Date(d - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 16);
        }
      }
      postChanged();
    });
    root.querySelector("[data-clear]").onclick = () => {
      if (!confirm("Очистить пост: текст, медиа и кнопки?")) return;
      P.ed.innerHTML = ""; P.buttons = []; P.sel = null; setPostFile(null); renderPostButtons(); postChanged();
    };
    root.querySelector(".pe-send").onclick = sendPost;
    setPostFile(postFiles.get(draftKey(c)) || null);
    renderPostButtons(); renderPostBot(); postChanged();
    api(`${chatPath(c.account_id, c.id)}/post`).then(info => {
      if (P?.c !== c) return;
      P.info = info; renderPostBot(); renderPostPreview();
    }).catch(e => { if (P?.c === c) { P.info = { bot: null, buttons_supported: false, can_promote: false }; renderPostBot(); toast(e.message, true); } });
    P.ed.focus();
  });
}
$("#post-btn").onclick = postEditor;

// ---------- realtime ----------
let wsWasOpen = false;
function connectWS() {
  // адрес относительно страницы: панель может стоять не в корне сайта (WEB_PREFIX)
  const url = new URL("ws", location.href);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(url);
  const ping = setInterval(() => ws.readyState === 1 && ws.send("ping"), 25000);
  ws.onmessage = e => onEvent(JSON.parse(e.data));
  ws.onopen = () => {
    // соединение рвалось (ноутбук спал, сервер перезапускался) — события за это время потеряны: перечитываем
    if (wsWasOpen) resyncAfterReconnect();
    wsWasOpen = true;
  };
  ws.onclose = ev => { clearInterval(ping); if (ev.code !== 4401) setTimeout(connectWS, 3000); };
}
async function resyncAfterReconnect() {
  try { await loadAccounts(); } catch { /* сервер ещё поднимается — список обновится по событиям */ }
  reloadDialogsSoon();
  const c = S.current;
  if (!c) return;
  try {
    const msgs = await api(`${chatPath(c.account_id, c.id)}/messages?limit=40`);
    if (S.current !== c) return;
    const known = new Set(S.messages.map(m => m.id));
    const fresh = msgs.filter(m => !known.has(m.id));
    if (fresh.length) { S.messages = S.messages.concat(fresh).sort((x, y) => x.id - y.id); renderMessages(atBottom); }
  } catch { /* чат перечитается при следующем открытии */ }
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
  // Чат прочитан в другом клиенте или самой панелью — Telegram присылает, сколько осталось непрочитанным
  if (ev.type === "read") {
    const d = S.dialogs.find(x => x.account_id === ev.account_id && x.id === ev.chat_id);
    if (d && !ev.outbox && ev.unread != null && d.unread !== ev.unread) { d.unread = ev.unread; renderDialogs(); renderRail(); }
    return;
  }
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
  $("#modal .modal-card").className = "modal-card";
  $("#modal-title").textContent = title;
  $("#modal-body").innerHTML = html;
  $("#modal-body").removeAttribute("data-aid");   // с какого аккаунта открывать ссылки из окна — задаёт само окно
  hydrateIcons($("#modal-body"));
  clearTimeout(modalCloseTimer);
  $("#modal").classList.remove("closing");
  $("#modal").hidden = false;
  onMount?.($("#modal-body"));
}
let modalCloseTimer;
function closeModal() {
  if (P) { savePostDraft(); if (P.fileUrl) URL.revokeObjectURL(P.fileUrl); P = null; }   // текст и кнопки поста остаются в черновике
  const m = $("#modal");
  if (m.hidden) return;
  m.classList.add("closing");   // окно уходит плавно; содержимое убираем после анимации
  clearTimeout(modalCloseTimer);
  modalCloseTimer = setTimeout(() => {
    if (!m.classList.contains("closing")) return;   // за это время открыли другое окно
    m.classList.remove("closing"); m.hidden = true; $("#modal-body").innerHTML = "";
  }, 170);
}
$("#modal-close").onclick = closeModal;
$("#modal").addEventListener("mousedown", e => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#modal").hidden && !$("#modal").classList.contains("closing")) closeModal(); });
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
      const a = await api("api/accounts/import", { method: "POST", form: send });
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
// правый клик по аккаунту в рейке
function accountCtxMenu(a, x, y) {
  ctxMenu(x, y, [
    { icon: "check", label: "Прочитать все", run: () => readAllAccount(a.id) },
    { icon: "link", label: "Вступить по ссылке", run: () => joinModal(a.id) },
    "sep",
    { icon: "sliders", label: "Настройки", run: () => accountMenu(a.id) },
  ], a.name);
}
async function readAllAccount(aid) {
  toast("Отмечаю все чаты прочитанными…");
  const r = await api(`api/accounts/${aid}/read_all`, { method: "POST" });
  S.dialogs.forEach(d => { if (d.account_id === aid) { d.unread = 0; d.mentions = 0; } });
  renderDialogs(); renderRail();
  toast(r.count ? `Прочитано чатов: ${r.count}` : "Непрочитанных чатов нет");
}
async function reconnect(aid) {
  closeModal(); toast("Переподключение…");
  try { const a = await api(`api/accounts/${aid}/reconnect`, { method: "POST" }); S.accounts.set(a.id, a); renderRail(); toast(statusText(a), a.status !== "online"); }
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
      const res = await api(`api/accounts/${aid}/search?q=${encodeURIComponent(fd.get("q"))}`);
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
    const r = await api(`api/accounts/${aid}/channels`, { method: "POST", body: { title: fd.get("title"), about: fd.get("about"), username: fd.get("username"), kind } });
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
    const r = await api(`api/accounts/${aid}/join`, { method: "POST", body: { link: fd.get("link") } });
    closeModal(); toast(`Готово: ${r.title}`);
    openChat({ account_id: aid, id: r.id, title: r.title, type: r.type, unread: 0 });
    reloadDialogsSoon();
  }));
}
async function profileModal(aid) {
  modal("Профиль Telegram", loadingHtml);
  let p;
  try { p = await api(`api/accounts/${aid}/profile`); } catch (e) { return $("#modal-body").innerHTML = emptyState("alert", e.message); }
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
      await api(`api/accounts/${aid}/photo`, { method: "POST", form: fd });
      bumpAvatar(aid, "me");
      box.querySelector(".avatar").replaceWith(avatarEl(aid, "me", p.first_name, acc(aid).color, "lg"));
      renderRail();
      toast("Аватар обновлён");
    }));
    formSubmit(root, async fd => {
      await api(`api/accounts/${aid}/profile`, { method: "POST", body: Object.fromEntries(fd) });
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
      const upd = await api(`api/accounts/${aid}`, { method: "PATCH", body });
      S.accounts.set(aid, { ...a, ...upd });
      closeModal(); renderRail(); renderDialogs();
      toast("Сохранено");
    });
  });
}
async function sessionsModal(aid) {
  modal("Активные сеансы", loadingHtml);
  try {
    const list = await api(`api/accounts/${aid}/authorizations`);
    modal("Активные сеансы", `<div class="form">${list.map(s => `
      <div class="session-item"><span class="si">${icon(s.current ? "check" : "monitor")}</span><div><b>${esc(s.device)}</b> ${s.current ? '<span class="chip" style="--c:var(--ok)">эта панель</span>' : ""}
        <div class="small muted">${esc(s.app)} · ${esc(s.platform)} ${esc(s.system)}<br>${esc(s.ip)} ${esc(s.country)} · ${fmtTime(s.active)}</div></div>
        ${s.current ? "" : `<button class="btn danger" data-hash="${s.hash}">Завершить</button>`}</div>`).join("")}</div>`, root => {
      root.onclick = async e => {
        const b = e.target.closest("[data-hash]"); if (!b || !confirm("Завершить этот сеанс?")) return;
        try { await api(`api/accounts/${aid}/authorizations/${b.dataset.hash}`, { method: "DELETE" }); b.closest(".session-item").remove(); toast("Сеанс завершён"); }
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
      await api(`api/accounts/${aid}?logout=${b.dataset.logout === "1"}`, { method: "DELETE" });
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
      <div class="section-title">Пригласительная ссылка</div>
      <div class="invite-row"><input id="invite-link" readonly value="${esc(c.invite || "")}" placeholder="ещё не создана">
        <button class="btn sm" type="button" id="copy-invite">${icon("copy")} Копировать</button>
        <button class="btn sm" type="button" id="make-invite">${icon("plus")} Новая</button></div>
      <div class="section-title">Управление</div>
      <div class="menu-list" id="manage-list">
        <button data-m="edit">${icon("edit")} Изменить ${c.type === "channel" ? "канал" : "группу"}</button>
        ${c.legacy ? "" : `<button data-m="admins">${icon("user")} Администраторы</button>`}
        <button data-m="settings">${icon("sliders")} Настройки ${c.type === "channel" ? "канала" : "группы"}</button>
        ${c.is_creator && !c.legacy ? `<button data-m="delete" class="danger">${icon("trash")} Удалить ${c.type === "channel" ? "канал" : "группу"}</button>` : ""}
      </div>` : ""}
    <div class="section-title">Действия</div>
    <div class="menu-list" id="chat-actions">
      ${S.ghost ? `<button data-a="read">${icon("check")} Отметить прочитанным</button>` : ""}
      <button data-a="leave" class="danger">${icon(c.type === "user" || c.type === "bot" ? "trash" : "door")} ${c.type === "user" || c.type === "bot" ? "Удалить чат" : "Покинуть"}</button>
    </div>`, root => {
    root.dataset.aid = c.account_id;
    root.querySelector("#chat-ava").appendChild(avatarEl(c.account_id, c.id, c.title, peerColor(c.id), "lg"));
    if (editable) {
      const inviteInput = root.querySelector("#invite-link");
      root.querySelector("#copy-invite").onclick = async () => {
        if (!inviteInput.value) return toast("Ссылки ещё нет — нажмите «Новая»", true);
        if (await copyText(inviteInput.value)) return toast("Ссылка скопирована");
        inviteInput.select(); toast("Браузер не дал скопировать — выделил ссылку, нажмите Ctrl+C", true);
      };
      root.querySelector("#make-invite").onclick = async () => {
        try {
          const { link } = await api(`${chatPath(c.account_id, c.id)}/invite`, { method: "POST" });
          c.invite = link; inviteInput.value = link;
          toast((await copyText(link)) ? "Новая ссылка создана и скопирована" : "Новая ссылка создана");
        } catch (ex) { toast(ex.message, true); }
      };
      root.querySelector("#manage-list").onclick = e => {
        const b = e.target.closest("button"); if (!b) return;
        ({ edit: () => chatEditModal(c), admins: () => adminsModal(c), settings: () => chatSettingsModal(c), delete: () => deleteChannel(c) })[b.dataset.m]();
      };
    }
    root.querySelector("#chat-actions").onclick = async e => {
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

// --- управление каналом и группой ---
const ADMIN_RIGHTS = {
  channel: [["change_info", "Изменение профиля канала"], ["post_messages", "Публикация сообщений"],
    ["edit_messages", "Изменение чужих публикаций"], ["delete_messages", "Удаление чужих публикаций"],
    ["invite_users", "Добавление подписчиков"], ["post_stories", "Публикация историй"],
    ["edit_stories", "Изменение чужих историй"], ["delete_stories", "Удаление чужих историй"],
    ["manage_call", "Управление трансляциями"], ["add_admins", "Назначение администраторов"]],
  group: [["change_info", "Изменение профиля группы"], ["delete_messages", "Удаление сообщений"],
    ["ban_users", "Блокировка пользователей"], ["invite_users", "Пригласительные ссылки"],
    ["pin_messages", "Закрепление сообщений"], ["manage_call", "Управление видеочатами"],
    ["anonymous", "Анонимность"], ["add_admins", "Назначение администраторов"]],
};
const ADMIN_OFF_BY_DEFAULT = new Set(["add_admins", "anonymous"]);
const PERMISSION_LABELS = [["send_plain", "Отправлять текст"], ["send_photos", "Фото"], ["send_videos", "Видео"],
  ["stickers", "Стикеры и GIF"], ["send_audios", "Музыка"], ["send_docs", "Файлы"], ["send_voices", "Голосовые"],
  ["send_roundvideos", "Видеосообщения"], ["embed_links", "Предпросмотр ссылок"], ["send_polls", "Опросы"],
  ["invite_users", "Добавлять участников"], ["pin_messages", "Закреплять сообщения"], ["change_info", "Изменять профиль группы"]];
const SLOWMODE = [[0, "Выключен"], [10, "10 секунд"], [30, "30 секунд"], [60, "1 минута"], [300, "5 минут"], [900, "15 минут"], [3600, "1 час"]];
const backBtn = `<button class="btn sm back-btn" type="button">${icon("back")} Назад</button>`;

// права и настройки берём свежими: окно о чате могло открыться раньше, чем догрузилось описание
async function freshChat(c) {
  const info = await api(chatPath(c.account_id, c.id));
  Object.assign(c, info);
  if (isOpen(c) && S.current !== c) Object.assign(S.current, info);
  return c;
}
function chatEditModal(c) {
  const chatAvatar = () => avatarEl(c.account_id, c.id, c.title, peerColor(c.id), "lg");
  modal(`Изменить ${c.type === "channel" ? "канал" : "группу"}`, `${backBtn}
    <div class="acc-head"><div id="edit-ava"></div><div class="info">
      <div class="name">${esc(c.title)}</div><div class="muted small">Нажмите на фото, чтобы сменить его</div></div></div>
    <form class="form">
      <label>Название<input name="title" value="${esc(c.title)}" required maxlength="128" autocomplete="off"></label>
      <label>Описание<textarea name="about" rows="4" maxlength="255">${esc(c.about || "")}</textarea></label>
      <label>Публичная ссылка t.me/…<input name="username" value="${esc(c.username || "")}" placeholder="пусто — приватный" autocomplete="off"></label>
      <div class="error"></div><button class="btn primary block" type="submit">Сохранить</button>
    </form>`, root => {
    root.querySelector(".back-btn").onclick = () => chatInfoModal(c);
    const avaBox = root.querySelector("#edit-ava");
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
      if (isOpen(c) && S.current !== c) Object.assign(S.current, info);
      if (isOpen(c)) renderChatHead();
      toast("Сохранено"); reloadDialogsSoon();
      chatInfoModal(c);
    });
  });
}
async function adminsModal(c) {
  modal("Администраторы", loadingHtml);
  try {
    const [, list] = await Promise.all([freshChat(c), api(`${chatPath(c.account_id, c.id)}/admins`)]);
    renderAdmins(c, list);
  } catch (e) { $("#modal-body").innerHTML = emptyState("alert", e.message); }
}
function renderAdmins(c, list) {
  const canAdd = c.my_rights?.add_admins;
  modal(`Администраторы · ${c.title}`, `${backBtn}
    <div class="admin-list"></div>
    ${canAdd ? `<button class="btn primary block" id="add-admin" type="button">${icon("plus")} Добавить администратора</button>`
      : '<p class="hint" style="margin-top:8px">Назначать администраторов может только аккаунт с правом «Назначение администраторов».</p>'}`, root => {
    root.querySelector(".back-btn").onclick = () => chatInfoModal(c);
    const box = root.querySelector(".admin-list");
    for (const a of list) {
      const el = document.createElement("div");
      el.className = "list-item" + (a.can_edit ? "" : " static");
      el.appendChild(avatarEl(c.account_id, a.id, a.name, peerColor(a.id), "sm"));
      const role = [a.creator ? "владелец" : a.rank || "администратор", a.bot && "бот"].filter(Boolean).join(" · ");
      el.insertAdjacentHTML("beforeend", `<div class="grow"><b>${esc(a.name)}</b>${a.self ? ' <span class="chip" style="--c:var(--ok)">этот аккаунт</span>' : ""}
        <div class="small muted">${a.username ? "@" + esc(a.username) + " · " : ""}${esc(role)}</div></div>
        ${a.can_edit ? `<span class="muted">${icon("chevron")}</span>` : ""}`);
      if (a.can_edit) el.onclick = () => adminEditModal(c, a);
      box.appendChild(el);
    }
    root.querySelector("#add-admin")?.addEventListener("click", () => adminEditModal(c, null));
  });
}
function adminEditModal(c, a) {
  const rights = ADMIN_RIGHTS[c.type === "channel" ? "channel" : "group"];
  const mine = c.my_rights || {};
  // у нового админа — всё, что может выдать аккаунт; у существующего — его текущие права
  const on = k => a ? !!a.rights[k] : !!mine[k] && !ADMIN_OFF_BY_DEFAULT.has(k);
  modal(a ? a.name : "Новый администратор", `${backBtn}
    <form class="form">
      ${a ? "" : '<label>Пользователь<input name="user" required placeholder="@username, t.me/username или +79991234567" autocomplete="off"></label>'}
      <label>Должность<input name="rank" maxlength="16" value="${esc(a?.rank || "")}" placeholder="администратор" autocomplete="off"></label>
      <div><div class="section-title" style="margin-top:0">Права</div>
        <div class="checks">${rights.map(([k, label]) => `<label class="opt${mine[k] ? "" : " off"}"${mine[k] ? "" : ' title="У аккаунта нет этого права"'}>
          <input type="checkbox" data-right="${k}"${on(k) ? " checked" : ""}${mine[k] ? "" : " disabled"}>${label}</label>`).join("")}</div></div>
      <div class="error"></div>
      <div class="row"><button class="btn primary" type="submit">${a ? "Сохранить" : "Назначить"}</button>
        ${a ? '<button class="btn danger" type="button" id="dismiss-admin">Снять права</button>' : ""}</div>
    </form>`, root => {
    root.querySelector(".back-btn").onclick = () => adminsModal(c);
    root.querySelector("[name=user]")?.focus();
    formSubmit(root, async (fd, form) => {
      const r = {};
      form.querySelectorAll("[data-right]").forEach(i => (r[i.dataset.right] = i.checked));
      const list = await api(`${chatPath(c.account_id, c.id)}/admins`, { method: "POST",
        body: { user: a ? String(a.id) : fd.get("user"), rights: r, rank: fd.get("rank") || "" } });
      toast(a ? "Права обновлены" : "Администратор назначен");
      renderAdmins(c, list);
    });
    root.querySelector("#dismiss-admin")?.addEventListener("click", async () => {
      if (!confirm(`Снять права администратора с «${a.name}»?`)) return;
      try {
        renderAdmins(c, await api(`${chatPath(c.account_id, c.id)}/admins/${a.id}`, { method: "DELETE" }));
        toast("Права сняты");
      } catch (ex) { toast(ex.message, true); }
    });
  });
}
async function chatSettingsModal(c) {
  modal("Настройки", loadingHtml);
  try { await freshChat(c); } catch (e) { return $("#modal-body").innerHTML = emptyState("alert", e.message); }
  const s = c.settings || {}, channel = c.type === "channel", supergroup = c.type === "group" && !c.legacy;
  const check = (name, title, hint, value) => `<label class="check"><input type="checkbox" name="${name}"${value ? " checked" : ""}>
    <span>${title}<span class="small">${hint}</span></span></label>`;
  modal(`Настройки · ${c.title}`, `${backBtn}
    <form class="form">
      ${channel ? check("signatures", "Подписывать сообщения", "К публикациям добавляется имя администратора", s.signatures) : ""}
      ${check("noforwards", "Запретить копирование", "Сообщения нельзя переслать, скопировать или сохранить", s.noforwards)}
      ${supergroup ? check("history", "История чата для новых участников", "Вступившие видят сообщения, отправленные до них", !s.hidden_prehistory) : ""}
      ${supergroup ? `<label>Медленный режим<select name="slowmode">${SLOWMODE.map(([v, l]) =>
        `<option value="${v}"${v === s.slowmode ? " selected" : ""}>${l}</option>`).join("")}</select></label>
        <p class="hint">Как часто участник может отправлять сообщения. На администраторов не действует.</p>` : ""}
      ${!channel && s.permissions ? `<div><div class="section-title" style="margin-top:0">Участники могут</div>
        <div class="checks">${PERMISSION_LABELS.map(([k, l]) => `<label class="opt"><input type="checkbox" data-perm="${k}"${s.permissions[k] ? " checked" : ""}>${l}</label>`).join("")}</div></div>` : ""}
      <div class="error"></div><button class="btn primary block" type="submit">Сохранить</button>
    </form>`, root => {
    root.querySelector(".back-btn").onclick = () => chatInfoModal(c);
    formSubmit(root, async (fd, form) => {
      // отправляем только изменённое: на «то же самое» Telegram отвечает ошибкой
      const body = {}, el = n => form.querySelector(`[name=${n}]`);
      if (el("signatures") && el("signatures").checked !== s.signatures) body.signatures = el("signatures").checked;
      if (el("noforwards").checked !== s.noforwards) body.noforwards = el("noforwards").checked;
      if (el("history") && el("history").checked === s.hidden_prehistory) body.hidden_prehistory = !el("history").checked;
      if (el("slowmode") && Number(el("slowmode").value) !== s.slowmode) body.slowmode = Number(el("slowmode").value);
      const perms = {};
      form.querySelectorAll("[data-perm]").forEach(i => (perms[i.dataset.perm] = i.checked));
      if (Object.keys(perms).some(k => perms[k] !== s.permissions[k])) body.permissions = perms;
      if (!Object.keys(body).length) return chatInfoModal(c);
      Object.assign(c, await api(`${chatPath(c.account_id, c.id)}/settings`, { method: "POST", body }));
      if (isOpen(c) && S.current !== c) Object.assign(S.current, c);
      toast("Настройки сохранены");
      chatInfoModal(c);
    });
  });
}
async function deleteChannel(c) {
  const word = c.type === "channel" ? "канал" : "группу";
  if (!confirm(`Удалить ${word} «${c.title}» для всех участников? Это нельзя отменить.`)) return;
  if (prompt(`Для подтверждения введите название: ${c.title}`) !== c.title) return toast("Название не совпало — ничего не удалено", true);
  try {
    await api(chatPath(c.account_id, c.id), { method: "DELETE" });
    closeModal();
    if (isOpen(c)) { S.current = null; $("#chat").classList.add("empty"); }
    S.dialogs = S.dialogs.filter(x => !(x.account_id === c.account_id && x.id === c.id));
    renderDialogs(); renderRail();
    toast(c.type === "channel" ? "Канал удалён" : "Группа удалена");
  } catch (ex) { toast(ex.message, true); }
}

// ---------- ссылки t.me: открываем в панели ----------
const TG_HOSTS = ["t.me", "telegram.me", "telegram.dog"];
function isTgLink(href) {
  try {
    const u = new URL(href, location.href);
    return u.protocol === "tg:" || TG_HOSTS.includes(u.hostname.replace(/^www\./, ""));
  } catch { return false; }
}
// Ссылки на каналы, ботов и приглашения из сообщений и описаний. Ctrl/Cmd+клик — как раньше, в новой вкладке
document.addEventListener("click", e => {
  const a = e.target.closest("a[href]");
  if (!a || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || !isTgLink(a.href)) return;
  if (a.hasAttribute("data-external")) return;
  const aid = Number(a.closest("[data-aid]")?.dataset.aid) || S.current?.account_id || (S.scope !== "" ? S.scope : 0);
  e.preventDefault();
  if (aid) openTgLink(aid, a.href); else pickAccountThen(id => { closeModal(); openTgLink(id, a.href); });
});
async function openTgLink(aid, href) {
  let r;
  try { r = await api(`api/accounts/${aid}/resolve?link=${encodeURIComponent(href)}`); }
  catch (e) { return toast(e.message, true); }
  if (r.kind === "external") { const url = safeUrl(href); if (url) window.open(url, "_blank", "noopener"); return; }
  if (r.app || r.startapp != null) {
    return openWebApp(aid, { bot: String(r.id), mode: r.app ? "app" : "main", app: r.app || "", start_param: r.startapp || "", title: r.title });
  }
  // свой канал или группа — сразу открываем; остальное — сначала карточка
  if (r.joined && r.id && (r.type === "channel" || r.type === "group")) { closeModal(); return openFromCard(aid, r); }
  linkPreviewModal(aid, r);
}
function openFromCard(aid, r) {
  closeModal();
  openChat({ account_id: aid, id: r.id, title: r.title, type: r.type, username: r.username, unread: 0,
             joined: r.joined, invite: r.invite, post: r.post, webapp: r.webapp });
}
function linkPreviewModal(aid, r) {
  const kind = { user: "Пользователь", bot: "Бот", group: "Группа", channel: "Канал" }[r.type] || "";
  const sub = r.members ? `${r.members.toLocaleString("ru")} ${r.type === "channel" ? "подписчиков" : "участников"}` : kind;
  const join = r.request_needed ? "Подать заявку" : r.type === "channel" ? "Подписаться" : "Вступить";
  const buttons = [];
  if (r.type === "channel" || r.type === "group") {
    if (r.id) buttons.push(["view", r.joined ? "Открыть" : "Посмотреть", r.joined ? "primary" : ""]);
    if (!r.joined) buttons.push(["join", join, "primary"]);
  } else if (r.type === "bot") {
    buttons.push(r.start != null ? ["start", "Запустить", "primary"] : ["view", "Открыть чат", "primary"]);
    if (r.webapp) buttons.push(["app", r.webapp.text || "Приложение", ""]);
  } else buttons.push(["view", "Написать", "primary"]);
  modal(kind, `
    <div class="acc-head"><div id="lp-ava"></div><div class="info">
      <div class="name">${esc(r.title)}${r.verified ? ` <span class="verified">${icon("check")}</span>` : ""}</div>
      <div class="muted small">${esc(sub)}</div></div></div>
    <div class="info-list">
      ${r.username ? `<div class="info-row"><span data-icon="at"></span><span class="val">@${esc(r.username)}</span></div>` : ""}
      ${r.about ? `<div class="info-row"><span data-icon="info"></span><span class="val">${linkify(r.about)}</span></div>` : ""}
      ${r.post ? `<div class="info-row"><span data-icon="msg"></span><span class="val muted small">Ссылка ведёт на пост № ${r.post}</span></div>` : ""}
    </div>
    ${r.request_needed ? '<p class="hint" style="margin:8px 0 0">Вступление по заявке — её должен одобрить администратор.</p>' : ""}
    <div class="row lp-actions">${buttons.map(([a, label, cls]) => `<button class="btn ${cls}" data-a="${a}">${esc(label)}</button>`).join("")}</div>`, root => {
    root.dataset.aid = aid;
    root.querySelector("#lp-ava").appendChild(avatarEl(r.id ? aid : null, r.id, r.title, peerColor(r.id || 0), "lg"));
    root.querySelector(".lp-actions").onclick = async e => {
      const b = e.target.closest("button"); if (!b) return;
      b.disabled = true;
      try {
        if (b.dataset.a === "view") openFromCard(aid, r);
        if (b.dataset.a === "app") { closeModal(); openWebApp(aid, { bot: String(r.id), mode: r.webapp.mode, url: r.webapp.url, title: r.title }); }
        if (b.dataset.a === "start") {
          await api(`${chatPath(aid, r.id)}/messages`, { method: "POST", body: { text: r.start ? `/start ${r.start}` : "/start" } });
          openFromCard(aid, r);
        }
        if (b.dataset.a === "join") {
          const j = await api(`api/accounts/${aid}/join`, { method: "POST", body: r.invite ? { link: r.invite } : { chat_id: r.id } });
          toast(r.type === "channel" ? "Вы подписались" : "Вы вступили в группу");
          openFromCard(aid, { ...r, id: j.id, title: j.title, type: j.type, joined: true });
          reloadDialogsSoon();
        }
      } catch (ex) { toast(ex.message, true); b.disabled = false; }
    };
  });
}

// ---------- мини-приложения ботов ----------
// Приложение работает во фрейме и общается с панелью как с Telegram Web: postMessage({eventType, eventData})
let WA = null;   // открытое приложение: {aid, opts, res, frame, root, timer, confirmClose}
function cssColor(name) {
  // без ||= : встроенный браузер Windows-программы (Qt 5.15.2, Chromium 83) его не знает, и app.js не запускается
  const ctx = cssColor.ctx || (cssColor.ctx = document.createElement("canvas").getContext("2d"));
  ctx.fillStyle = "#000"; ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return ctx.fillStyle;   // браузер приводит цвет к #rrggbb
}
function webAppTheme() {
  const t = {
    bg_color: "--elev", secondary_bg_color: "--surface-2", section_bg_color: "--surface", header_bg_color: "--elev",
    bottom_bar_bg_color: "--elev", text_color: "--text", hint_color: "--muted", subtitle_text_color: "--muted",
    section_header_text_color: "--muted", link_color: "--accent", accent_text_color: "--accent", button_color: "--accent",
    destructive_text_color: "--danger", section_separator_color: "--faint",
  };
  const out = { button_text_color: "#ffffff" };
  for (const [k, v] of Object.entries(t)) out[k] = cssColor(v);
  return out;
}
async function openWebApp(aid, opts) {
  closeWebApp(true);
  const root = document.createElement("div");
  root.className = "webapp-overlay";
  root.innerHTML = `<div class="webapp" role="dialog" aria-modal="true">
    <header>
      <button class="icon-btn sm wa-back" hidden title="Назад">${icon("back")}</button>
      <div class="wa-title">${esc(opts.title || "Приложение")}</div>
      <button class="icon-btn sm wa-reload" title="Перезагрузить">${icon("refresh")}</button>
      <button class="icon-btn sm wa-ext" title="Открыть в новой вкладке">${icon("external")}</button>
      <button class="icon-btn sm wa-close" title="Закрыть">${icon("x")}</button>
    </header>
    <div class="wa-body"><div class="wa-loading"><div class="spinner"></div><div class="small muted wa-slow" hidden>
      Приложение долго не отвечает. Некоторые запрещают показ внутри других сайтов — откройте его в новой вкладке ${icon("external")}</div></div></div>
    <div class="wa-buttons" hidden><button class="wa-btn secondary" hidden></button><button class="wa-btn main" hidden></button></div>
  </div>`;
  document.body.appendChild(root);
  WA = { aid, opts, root, res: null, frame: null, timer: null, confirmClose: false };
  const wa = WA;
  root.querySelector(".wa-close").onclick = () => closeWebApp();
  root.querySelector(".wa-back").onclick = () => waSend("back_button_pressed");
  root.querySelector(".wa-btn.main").onclick = () => waSend("main_button_pressed");
  root.querySelector(".wa-btn.secondary").onclick = () => waSend("secondary_button_pressed");
  root.querySelector(".wa-ext").onclick = () => wa.res && window.open(wa.res.url, "_blank", "noopener");
  root.querySelector(".wa-reload").onclick = () => wa.frame && loadWebAppFrame(wa);
  root.addEventListener("mousedown", e => { if (e.target === root) closeWebApp(); });
  try {
    wa.res = await api(`api/accounts/${aid}/webapp`, { method: "POST", body: {
      bot: opts.bot, mode: opts.mode, chat_id: opts.chat_id ?? null, url: opts.url || "", app: opts.app || "",
      start_param: opts.start_param || "", theme: webAppTheme() } });
  } catch (e) {
    if (WA !== wa) return;
    root.querySelector(".wa-body").innerHTML = emptyState("alert", e.message);
    return;
  }
  if (WA !== wa) return;
  root.querySelector(".wa-title").textContent = wa.res.title || opts.title || "Приложение";
  loadWebAppFrame(wa);
  // кнопки под сообщением и меню бота держат сеанс открытым — иначе ответ бота не дойдёт
  if (wa.res.query_id) {
    wa.timer = setInterval(() => api(`api/accounts/${aid}/webapp/prolong`, { method: "POST",
      body: { bot: opts.bot, query_id: wa.res.query_id, chat_id: opts.chat_id ?? null } })
      .catch(() => clearInterval(wa.timer)), 55000);
  }
}
function loadWebAppFrame(wa) {
  const body = wa.root.querySelector(".wa-body");
  body.querySelector("iframe")?.remove();
  body.querySelector(".wa-loading").hidden = false;
  const slow = body.querySelector(".wa-slow");
  slow.hidden = true;
  clearTimeout(wa.slowTimer); wa.slowTimer = setTimeout(() => (slow.hidden = false), 8000);
  const frame = document.createElement("iframe");
  frame.src = wa.res.url;
  frame.allow = "clipboard-write; fullscreen; camera; microphone; geolocation";
  frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads");
  frame.onload = () => setTimeout(() => { if (WA === wa) body.querySelector(".wa-loading").hidden = true; }, 300);
  body.appendChild(frame);
  wa.frame = frame;
}
function closeWebApp(force = false) {
  if (!WA) return;
  if (!force && WA.confirmClose && !confirm("Закрыть приложение? Изменения могут не сохраниться.")) return;
  clearInterval(WA.timer); clearTimeout(WA.slowTimer);
  WA.root.remove(); WA = null;
}
function waSend(eventType, eventData = {}) {
  WA?.frame?.contentWindow?.postMessage(JSON.stringify({ eventType, eventData }), "*");
}
function waButton(kind, p) {
  const b = WA.root.querySelector(`.wa-btn.${kind}`);
  b.hidden = !p.is_visible || !p.text;
  b.disabled = p.is_active === false;
  b.classList.toggle("loading", !!p.is_progress_visible);
  b.textContent = p.text || "";
  // цвета задаёт само приложение; без них — цвета панели из CSS
  b.style.background = p.color || ""; b.style.color = p.text_color || "";
  WA.root.querySelector(".wa-buttons").hidden = [...WA.root.querySelectorAll(".wa-btn")].every(x => x.hidden);
}
function waPopup(p) {
  const buttons = p.buttons?.length ? p.buttons : [{ id: "", type: "close" }];
  const text = [p.title, p.message].filter(Boolean).join("\n\n");
  let id;
  if (buttons.length === 1) { alert(text); id = buttons[0].id; }
  else {
    const ok = buttons.find(b => b.type !== "cancel" && b.type !== "close") || buttons[0];
    const cancel = buttons.find(b => b !== ok);
    id = confirm(text) ? ok.id : cancel?.id ?? "";
  }
  waSend("popup_closed", { button_id: id });
}
const WA_UNSUPPORTED = {
  web_app_request_phone: ["phone_requested", { status: "cancelled" }, "Номер телефона из панели не передаётся"],
  web_app_request_write_access: ["write_access_requested", { status: "cancelled" }],
  web_app_open_scan_qr_popup: ["scan_qr_popup_closed", {}, "Сканер QR в панели не поддерживается"],
  web_app_check_home_screen: ["home_screen_checked", { status: "unsupported" }],
  web_app_biometry_get_info: ["biometry_info_received", { available: false }],
  web_app_check_location: ["location_checked", { available: false }],
};
function onWebAppEvent(type, d) {
  const frame = WA.frame;
  switch (type) {
    case "web_app_ready": WA.root.querySelector(".wa-loading").hidden = true; break;
    case "web_app_close": closeWebApp(true); break;
    case "web_app_request_theme": waSend("theme_changed", { theme_params: webAppTheme() }); break;
    case "web_app_request_viewport":
      waSend("viewport_changed", { height: frame.clientHeight, width: frame.clientWidth, is_expanded: true, is_state_stable: true }); break;
    case "web_app_request_safe_area": waSend("safe_area_changed", { top: 0, bottom: 0, left: 0, right: 0 }); break;
    case "web_app_request_content_safe_area": waSend("content_safe_area_changed", { top: 0, bottom: 0, left: 0, right: 0 }); break;
    case "web_app_setup_main_button": waButton("main", d); break;
    case "web_app_setup_secondary_button": waButton("secondary", d); break;
    case "web_app_setup_back_button": WA.root.querySelector(".wa-back").hidden = !d.is_visible; break;
    case "web_app_setup_closing_behavior": WA.confirmClose = !!d.need_confirmation; break;
    case "web_app_open_link": { const url = safeUrl(d.url); if (url) window.open(url, "_blank", "noopener"); break; }
    case "web_app_open_tg_link": { const aid = WA.aid; closeWebApp(true); openTgLink(aid, `https://t.me${d.path_full || ""}`); break; }
    case "web_app_open_popup": waPopup(d); break;
    case "web_app_read_text_from_clipboard": waSend("clipboard_text_received", { req_id: d.req_id, data: null }); break;
    case "web_app_request_fullscreen":
      WA.root.classList.add("full"); waSend("fullscreen_changed", { is_fullscreen: true }); break;
    case "web_app_exit_fullscreen":
      WA.root.classList.remove("full"); waSend("fullscreen_changed", { is_fullscreen: false }); break;
    case "web_app_open_invoice":
      waSend("invoice_closed", { slug: d.slug, status: "cancelled" });
      toast("Оплата в мини-приложениях из панели не поддерживается — откройте его в Telegram", true); break;
    case "web_app_data_send": case "web_app_switch_inline_query": case "web_app_send_prepared_message": case "web_app_share_to_story":
      toast("Это действие мини-приложения работает только в Telegram", true); break;
    default: {
      const u = WA_UNSUPPORTED[type];
      if (u) { waSend(u[0], u[1]); if (u[2]) toast(u[2], true); }
      else if (/^web_app_(device|secure)_storage_/.test(type)) {
        waSend(type.includes("secure") ? "secure_storage_failed" : "device_storage_failed", { req_id: d.req_id, error: "UNSUPPORTED" });
      } else if (type === "web_app_invoke_custom_method") {
        waSend("custom_method_invoked", { req_id: d.req_id, error: "UNSUPPORTED" });
      }
    }
  }
}
window.addEventListener("message", e => {
  if (!WA?.frame || e.source !== WA.frame.contentWindow) return;
  let msg;
  try { msg = typeof e.data === "string" ? JSON.parse(e.data) : e.data; } catch { return; }
  if (!msg?.eventType) return;
  let data = msg.eventData ?? {};
  if (typeof data === "string") { try { data = JSON.parse(data); } catch { data = {}; } }
  onWebAppEvent(msg.eventType, data || {});
});
document.addEventListener("keydown", e => { if (e.key === "Escape" && WA && $("#modal").hidden) closeWebApp(); });

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
  tipEl?.remove(); tipEl = null;
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
  S.folders = await api("api/folders");
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
          ? await api(`api/folders/${f.id}/items?account_id=${d.account_id}&chat_id=${d.id}`, { method: "DELETE" })
          : await api(`api/folders/${f.id}/items`, { method: "POST", body: { account_id: d.account_id, chat_id: d.id } });
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
  Object.assign(f, await api(`api/folders/${f.id}/items?account_id=${d.account_id}&chat_id=${d.id}`, { method: "DELETE" }));
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
      if (folder) f = await api(`api/folders/${folder.id}`, { method: "PATCH", body: { name: fd.get("name") } });
      else {
        f = await api("api/folders", { method: "POST", body: { name: fd.get("name") } });
        if (addChat) f = await api(`api/folders/${f.id}/items`, { method: "POST", body: { account_id: addChat.account_id, chat_id: addChat.id } });
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
      await api(`api/folders/${f.id}`, { method: "DELETE" });
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

// ---------- поддержка проекта ----------
// Те же ссылки, что в разделах README «Поддержка» и «Поддержать». Цвета — фирменные цвета площадок
const REPO = "https://github.com/Dosash/web_panel_acc";
const SUPPORT_DONATE = [
  ["https://pay.cloudtips.ru/p/894f4248", "card", "Банковская карта", "CloudTips — любая сумма, без регистрации"],
  ["https://t.me/send?start=IVoQmPAfgWnM", "wallet", "Telegram-кошелёк", "Криптовалюта через @send"],
];
const SUPPORT_LINKS = [
  [`${REPO}/issues`, "bug", "GitHub Issues", "Ошибки, идеи и вопросы по панели", "#8b949e"],
  ["https://dosash.ru", "globe", "dosash.ru", "Сайт автора", "#00b8d4"],
  ["https://twitch.tv/dosash", "tv", "Twitch", "twitch.tv/dosash", "#9146ff"],
  ["https://kick.com/dosash1", "tv", "Kick", "kick.com/dosash1", "#53fc18"],
  ["https://youtube.com/@dosash", "play", "YouTube", "youtube.com/@dosash", "#ff0000"],
  ["https://discord.gg/WubwwU2bpM", "msg", "Discord", "Сервер RedImpact", "#5865f2"],
];
function supportModal() {
  const link = (url, inner, cls) => `<a class="${cls}" href="${esc(url)}" target="_blank" rel="noopener noreferrer" data-external>${inner}</a>`;
  modal("Поддержка", `
    <div class="support-head"><div class="brand-mark" data-icon="plane"></div><div>
      <div class="name">TG Panel${S.version ? ` <span class="muted small">${esc(S.version)}</span>` : ""}</div>
      <div class="muted small">Автор — ${link("https://github.com/Dosash", "Dosash", "")} · лицензия MIT · ${link(REPO, "исходный код", "")}</div>
      <div class="small upd-line">${updateLine()}</div>
    </div></div>
    <div class="section-title">${icon("heart")} Поддержать</div>
    <p class="support-text">Если панель пригодилась — можно поблагодарить автора. Это не обязательно, но очень приятно и помогает развивать проект.</p>
    <div class="donate">${SUPPORT_DONATE.map(([url, ic, title, sub]) =>
      link(url, `<span class="ti">${icon(ic)}</span><span><b>${title}</b><span class="small">${sub}</span></span>`, "donate-card")).join("")}</div>
    <p class="support-text">Ещё помогают ⭐ на GitHub и ссылка на автора или репозиторий — в описании своего проекта или в канале.</p>
    ${link(REPO, `${icon("star")} Звезда на GitHub`, "btn block")}
    <div class="section-title">Поддержка</div>
    <p class="support-text">Вопросы, идеи и сообщения об ошибках — в Issues или на любой из площадок:</p>
    <div class="support-links">${SUPPORT_LINKS.map(([url, ic, title, sub, color]) =>
      link(url, `<span class="si" style="--c:${color}">${icon(ic)}</span><span><b>${title}</b><span class="small muted">${sub}</span></span>${icon("external")}`, "support-link")).join("")}</div>`);
}
$("#support").onclick = supportModal;

// ---------- обновления ----------
// Сервер раз в 6 часов смотрит последний релиз на GitHub. Значок справа внизу — когда новее панель на
// сервере или программа для компьютера; оттуда — обновить программу, панель на сервере или скачать с GitHub
const UPD = { info: null, intro: false };
const verNum = v => (String(v || "").match(/\d+/g) || []).slice(0, 3).map(Number);
function isNewer(a, b) {
  const x = verNum(a), y = verNum(b);
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0);
  return false;
}
// Программа для компьютера с 0.11 сообщает свою версию и режим и обновляется переходом на tg-desktop/update.
// Программа 0.10 знает только TG_DESKTOP; с этой страницей она может быть лишь в режиме «на моём сервере»
// (в своём режиме у неё старый интерфейс без значка)
function desktopApp() {
  return window.TG_DESKTOP_APP || (window.TG_DESKTOP ? { version: "0.10.0", mode: "remote", update: false } : null);
}
function updateTargets(u) {
  const app = desktopApp(), local = app?.mode === "local";   // свой сервер программы обновляется вместе с ней
  return { app: !!app && (local ? u.available : isNewer(u.latest, app.version)), server: !!u.available && !local };
}
async function checkUpdate(force = false) {
  try { UPD.info = await api(`api/update${force ? "?force=1" : ""}`); } catch { return null; }
  renderUpdateBadge();
  return UPD.info;
}
function renderUpdateBadge() {
  const u = UPD.info, b = $("#update-badge"), t = u?.latest ? updateTargets(u) : {};
  const show = (t.app || t.server) && readPref("update_hidden", "") !== u.latest;
  b.hidden = !show;
  $("#app").classList.toggle("has-update", !!show);
  if (!show) return;
  b.querySelector(".t").textContent = `Обновление ${u.latest}`;
  b.title = `Вышла TG Panel ${u.latest}`;
  if (!UPD.intro && $("#chat").classList.contains("empty")) {   // при первом показе — с подписью (пока подпись не закрывает поле ввода), потом только значок
    UPD.intro = true;
    b.classList.add("open");
    setTimeout(() => b.classList.remove("open"), 6000);
  }
}
$("#update-badge").onclick = () => updateModal();
function updateLine() {
  const u = UPD.info;
  if (!u?.enabled) return "";
  const t = u.latest ? updateTargets(u) : {};
  if (t.app || t.server) return `<a href="#" data-upd="open">${icon("update")} Доступна версия ${esc(u.latest)}</a>`;
  return `<span class="muted">${u.latest ? "Последняя версия · " : ""}</span><a href="#" data-upd="check">Проверить обновления</a>`;
}
document.addEventListener("click", async e => {
  const a = e.target.closest("[data-upd]");
  if (!a) return;
  e.preventDefault();
  if (a.dataset.upd === "open") return updateModal();
  a.textContent = "Проверяем…";
  const u = await checkUpdate(true);
  if (!u) { a.textContent = "Проверить обновления"; return toast("Не удалось проверить обновления", true); }
  const t = u.latest ? updateTargets(u) : {};
  if (t.app || t.server) return updateModal();
  if (u.error && !u.latest) { a.textContent = "Проверить обновления"; return toast(`GitHub не ответил: ${u.error}`, true); }
  a.parentElement.innerHTML = updateLine();
  toast(`У вас последняя версия${u.latest ? ` — ${u.latest}` : ""}`);
});
// Описание релиза — раздел CHANGELOG.md: абзацы, списки (с переносом строк), **жирный**, `код`
function releaseNotes(md) {
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const blocks = [];
  let list = null;
  for (const line of String(md).replace(/\r/g, "").split("\n")) {
    if (/^\s*[-*] /.test(line)) { if (!list) blocks.push(list = []); list.push(line.replace(/^\s*[-*] /, "")); }
    else if (list && /^\s+\S/.test(line)) list[list.length - 1] += " " + line.trim();
    else { list = null; if (line.trim()) blocks.push(line.replace(/^#+\s*/, "")); }
  }
  return blocks.map(b => Array.isArray(b) ? `<ul>${b.map(li => `<li>${inline(li)}</li>`).join("")}</ul>` : `<p>${inline(b)}</p>`).join("");
}
function updateModal() {
  const u = UPD.info;
  if (!u?.latest) return;
  const t = updateTargets(u), app = desktopApp();
  const date = u.published_at ? new Date(u.published_at).toLocaleDateString("ru", { day: "numeric", month: "long", year: "numeric" }) : "";
  const ver = (label, cur) => `<div class="upd-ver"><span class="muted">${label}</span><b>${esc(cur || "—")}</b>${icon("arrowR")}<b class="new">${esc(u.latest)}</b></div>`;
  const cmd = u.docker ? "git pull && docker compose up -d --build" : "git pull && .venv/bin/pip install -r requirements.txt";
  const page = u.page || `${REPO}/releases/latest`;
  let html = `
    <div class="upd-head"><span class="upd-ico">${icon("update")}</span><div>
      <div class="name">Вышла TG Panel ${esc(u.latest)}</div>
      <div class="muted small">${date ? `Выпущена ${esc(date)}` : "Новая версия на GitHub"}</div>
    </div></div>
    <div class="upd-vers">
      ${t.server ? ver("Панель на сервере", u.current) : ""}
      ${t.app ? ver(app.mode === "local" ? "Программа" : "Программа на компьютере", app.mode === "local" ? u.current : app.version) : ""}
    </div>`;
  if (u.notes) html += `<div class="section-title">Что нового</div><div class="upd-notes">${releaseNotes(u.notes)}</div>`;
  if (t.app) html += `<div class="section-title">Программа</div>` + (app.update
    ? `<p class="support-text">Программа скачает версию для вашей системы и перезапустится — аккаунты переподключатся сами.</p>
       <button id="upd-app" class="btn primary block">${icon("download")} Обновить программу</button>`
    : `<p class="support-text">Программа обновится сама в течение 6 часов. Сразу — значок TG Panel в трее → «Проверить обновления».</p>`);
  if (t.server) html += `<div class="section-title">Панель на сервере</div>
    <p class="support-text">Выполните в папке панели на сервере${u.docker ? " (там, где <code>docker-compose.yml</code>)" : ", затем перезапустите панель"} — аккаунты, папки и настройки сохранятся:</p>
    <div class="upd-cmd"><code>${esc(cmd)}</code><button class="icon-btn sm" data-copy="${esc(cmd)}" title="Скопировать">${icon("copy")}</button></div>
    <p class="muted small">После обновления сервера страница панели подхватит новую версию после перезагрузки (F5) — на всех устройствах сразу.</p>`;
  html += `<div class="section-title">GitHub</div>
    <a class="btn block" href="${esc(page)}" target="_blank" rel="noopener noreferrer" data-external>${icon("external")} Скачать с GitHub</a>
    <p class="muted small upd-hint">Описание выпуска и файлы программы для Windows, Linux и macOS</p>
    <div class="upd-foot"><button id="upd-hide" class="btn sm">Не напоминать об этой версии</button></div>`;
  modal("Обновление", html, body => {
    body.querySelector("#upd-app")?.addEventListener("click", () => {
      closeModal();
      toast("Программа проверяет обновление — дальше она спросит сама");
      location.href = "tg-desktop/update";   // переход ловит программа (desktop/shell.py) и остаётся на странице
    });
    body.querySelector("[data-copy]")?.addEventListener("click", async e => {
      const ok = await copyText(e.currentTarget.dataset.copy);
      toast(ok ? "Команда скопирована" : "Не удалось скопировать — выделите команду вручную", !ok);
    });
    body.querySelector("#upd-hide").onclick = () => {
      writePref("update_hidden", u.latest);
      renderUpdateBadge(); closeModal();
      toast("Значок скрыт до следующей версии — проверить можно в «Поддержке»");
    };
  });
}

// ---------- встроенные боты: бот постинга и бот рекламы (app/bots.py) ----------
// Кнопка в рейке открывает бота на месте списка чатов и ленты: не настроен — экран запуска
// (токен, администраторы), работает — его собственная веб-панель во фрейме (тот же адрес и вход).
const BOTS = { list: [], current: null, setup: false, frame: null, poll: 0 };
const BOT_STATUS = { off: "Выключен", starting: "Запускается…", stopping: "Останавливается…", running: "Работает", error: "Ошибка запуска" };
const BOT_ICON = { posts: "newspaper", ads: "megaphone" };
const botInfo = name => BOTS.list.find(b => b.name === name);
async function loadBots() {
  try { BOTS.list = await api("api/bots"); } catch { BOTS.list = []; }
  renderBotTools();
}
function renderBotTools() {
  for (const el of document.querySelectorAll(".bot-tool")) {
    const b = botInfo(el.dataset.bot);
    el.classList.toggle("on", BOTS.current === el.dataset.bot);
    const st = b?.configured ? { running: "online", starting: "connecting", stopping: "connecting", error: "error" }[b.status] || "" : "";
    el.querySelector(".dot").className = "dot " + st;
    if (b) el.dataset.tip = [b.title, b.username && "@" + b.username,
      b.configured ? BOT_STATUS[b.status] : "Не подключён — нажмите, чтобы указать токен"].filter(Boolean).join("\n");
  }
}
function openBot(name) {
  if (BOTS.current !== name) { BOTS.frame = null; BOTS.setup = false; }
  BOTS.current = name;
  $("#app").classList.add("bot-mode");
  $("#bot-view").hidden = false;
  renderRail();
  renderBotView();
  loadBots().then(() => BOTS.current === name && renderBotView());
}
function closeBotView() {
  if (!BOTS.current) return;
  BOTS.current = null; BOTS.frame = null; BOTS.setup = false;
  clearTimeout(BOTS.poll);
  $("#app").classList.remove("bot-mode");
  $("#bot-view").hidden = true;
  $("#bot-body").innerHTML = "";
  renderBotTools();
  renderRail();
}
async function refreshBot() {
  await loadBots();
  if (BOTS.current) renderBotView();
}
function renderBotView() {
  const b = botInfo(BOTS.current);
  renderBotTools();
  if (!b) return;
  $("#bot-view .bot-ico").innerHTML = icon(BOT_ICON[b.name]);
  $("#bot-view .bot-title").textContent = b.bot_name ? `${b.title} · ${b.bot_name}` : b.title;
  $("#bot-view .bot-sub").textContent = [b.username && "@" + b.username, b.configured ? BOT_STATUS[b.status] : "Не подключён"]
    .filter(Boolean).join(" · ");
  $("#bot-reload").hidden = b.status !== "running" || BOTS.setup;
  $("#bot-window").hidden = !b.configured || BOTS.setup;
  $("#bot-settings").hidden = !b.configured;
  $("#bot-settings").classList.toggle("on", BOTS.setup);
  clearTimeout(BOTS.poll);
  const body = $("#bot-body");
  if (!b.configured || BOTS.setup) {
    BOTS.frame = null;
    if (!body.querySelector(".bot-setup")) botSetup(body, b);
    return;
  }
  if (b.status === "running") {
    if (BOTS.frame !== b.name) {
      body.innerHTML = `<iframe class="bot-frame" src="bots/${b.name}/" title="${esc(b.title)}"></iframe>`;
      BOTS.frame = b.name;
    }
    BOTS.poll = setTimeout(refreshBot, 15000);   // заметить, если бот упал или перезапускается
    return;
  }
  BOTS.frame = null;
  let html;
  if (b.status === "starting" || b.status === "stopping") {
    html = b.status === "starting"
      ? `<div class="spinner"></div><h3>Бот запускается…</h3><p class="muted">Обычно это занимает несколько секунд.</p>`
      : `<div class="spinner"></div><h3>Бот останавливается…</h3><p class="muted">Начатые публикации завершатся — это может занять до минуты.</p>`;
  } else if (b.status === "error") {
    html = `<span class="bot-state-ico err">${icon("bot")}</span><h3>Бот не запустился</h3>
      ${b.error ? `<pre class="bot-error">${esc(b.error)}</pre>` : ""}
      <p class="muted">Панель повторяет запуск сама. Проверьте токен в настройках запуска или посмотрите журнал.</p>
      <div class="bot-actions"><button class="btn" data-act="log">${icon("file")} Журнал</button>
      <button class="btn primary" data-act="setup">${icon("settings")} Настройки запуска</button></div>`;
  } else {
    html = `<span class="bot-state-ico">${icon(BOT_ICON[b.name])}</span><h3>Бот выключен</h3>
      <p class="muted">Пока бот выключен, он не отвечает в Telegram и не публикует посты.</p>
      <div class="bot-actions"><button class="btn primary" data-act="start">${icon("power")} Запустить</button></div>`;
  }
  body.innerHTML = `<div class="bot-state">${html}<div class="bot-log" hidden></div></div>`;
  body.querySelector("[data-act=start]")?.addEventListener("click", async e => {
    e.currentTarget.disabled = true;
    try { await api(`api/bots/${b.name}/start`, { method: "POST" }); } catch (ex) { toast(ex.message, true); }
    refreshBot();
  });
  body.querySelector("[data-act=setup]")?.addEventListener("click", () => { BOTS.setup = true; renderBotView(); });
  body.querySelector("[data-act=log]")?.addEventListener("click", async () => {
    const box = body.querySelector(".bot-log");
    const { lines } = await api(`api/bots/${b.name}/log`);
    box.textContent = lines.join("\n") || "Журнал пуст";
    box.hidden = false;
    box.scrollTop = box.scrollHeight;
  });
  if (["starting", "stopping", "error"].includes(b.status)) BOTS.poll = setTimeout(refreshBot, b.status === "error" ? 5000 : 1500);
}
function botSetup(body, b) {
  const people = [...S.accounts.values()].filter(a => a.user_id);
  const known = new Set(people.map(a => a.user_id));
  const chosen = new Set(b.admin_ids);
  const extra = b.admin_ids.filter(id => !known.has(id)).join(", ");
  const adminHint = b.name === "posts"
    ? "Только они смогут пользоваться ботом. Если никого не выбрать, владельцем станет первый, кто напишет боту /start."
    : "Они получают заказы на модерацию и видят админ-меню бота. Покупатели рекламы — все остальные.";
  body.innerHTML = `<div class="bot-setup"><div class="bot-card">
    <div class="bot-hero">${icon(BOT_ICON[b.name])}</div>
    <h2>${esc(b.title)}</h2>
    <p class="muted">${esc(b.about)}</p>
    <form class="form">
      <label>Токен бота<input name="token" autocomplete="off" spellcheck="false" ${b.configured ? "" : "required"}
        placeholder="${b.configured ? `Оставить прежний (${esc(b.token)})` : "123456789:AAE…"}"></label>
      <p class="hint">Создайте бота в <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer" data-external>@BotFather</a>
        командой /newbot и вставьте его токен. Чтобы бот публиковал в канал, сделайте его администратором канала.</p>
      <label>Администраторы бота</label>
      ${people.length ? `<div class="checks">${people.map(a => `<label class="opt"><input type="checkbox" name="admin" value="${a.user_id}"
        ${chosen.has(a.user_id) ? "checked" : ""}>${esc(a.full_name || a.name)}<span class="muted small">${esc(a.username ? "@" + a.username : String(a.user_id))}</span></label>`).join("")}</div>` : ""}
      <input name="admin_extra" value="${esc(extra)}" placeholder="${people.length ? "Другие Telegram ID через запятую" : "Telegram ID через запятую"}">
      <p class="hint">${adminHint}</p>
      <label>Часовой пояс<input name="timezone" value="${esc(b.timezone)}" placeholder="Europe/Moscow"></label>
      <div class="error"></div>
      <div class="row">
        ${b.configured ? `<button type="button" class="btn" data-act="cancel">Отмена</button>` : ""}
        <button class="btn primary" type="submit">${icon("power")} ${b.configured ? "Сохранить и перезапустить" : "Подключить и запустить"}</button>
      </div>
      ${b.configured && b.status !== "off" ? `<button type="button" class="btn block danger" data-act="stop">Выключить бота</button>` : ""}
      ${b.configured ? `<p class="hint">Цены, каналы, оплата, пароль и остальное настраиваются в панели самого бота.</p>` : ""}
    </form></div></div>`;
  hydrateIcons(body);
  body.querySelector("[data-act=cancel]")?.addEventListener("click", () => { BOTS.setup = false; renderBotView(); });
  body.querySelector("[data-act=stop]")?.addEventListener("click", async e => {
    e.currentTarget.disabled = true;
    try { await api(`api/bots/${b.name}/stop`, { method: "POST" }); toast("Бот выключен"); } catch (ex) { toast(ex.message, true); }
    BOTS.setup = false; refreshBot();
  });
  formSubmit(body, async fd => {
    const ids = [...fd.getAll("admin"), ...String(fd.get("admin_extra")).split(/[\s,;]+/)].filter(Boolean);
    if (ids.some(x => !/^\d{3,15}$/.test(x))) throw new Error("Telegram ID — это число, например 123456789");
    const token = String(fd.get("token")).trim();
    const res = await api(`api/bots/${b.name}`, { method: "PUT", body: {
      token: token || null, admin_ids: ids.map(Number), timezone: String(fd.get("timezone")).trim() } });
    BOTS.list = BOTS.list.map(x => x.name === res.name ? res : x);
    BOTS.setup = false; BOTS.frame = null;
    toast(res.username ? `@${res.username} запускается` : "Бот запускается");
    renderBotView();
  });
}
// Панель бота в отдельном окне: в браузере — окно-попап (одно на бота, повторно — то же окно),
// в программе для ПК окно открывает сама программа (desktop/shell.py, ViewerWindow)
function openBotWindow(name) {
  const w = window.open(`bots/${name}/`, `tgpanel-bot-${name}`, "popup,width=1280,height=860");
  if (!w) toast("Браузер не дал открыть окно — разрешите всплывающие окна для панели", true);
}
function botCtxMenu(name, x, y) {
  const b = botInfo(name);
  if (!b) return;
  const items = [
    { icon: BOT_ICON[name], label: "Открыть в панели", run: () => openBot(name) },
  ];
  if (b.configured) {
    items.push({ icon: "external", label: "Открыть в отдельном окне", run: () => openBotWindow(name) });
    if (!desktopApp()) items.push({ icon: "link", label: "Открыть в новой вкладке", run: () => window.open(`bots/${name}/`, "_blank") });
    items.push("sep", { icon: "settings", label: "Настройки запуска", run: () => { openBot(name); BOTS.setup = true; renderBotView(); } });
    items.push(b.status === "off"
      ? { icon: "power", label: "Запустить", run: async () => { await api(`api/bots/${name}/start`, { method: "POST" }); refreshBot(); } }
      : { icon: "power", label: "Выключить", danger: true, run: async () => {
          await api(`api/bots/${name}/stop`, { method: "POST" }); toast("Бот выключен"); refreshBot(); } });
  }
  ctxMenu(x, y, items, [b.title, b.username && "@" + b.username].filter(Boolean).join(" · "));
}
for (const el of document.querySelectorAll(".bot-tool")) {
  el.onclick = () => openBot(el.dataset.bot);
  el.oncontextmenu = e => { e.preventDefault(); botCtxMenu(el.dataset.bot, e.clientX, e.clientY); };
}
$("#bot-window").onclick = () => openBotWindow(BOTS.current);
$("#bot-settings").onclick = () => { BOTS.setup = !BOTS.setup; renderBotView(); };
$("#bot-reload").onclick = () => { const f = $("#bot-body .bot-frame"); if (f) f.src = f.src; };

// ---------- невидимка и тема ----------
function renderGhost() {
  const b = $("#toggle-ghost");
  b.innerHTML = icon(S.ghost ? "ghost" : "eye");
  b.classList.toggle("on", S.ghost);
  b.dataset.tip = S.ghost ? "Невидимка включена\nсообщения не отмечаются прочитанными" : "Невидимка выключена\nоткрытые чаты отмечаются прочитанными";
}
$("#toggle-ghost").onclick = () => { S.ghost = !S.ghost; writePref("ghost", S.ghost ? "1" : "0"); renderGhost(); toast(S.ghost ? "Невидимка включена" : "Невидимка выключена"); };
function applyTheme(t) {
  const html = document.documentElement;
  if (html.dataset.theme && html.dataset.theme !== t) {
    html.classList.add("theming");
    clearTimeout(applyTheme.timer); applyTheme.timer = setTimeout(() => html.classList.remove("theming"), 450);
  }
  html.dataset.theme = t;
  writePref("theme", t);
  writePref("panel-theme", t);   // тот же ключ читают панели встроенных ботов
  const frame = $("#bot-body .bot-frame");
  try { if (frame?.contentDocument) frame.contentDocument.documentElement.dataset.theme = t; } catch { /* ещё грузится */ }
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
  try { sess = await api("api/session"); } catch { return showLogin(); }
  $("#login").hidden = true; $("#app").hidden = false;
  $("#logout").hidden = !sess.auth;
  S.version = sess.version || "";
  await Promise.all([loadAccounts(), loadFolders(), loadBots()]);
  // #bot=posts|ads — сразу открыть бота (сюда ведут старые адреса /posts/ и /ads/)
  const want = /^#bot=(\w+)$/.exec(location.hash)?.[1];
  if (want && botInfo(want)) { history.replaceState(null, "", location.pathname + location.search); openBot(want); }
  await loadDialogs();
  if (!started) {
    started = true;
    connectWS();
    checkUpdate();
    setInterval(checkUpdate, 3600e3);   // сервер спрашивает GitHub раз в 6 часов, здесь — его кэш
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  }
}
start();
