"use strict";
/* Демо-ролик TG Panel. Вся сцена детерминирована: renderAt(t) выставляет состояние на момент t (секунды).
   Данные — выдуманные, как на скриншотах в README. */

const FPS = 60, DUR = 44.4;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function icon(name, cls = "") {
  const body = ICONS[name] || "", filled = name === "more" || name === "plane";
  return `<svg class="i ${filled ? "fill" : ""} ${cls}" viewBox="0 0 24 24" aria-hidden="true">${body}</svg>`;
}
function fillIcons(root) { $$("[data-icon]", root).forEach(s => { if (!s.firstChild) s.innerHTML = icon(s.dataset.icon); }); }
const clamp = (v, a = 0, b = 1) => v < a ? a : v > b ? b : v, lerp = (a, b, t) => a + (b - a) * t, seg = (t, a, b) => clamp((t - a) / (b - a));
const E = {
  lin: t => t, io: t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2, out: t => 1 - Math.pow(1 - t, 3), in: t => t * t * t,
  out5: t => 1 - Math.pow(1 - t, 5), in2: t => t * t, out2: t => 1 - (1 - t) * (1 - t),
  spr: t => 1 - Math.exp(-6.5 * t) * Math.cos(7.5 * t),      // с перелётом ~9 %
  sprS: t => 1 - Math.exp(-7 * t) * Math.cos(5 * t),          // мягкий перелёт ~3 %
};
const px = v => `${v.toFixed(2)}px`;

/* ================= таймлайн (секунды) ================= */
const TL = {
  flyStart: 3.5, flyEnd: 4.75, panel: 4.8,
  cursorIn: 7.6, clickAcc: 9.0,
  newMsg: 12.0, clickDlg: 13.4, chatOpen: 13.45, clickComposer: 14.8, type0: 15.0, clickSend: 17.8, sent: 17.85,
  clickAll: 19.4, clickCh: 20.4, chOpen: 20.45, hoverApp: 23.0, clickApp: 23.6, overlayOpen: 23.65, overlayLoaded: 24.4, clickClose: 26.3, overlayClose: 26.4,
  clickBot: 27.2, botOpen: 27.25, themeClick: 31.8, themeDone: 32.7, phone: 33.6, outro: 36.0, end: DUR,
};
const TYPED = "Синий есть, отложу для вас 🙂 Приходите после 15:00";
const TYPED_CHARS = Array.from(TYPED);
const CHAR_T = TYPED_CHARS.map((c, i) => TL.type0 + i * 0.046 + (i % 3) * 0.004 + (c === " " ? 0.012 : 0));
const TERM_CMD = "docker compose up -d";
const TERM_T = Array.from(TERM_CMD).map((c, i) => 39.7 + i * 0.062 + (i % 2) * 0.006);

/* ================= данные ================= */
const ACC = [
  { id: 1, name: "Продажи", full: "Анна Морозова", init: "АМ", color: "#4f8cff", user: "anna_store_demo" },
  { id: 2, name: "Поддержка", full: "Сергей Зайцев", init: "СЗ", color: "#2ecc8f", user: "sergey_help" },
  { id: 3, name: "Канал", full: "Дмитрий Ковалёв", init: "ДК", color: "#f5a524", user: "dk_media" },
  { id: 4, name: "Реклама", full: "Рита Лебедева", init: "РЛ", color: "#a36cf7", user: "rita_ads" },
  { id: 5, name: "Личный", full: "Макс Орлов", init: "МО", color: "#f2555a", user: "max_o" },
];
const accOf = id => ACC.find(a => a.id === id);
const DLG0 = [
  { id: "news", acc: 3, type: "channel", title: "Новости проекта", init: "НП", color: "#2ecc8f", time: "01:51", text: "🚀 Вышла версия 0.13: импорт из файлов .session", pinned: true },
  { id: "shop", acc: 1, type: "bot", title: "Магазин Demo", init: "MD", color: "#2ecc8f", time: "01:50", text: "Заказ #1042 оформлен ✅ Доставка завтра" },
  { id: "vip", acc: 2, type: "group", title: "Клиенты · VIP", init: "KV", color: "#2ecc8f", time: "01:45", text: "Мария: спасибо за быстрый ответ!", unread: 14 },
  { id: "ivan", acc: 1, type: "user", title: "Иван Петров", init: "ИП", color: "#2ecc8f", time: "01:48", text: "Отлично! А синий есть в наличии?", unread: 1, user: "ivan_demo" },
  { id: "design", acc: 4, type: "channel", title: "Дизайн и вдохновение", init: "ДИ", color: "#f5a524", time: "01:27", text: "Подборка интерфейсов недели", unread: 5, media: "Фото" },
  { id: "olga", acc: 2, type: "user", title: "Ольга Смирнова", init: "ОС", color: "#f5a524", time: "01:13", text: "Отправила счёт на почту, проверьте", you: true },
  { id: "team", acc: 1, type: "group", title: "Команда продаж", init: "КП", color: "#f5a524", time: "00:56", text: "План на неделю в закрепе 📌" },
  { id: "py", acc: 5, type: "channel", title: "Python-разработчики", init: "P", color: "#f2555a", time: "00:39", text: "Кто пробовал Telethon с FastAPI?", unread: 37, muted: true },
  { id: "alex", acc: 2, type: "user", title: "Алексей", init: "А", color: "#f2555a", time: "чт", text: "", media: "Голосовое сообщение" },
  { id: "weather", acc: 1, type: "bot", title: "Погода", init: "П", color: "#f5a524", time: "чт", text: "Москва: +12°, облачно" },
  { id: "ads", acc: 4, type: "group", title: "Реклама · заказы", init: "РЗ", color: "#a36cf7", time: "ср", text: "Новый заказ на размещение — 3 поста" },
];
function dialogsAt(s) {
  let list = DLG0.map(d => ({ ...d }));
  if (s.newMsg) {
    const iv = list.find(d => d.id === "ivan");
    iv.time = "01:50"; iv.unread = 2; iv.text = "Хочу забрать сегодня, если можно 🙂";
    list = [iv, ...list.filter(d => d !== iv)];
  }
  if (s.sent) { const iv = list.find(d => d.id === "ivan"); iv.time = "01:52"; iv.unread = 0; iv.text = TYPED; iv.you = true; }
  if (s.chat === "ivan") list.find(d => d.id === "ivan").unread = 0;
  if (s.scope) list = list.filter(d => d.acc === s.scope);
  return list;
}
const CHATS = {
  vip: {
    title: "Клиенты · VIP", acc: 2, type: "group", init: "KV", color: "#2ecc8f", sub: "32 участн.", msgs: [
      { day: "Сегодня" },
      { from: "Мария", c: "#f5a524", text: "Добрый день! Подскажите, когда придёт заказ #1038?", time: "01:20" },
      { out: true, text: "Здравствуйте, Мария! Курьер будет сегодня до 18:00 🚚", time: "01:22" },
      { from: "Олег", c: "#a36cf7", text: "А можно оформить доставку в другой город?", time: "01:31" },
      { out: true, text: "Конечно — СДЭК или Почта России, 2–4 дня.", time: "01:33" },
      { from: "Мария", c: "#f5a524", text: "Спасибо за быстрый ответ!", time: "01:45" },
    ],
  },
  ivan: {
    title: "Иван Петров", acc: 1, type: "user", init: "ИП", color: "#2ecc8f", sub: "@ivan_demo", msgs: [
      { day: "Вчера" },
      { text: "Здравствуйте! Видел у вас рюкзак «Городской 25 л» — он ещё в продаже?", time: "22:54" },
      { out: true, text: "Добрый день, Иван! Да, есть в чёрном и сером цвете. Доставка по городу — на следующий день 🚚", time: "22:56" },
      { out: true, text: "Цена 4 990 ₽, при оплате онлайн — скидка 5%.", time: "22:57" },
      { day: "Сегодня" },
      { quote: "Добрый день, Иван! Да, есть в чёрном и сером цвете. Доставка по городу …", text: "Отлично! А синий есть в наличии?", time: "01:48" },
      { text: "Хочу забрать сегодня, если можно 🙂", time: "01:50", id: "new" },
      { out: true, text: TYPED, time: "01:52", id: "sent" },
    ],
  },
  news: {
    title: "Новости проекта", acc: 3, type: "channel", init: "НП", color: "#2ecc8f", sub: "3 482 участн.", msgs: [
      { day: "Вчера" },
      { out: true, html: `Как мы ведём <b>12 аккаунтов</b> из одного окна: цветные метки, общий список диалогов и <i>папки</i>, в которых собраны чаты разных аккаунтов.`, time: "00:54", views: "2 140", web: { site: "GitHub", title: "Dosash/web_panel_acc", desc: "Веб-панель для нескольких Telegram-аккаунтов" } },
      { day: "Сегодня" },
      { out: true, html: `<b>Опрос недели:</b> что добавить следующим? Голосуйте в комментариях 👇 <span class="tag">#планы</span>`, time: "01:04", views: "1 530" },
      { out: true, html: `🚀 <b>Вышла версия 0.13</b>\n\n<b>Импорт из файлов .session</b> — Telethon и Pyrogram, по одному или пачкой. <b>Мини-приложения ботов</b> открываются прямо в панели.\n\nОбновление — одной командой: <code>docker compose up -d --build</code>`, time: "01:51", views: "1 284", pinned: true,
        kb: [[{ t: "Открыть на GitHub", ic: "link" }], [{ t: "Приложение", ic: "grid", app: true }, { t: "Обсудить", ic: "link" }]] },
    ],
  },
};

/* ================= сборка DOM панели ================= */
const panel = $("#panel"), world = $("#world"), stage = $("#stage");
function avatar(d, cls = "") { return `<div class="avatar ${cls}" style="--c:${d.color}">${esc(d.init)}</div>`; }
function buildRail(s) {
  return `<nav class="rail">
    <div class="brand-mark" data-icon="plane"></div>
    <button class="rail-item all${!s.scope && !s.bot ? " active" : ""}" data-id="all"><span data-icon="layers"></span></button>
    <div class="rail-sep"></div>
    <div id="rail-accounts" class="rail-accounts">${ACC.map(a => {
      const unread = !s.scope ? dialogsAt({ ...s, scope: 0 }).filter(d => d.acc === a.id && d.unread && !d.muted).length : 0;
      return `<button class="rail-item acc${s.scope === a.id && !s.bot ? " active" : ""}" data-id="${a.id}" style="--c:${a.color}">
        <div class="avatar" style="--c:${a.color}">${a.init}</div><span class="dot online"></span>${unread ? `<span class="badge">${unread}</span>` : ""}</button>`;
    }).join("")}</div>
    <button class="rail-item add" data-id="add"><span data-icon="plus"></span></button>
    <div class="rail-spacer"></div>
    <button class="rail-tool bot-tool${s.bot ? " on" : ""}" data-bot="posts"><span data-icon="newspaper"></span><span class="dot online"></span></button>
    <button class="rail-tool bot-tool" data-bot="ads"><span data-icon="megaphone"></span><span class="dot online"></span></button>
    <button id="toggle-ghost" class="rail-tool on"><span data-icon="ghost"></span></button>
    <button id="toggle-theme" class="rail-tool"><span data-icon="${s.theme === "light" ? "moon" : "sun"}"></span></button>
    <button id="support" class="rail-tool support"><span data-icon="dollar"></span></button>
    <button id="logout" class="rail-tool"><span data-icon="logout"></span></button>
  </nav>`;
}
function dialogHtml(d, all, active) {
  const a = accOf(d.acc);
  const typeIcon = { channel: "channel", group: "group", bot: "bot" }[d.type];
  const preview = `${d.you ? `<span class="you">Вы: </span>` : ""}${d.media ? `<span class="media-label">${esc(d.media)}</span>${d.text ? ", " : ""}` : ""}${esc(d.text)}`;
  return `<div class="dialog${active ? " active" : ""}${d.unread ? " has-unread" : ""}" data-id="${d.id}" style="--c:${a.color}">
    ${avatar(d)}${all ? `<span class="acc-mark"></span>` : ""}
    <div>
      <div class="d-row"><span class="d-name">${typeIcon ? icon(typeIcon) : ""}<span class="t">${esc(d.title)}</span></span>
        ${all ? `<span class="chip" style="--c:${a.color}">${esc(a.name)}</span>` : ""}<span class="d-time">${d.time}</span></div>
      <div class="d-row"><span class="d-text">${preview}</span>
        <span class="d-flags">${d.muted ? icon("muted") : ""}${d.pinned && !all ? icon("pin") : ""}${d.unread ? `<span class="badge${d.muted ? " dim" : ""}">${d.unread}</span>` : ""}</span></div>
    </div></div>`;
}
function buildSidebar(s) {
  const a = s.scope ? accOf(s.scope) : null;
  const list = dialogsAt(s);
  return `<aside class="sidebar">
    <header class="sidebar-head">
      <div class="scope"><div class="scope-text">
        <div class="scope-title">${a ? esc(a.name) : "Все аккаунты"}</div>
        <div class="scope-sub muted">${a ? `@${a.user} · В сети` : "5 из 5 в сети"}</div></div>
        <button class="icon-btn" id="new-chat"><span data-icon="edit"></span></button>
        ${a ? `<button class="icon-btn" id="account-menu"><span data-icon="more"></span></button>` : ""}</div>
      <label class="search"><span data-icon="search"></span><input type="search" placeholder="Поиск по чатам" readonly></label>
      <div class="folder-tabs"><button class="ftab active">Все чаты</button><button class="ftab">Непрочитанные</button>
        <button class="ftab">${icon("folder")}Клиенты<span class="ftab-n">2</span></button><button class="ftab">${icon("archive")}Архив</button></div>
    </header>
    <div class="dialog-list">${list.map(d => dialogHtml(d, !s.scope, d.id === s.chat)).join("")}</div>
  </aside>`;
}
function msgHtml(m, prev, next, type) {
  if (m.day) return `<div class="day-sep">${m.day}</div>`;
  const same = (a, b) => a && b && !a.day && !!a.out === !!b.out && a.from === b.from;
  const first = !same(prev, m), last = !same(m, next);
  const cls = `msg${m.out ? " out" : ""}${first ? " grp-first" : ""}${last ? " grp-last" : ""}`;
  const text = m.html != null ? m.html.replace(/\n/g, "\n") : esc(m.text);
  const meta = `${m.views ? `${icon("eye")}${m.views} · ` : ""}${m.pinned ? icon("pin") : ""}${m.time}`;
  const web = m.web ? `<a class="webpage"><span class="wp-site">${m.web.site}</span><b>${m.web.title}</b><span class="wp-desc">${m.web.desc}</span></a>` : "";
  const kb = m.kb ? `<div class="kb">${m.kb.map(row => `<div class="kb-row">${row.map(b =>
    `<button class="kb-btn"${b.app ? ' data-app="1"' : ""}>${esc(b.t)}<span class="kb-ic">${icon(b.ic)}</span></button>`).join("")}</div>`).join("")}</div>` : "";
  return `<div class="${cls}"${m.id ? ` data-mid="${m.id}"` : ""}><div class="bubble">${first && m.from && type === "group" ? `<div class="sender" style="--sc:${m.c}">${esc(m.from)}</div>` : ""}${
    m.quote ? `<div class="quote">${esc(m.quote)}</div>` : ""}${text}${web}<span class="meta">${meta}</span></div>${kb}</div>`;
}
function buildChat(s) {
  const c = CHATS[s.chat], a = accOf(c.acc);
  let msgs = c.msgs;
  if (s.chat === "ivan") msgs = msgs.filter(m => (m.id !== "new" || s.newMsg) && (m.id !== "sent" || s.sent));
  const composerBody = s.chat === "news"
    ? `<div class="readonly-bar">${icon("lock")} Только чтение — вы не администратор канала</div>`
    : `<form class="composer${s.chat === "ivan" && s.focus ? " focus" : ""}">
        <label class="icon-btn"><span data-icon="clip"></span></label>
        <div class="typed"><span class="ph">Сообщение</span></div>
        <button class="send" type="button"><span data-icon="send"></span></button></form>`;
  return `<section class="chat">
    <header class="chat-head">
      <button class="icon-btn back"><span data-icon="back"></span></button>
      <div class="chat-avatar">${avatar(c, "sm")}</div>
      <div class="chat-meta"><div class="chat-title">${esc(c.title)}</div>
        <div class="chat-sub"><span class="chip" style="--c:${a.color}">${esc(a.name)}</span><span>${esc(c.sub)}</span></div></div>
      <button class="icon-btn"><span data-icon="info"></span></button>
    </header>
    <div class="chat-body"><div class="messages">${msgs.map((m, i) => msgHtml(m, msgs[i - 1], msgs[i + 1], c.type)).join("")}</div></div>
    <div class="composer-wrap">${composerBody}</div>
  </section>`;
}
function buildBot() {
  const nav = [["Публикации"], ["grid", "Обзор", true], ["edit", "Новый пост"], ["file", "Посты"], ["clock", "Контент-план"], ["Каналы"], ["channel", "Каналы", false, 1], ["sliders", "Статистика"], ["Система"], ["settings", "Настройки"]];
  const days = ["Пн 20", "Вт 21", "Ср 22", "Чт 23", "Пт 24", "Сб 25", "Вс 26"];
  const plan = [["09:00 Акция в «Зерне»", "g|18:00 Подкаст"], ["12:00 Итоги месяца"], ["10:00 Круассан 🥐"], ["o|15:00 Розыгрыш"], ["09:00 Нейросети: мифы", "19:00 Дайджест"], [], ["11:00 Анонс недели"]];
  return `<section class="bot-view">
    <header class="bot-head"><span class="bot-ico">${icon("newspaper")}</span>
      <div class="bot-meta"><div class="bot-title">Бот постинга · Мои каналы</div><div class="bot-sub muted">@my_posting_bot · Работает</div></div>
      <button class="icon-btn"><span data-icon="refresh"></span></button><button class="icon-btn"><span data-icon="external"></span></button><button class="icon-btn"><span data-icon="settings"></span></button>
    </header>
    <div class="bot-body"><div class="bd">
      <nav class="bd-nav"><div class="bd-brand"><span class="ico">${icon("newspaper")}</span><div><b>Посты</b><span>Публикация в каналы</span></div></div>
        ${nav.map(n => n.length === 1 ? `<div class="bd-sec">${n[0]}</div>` : `<div class="bd-item${n[2] ? " active" : ""}">${icon(n[0])}${n[1]}${n[3] ? `<span class="badge">${n[3]}</span>` : ""}</div>`).join("")}
        <div class="bd-foot"><span>${icon("moon")}</span><span>v2.7.0</span></div></nav>
      <div class="bd-main">
        <div class="bd-top"><div><h2>Обзор</h2><p>Бот <b>@my_posting_bot</b> публикует посты в ваши каналы</p></div><div class="sp"></div>
          <span class="bd-btn">${icon("plus")}Новый пост</span><span class="bd-status"><i></i>Работает</span></div>
        <div class="bd-stats">
          ${[["Каналы", 12, "ещё 1 ждёт подтверждения"], ["Подписчики", 58010, "во всех каналах"], ["Опубликовано", 7, "постов за неделю"], ["Запланировано", 5, "в контент-плане"], ["Черновики", 2, "не опубликованы"]]
            .map(([k, v, s]) => `<div class="bd-stat"><div class="k">${k}</div><div class="v" data-n="${v}">0</div><div class="s">${s}</div></div>`).join("")}
        </div>
        <div class="bd-cols">
          <div class="bd-card"><header>Контент-план<span>${icon("clock")}Эта неделя</span></header>
            <div class="bd-plan">${days.map((d, i) => `<div class="bd-day${i === 4 ? " today" : ""}"><b>${d.split(" ")[0]} <em>${d.split(" ")[1]}</em></b>${plan[i].map(e => { const [cls, t] = e.includes("|") ? e.split("|") : ["", e]; return `<div class="ev ${cls}">${t}</div>`; }).join("")}</div>`).join("")}</div></div>
          <div class="bd-card"><header>Последние посты<span>Все посты</span></header>
            ${[["g", "☕ Осенняя акция в кофейне «Зерно»", "Опубликован 24.10, 09:00 · Кофейня «Зерно»", "pub", "Опубликован"],
               ["b", "📸 Итоги месяца в фото — лучшие кадры подписчиков", "Черновик · Мой блог", "draft", "Черновик"],
               ["", "🥐 Новинка: круассан с фисташкой", "Запланирован на 22.10, 10:00 · Пекарня «Кусь»", "sch", "Запланирован"],
               ["", "🧠 Нейросети: 5 мифов, в которые до сих пор верят", "Запланирован на 24.10, 09:00 · Гаджеты", "sch", "Запланирован"],
               ["", "🎧 Подкаст: как выбрать наушники", "Запланирован на 20.10, 18:00 · Книжный", "sch", "Запланирован"]]
              .map(([th, t, s, p, pt]) => `<div class="bd-row"><span class="th ${th}">${th ? "" : icon("file")}</span><div class="txt"><b>${t}</b><small>${s}</small></div><span class="pill ${p}">${pt}</span></div>`).join("")}
          </div>
        </div>
      </div>
    </div></div>
  </section>`;
}
function buildOverlay() {
  const items = [["🎒", "Городской 25 л", "4 990 ₽"], ["👜", "Сумка-шопер", "2 490 ₽"], ["🧢", "Кепка", "1 290 ₽"], ["🧳", "Дорожная 40 л", "7 990 ₽"]];
  return `<div class="webapp-overlay"><div class="webapp">
    <header class="wa-head"><button class="icon-btn sm wa-back"><span data-icon="back"></span></button><span class="wa-title">Магазин Demo</span>
      <button class="icon-btn sm"><span data-icon="refresh"></span></button><button class="icon-btn sm"><span data-icon="external"></span></button><button class="icon-btn sm wa-close"><span data-icon="x"></span></button></header>
    <div class="wa-body"><div class="wa-progress"></div>
      <div class="wa-loading"><div class="spinner"></div><div class="muted small">Открываем приложение бота…</div></div>
      <div class="wa"><div><h3>Магазин Demo</h3><div class="sub">Доставка завтра · бесплатно от 3 000 ₽</div></div>
        <div class="wa-tabs"><span class="wa-tab on">Все</span><span class="wa-tab">Рюкзаки</span><span class="wa-tab">Сумки</span><span class="wa-tab">Аксессуары</span></div>
        <div class="wa-grid">${items.map(([e, t, p]) => `<div class="wa-card"><div class="img">${e}</div><b>${t}</b><small>${p}</small><button class="wa-btn">В корзину</button></div>`).join("")}</div></div>
      <div class="wa-foot"><span class="wa-btn">Оформить заказ · 4 990 ₽</span></div>
    </div></div></div>`;
}
function buildPhone() {
  const c = CHATS.ivan, a = accOf(c.acc), msgs = c.msgs;
  return `<div class="notch"></div><div class="ph"><section class="chat">
    <header class="chat-head"><button class="icon-btn back"><span data-icon="back"></span></button><div class="chat-avatar">${avatar(c, "sm")}</div>
      <div class="chat-meta"><div class="chat-title">${c.title}</div><div class="chat-sub"><span class="chip" style="--c:${a.color}">${a.name}</span><span>${c.sub}</span></div></div>
      <button class="icon-btn"><span data-icon="info"></span></button></header>
    <div class="chat-body"><div class="messages">${msgs.map((m, i) => msgHtml(m, msgs[i - 1], msgs[i + 1], "user")).join("")}</div></div>
    <div class="composer-wrap"><form class="composer"><label class="icon-btn"><span data-icon="clip"></span></label><div class="typed"><span class="ph">Сообщение</span></div><button class="send" type="button"><span data-icon="send"></span></button></form></div>
  </section></div>`;
}

/* ================= состояние на момент t ================= */
function stateAt(t) {
  const s = { scope: 0, chat: "vip", bot: false, overlay: false, theme: "dark", newMsg: t >= TL.newMsg, sent: t >= TL.sent, focus: false };
  if (t >= TL.clickAcc && t < TL.clickAll) s.scope = 1;
  if (t >= TL.chatOpen) s.chat = "ivan";
  if (t >= TL.chOpen) s.chat = "news";
  if (t >= TL.clickComposer && t < TL.sent + 0.4) s.focus = true;
  if (t >= TL.overlayOpen && t < TL.overlayClose + 0.3) s.overlay = true;
  if (t >= TL.botOpen) s.bot = true;
  if (t >= TL.themeDone) s.theme = "light";
  s.key = [s.scope, s.chat, s.bot, s.overlay, s.theme, s.newMsg, s.sent, s.focus].join("|");
  return s;
}
let builtKey = null, lightKey = null;
function build(s) {
  panel.innerHTML = buildRail(s) + buildSidebar(s) + buildChat(s) + (s.bot ? buildBot() : "") + (s.overlay ? buildOverlay() : "")
    + `<svg id="cursor" viewBox="0 0 30 38"><path d="M4 3v26l6.5-6.3 4.4 10.4 4.2-1.8-4.4-10.2H23z" fill="#fff" stroke="#0b1220" stroke-width="1.8" stroke-linejoin="round"/></svg><div id="ripple"></div>`;
  fillIcons(panel);
  if (s.bot) { $(".sidebar", panel).style.display = "none"; $(".chat", panel).style.display = "none"; }
  builtKey = s.key;
}
/* позиция элемента в координатах панели (без учёта 3D-трансформаций) */
function panelPos(el, fx = .5, fy = .5) {
  let x = 0, y = 0, e = el;
  while (e && e !== panel) { x += e.offsetLeft; y += e.offsetTop; e = e.offsetParent; }
  return { x: x + el.offsetWidth * fx, y: y + el.offsetHeight * fy };
}

/* ================= камера ================= */
function monoSpline(keys, field) {
  const n = keys.length, xs = keys.map(k => k.t), ys = keys.map(k => k[field]);
  const d = [], m = new Array(n).fill(0);
  for (let i = 0; i < n - 1; i++) d.push((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]));
  m[0] = d[0]; m[n - 1] = d[n - 2];
  for (let i = 1; i < n - 1; i++) m[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
  for (let i = 0; i < n - 1; i++) {
    if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; continue; }
    const a = m[i] / d[i], b = m[i + 1] / d[i], q = a * a + b * b;
    if (q > 9) { const tau = 3 / Math.sqrt(q); m[i] = tau * a * d[i]; m[i + 1] = tau * b * d[i]; }
  }
  return t => {
    if (t <= xs[0]) return ys[0]; if (t >= xs[n - 1]) return ys[n - 1];
    let i = 0; while (xs[i + 1] < t) i++;
    const h = xs[i + 1] - xs[i], u = (t - xs[i]) / h, u2 = u * u, u3 = u2 * u;
    return (2 * u3 - 3 * u2 + 1) * ys[i] + (u3 - 2 * u2 + u) * h * m[i] + (-2 * u3 + 3 * u2) * ys[i + 1] + (u3 - u2) * h * m[i + 1];
  };
}
const CAMK = [
  { t: 0,    x: 0,    y: 0,    z: -180,  rx: 5, ry: -12, s: 1 },
  { t: 2.4,  x: 0,    y: 0,    z: -90,   rx: 3, ry: -2,  s: 1 },
  { t: 3.6,  x: 0,    y: 0,    z: 0,     rx: 2, ry: 6,   s: 1 },
  { t: 4.8,  x: 200,  y: 70,   z: 80,    rx: 4, ry: 14,  s: 1 },
  { t: 6.4,  x: 90,   y: 12,   z: 40,    rx: 2, ry: 7,   s: 1 },
  { t: 7.8,  x: 0,    y: 0,    z: 0,     rx: 0, ry: 0,   s: 1 },
  { t: 11.8, x: 0,    y: 0,    z: 0,     rx: 0, ry: 0,   s: 1.03 },
  { t: 13.4, x: 0,    y: 0,    z: 0,     rx: 0, ry: 0,   s: 1 },
  { t: 15.4, x: -250, y: -100, z: 0,     rx: 0, ry: 0,   s: 1.18 },
  { t: 17.6, x: -270, y: -110, z: 0,     rx: 0, ry: 0,   s: 1.2 },
  { t: 19.2, x: 0,    y: 0,    z: 0,     rx: 0, ry: 0,   s: 1 },
  { t: 20.6, x: 0,    y: 0,    z: 0,     rx: 0, ry: 0,   s: 1 },
  { t: 22.6, x: -140, y: 90,   z: 0,     rx: 0, ry: -3,  s: 1.18 },
  { t: 25.8, x: -160, y: 80,   z: 0,     rx: 0, ry: -2,  s: 1.2 },
  { t: 27.2, x: 0,    y: 0,    z: 0,     rx: 0, ry: 0,   s: 1 },
  { t: 29.0, x: -50,  y: 70,   z: 0,     rx: 0, ry: 0,   s: 1.08 },
  { t: 31.0, x: -90,  y: -40,  z: 0,     rx: 0, ry: 0,   s: 1.1 },
  { t: 32.9, x: 0,    y: 0,    z: 0,     rx: 0, ry: 0,   s: 1 },
  { t: 34.6, x: -150, y: 0,    z: -200,  rx: 3, ry: 12,  s: 1 },
  { t: 36.0, x: -170, y: 0,    z: -240,  rx: 3, ry: 14,  s: 1 },
  { t: 38.0, x: 0,    y: 60,   z: -1150, rx: 8, ry: 0,   s: 1 },
  { t: 44.4, x: 0,    y: 90,   z: -1350, rx: 9, ry: -5,  s: 1 },
];
const CAMF = Object.fromEntries(["x", "y", "z", "rx", "ry", "s"].map(f => [f, monoSpline(CAMK, f)]));
function camAt(t) {
  const c = Object.fromEntries(Object.entries(CAMF).map(([k, f]) => [k, f(t)]));
  // лёгкий дрейф: камера никогда не стоит полностью
  c.x += 7 * Math.sin(t * .62); c.y += 5 * Math.cos(t * .47); c.ry += .55 * Math.sin(t * .38); c.rx += .35 * Math.cos(t * .29);
  return c;
}
const camTransform = c => `translate3d(${px(c.x)}, ${px(c.y)}, ${px(c.z)}) rotateX(${c.rx.toFixed(3)}deg) rotateY(${c.ry.toFixed(3)}deg) scale(${c.s.toFixed(4)})`;

/* ================= курсор ================= */
const CUR = [
  { t: TL.cursorIn, at: { x: 1560, y: 1180 } },
  { t: 8.6, sel: '.rail-item.acc[data-id="1"]' },
  { t: TL.clickAcc, click: true },
  { t: 9.7, sel: '.rail-item.acc[data-id="1"]' },
  { t: 11.0, at: { x: 640, y: 520 } },
  { t: 12.2, at: { x: 600, y: 470 } },
  { t: 13.0, sel: '.dialog[data-id="ivan"]', fx: .56, fy: .5 },
  { t: TL.clickDlg, click: true },
  { t: 14.45, sel: '.composer .typed', fx: .25, fy: .5 },
  { t: TL.clickComposer, click: true },
  { t: 15.6, sel: '.composer .typed', fx: .3, fy: .9 },
  { t: 17.45, sel: '.composer .send' },
  { t: TL.clickSend, click: true },
  { t: 18.3, sel: '.composer .send' },
  { t: 19.05, sel: '.rail-item.all' },
  { t: TL.clickAll, click: true },
  { t: 20.05, sel: '.dialog[data-id="news"]', fx: .5, fy: .5 },
  { t: TL.clickCh, click: true },
  { t: 21.4, at: { x: 1040, y: 560 } },
  { t: TL.hoverApp, sel: '.kb-btn[data-app]', fx: .45, fy: .55 },
  { t: TL.clickApp, click: true },
  { t: 24.9, sel: '.wa-card:nth-child(1) .wa-btn', fx: .5, fy: .5 },
  { t: 25.95, sel: '.wa-close' },
  { t: TL.clickClose, click: true },
  { t: 26.9, sel: '.bot-tool[data-bot="posts"]' },
  { t: TL.clickBot, click: true },
  { t: 28.6, at: { x: 980, y: 430 } },
  { t: 30.5, at: { x: 1180, y: 700 } },
  { t: 31.45, sel: '#toggle-theme' },
  { t: TL.themeClick, click: true },
  { t: 32.7, sel: '#toggle-theme' },
  { t: 33.5, at: { x: 120, y: 1220 } },
];
let lastCur = { x: 1560, y: 1180 };
function curTarget(k) {
  if (k.at) return k.at;
  const el = $(k.sel, panel);
  return el ? panelPos(el, k.fx ?? .5, k.fy ?? .5) : lastCur;
}
function cursorAt(t) {
  if (t < CUR[0].t) return null;
  let i = 0; while (i + 1 < CUR.length && CUR[i + 1].t <= t) i++;
  const a = CUR[i], b = CUR[i + 1];
  let from = a, j = i; while (from.click && j > 0) from = CUR[--j];
  const pa = curTarget(from);
  if (!b || b.click) { lastCur = pa; return { ...pa, target: from.sel, arrived: true }; }
  const pb = curTarget(b), p = E.io(seg(t, a.t, b.t));
  const dx = pb.x - pa.x, dy = pb.y - pa.y, len = Math.hypot(dx, dy) || 1;
  const arc = Math.min(70, len * .14) * Math.sin(Math.PI * p);   // дуга поперёк движения
  const pos = { x: lerp(pa.x, pb.x, p) - dy / len * arc, y: lerp(pa.y, pb.y, p) + dx / len * arc, target: b.sel, arrived: p > .9 };
  lastCur = pos; return pos;
}
const CLICKS = CUR.filter(k => k.click).map(k => k.t);

/* ================= подписи ================= */
const CAPS = [
  { t0: 5.6, t1: 8.7, ic: "layers", text: "Все аккаунты — в одном списке, с цветными метками" },
  { t0: 9.4, t1: 11.7, ic: "user", text: "Выбрали аккаунт — видите только его чаты" },
  { t0: 12.15, t1: 14.5, ic: "bell", text: "Новые сообщения приходят мгновенно" },
  { t0: 15.0, t1: 18.9, ic: "send", text: "Отвечайте из нужного аккаунта" },
  { t0: 20.7, t1: 23.2, ic: "channel", text: "Каналы, посты и кнопки под ними" },
  { t0: 23.9, t1: 26.2, ic: "grid", text: "Мини-приложения ботов — прямо в панели" },
  { t0: 27.7, t1: 31.0, ic: "newspaper", text: "Встроенные боты: постинг и реклама в ваших каналах" },
  { t0: 32.3, t1: 35.7, ic: "sun", text: "Тёмная и светлая темы · с телефона · программа для ПК" },
];
const capsBox = $("#captions");
capsBox.innerHTML = CAPS.map(c => `<div class="cap" style="opacity:0"><span class="ic">${icon(c.ic)}</span>${esc(c.text)}</div>`).join("");
const capEls = $$(".cap", capsBox);
function renderCaps(t) {
  CAPS.forEach((c, i) => {
    const el = capEls[i];
    if (t < c.t0 - .05 || t > c.t1 + .5) { el.style.opacity = 0; return; }
    const pin = E.spr(seg(t, c.t0, c.t0 + .55)), pout = E.in2(seg(t, c.t1, c.t1 + .4));
    el.style.opacity = (Math.min(1, pin * 1.4) * (1 - pout)).toFixed(3);
    el.style.transform = `translateY(${(lerp(34, 0, pin) + 26 * pout).toFixed(2)}px) scale(${(lerp(.94, 1, pin) * (1 - .04 * pout)).toFixed(4)})`;
    el.style.filter = `blur(${(6 * (1 - E.out(seg(t, c.t0, c.t0 + .35))) + 4 * pout).toFixed(2)}px)`;
  });
}

/* ================= интро ================= */
const intro = $("#intro");
const ICARDS = [
  { x: 330, y: 250, z: -260, r: -7, acc: 0, msg: "Иван: а синий есть в наличии?", n: 2 },
  { x: 1330, y: 190, z: 40, r: 5, acc: 1, msg: "Мария: спасибо за быстрый ответ!", n: 14 },
  { x: 300, y: 760, z: 110, r: 4, acc: 2, msg: "Новости проекта: 🚀 версия 0.13", n: 1 },
  { x: 1410, y: 720, z: -330, r: -5, acc: 3, msg: "Реклама · заказы: новый заказ", n: 3 },
  { x: 860, y: 860, z: -120, r: 2, acc: 4, msg: "Python-разработчики: 37 новых", n: 37 },
];
intro.innerHTML = ICARDS.map((c, i) => { const a = ACC[c.acc]; return `<div class="icard" data-i="${i}">
  <div class="bar"><i></i><i></i><i></i><span>Telegram Desktop — окно ${i + 1}</span></div>
  <div class="row">${avatar({ init: a.init, color: a.color })}<div class="txt"><div class="t1">${a.full}</div><div class="t2">${c.msg}</div></div><span class="badge">${c.n}</span></div></div>`; }).join("")
  + `<div id="title"></div>`;
const cardEls = $$(".icard", intro), titleEl = $("#title", intro);
const TITLE1 = ["5 аккаунтов.", " ", "5 окон."], TITLE2 = ["Одно", " ", "окно."];
titleEl.innerHTML = `<div class="t1">${TITLE1.map(w => `<span class="w">${w}</span>`).join("")}</div><div class="t2" style="position:absolute;left:0;right:0;top:0">${TITLE2.map((w, i) => `<span class="w${i === 0 ? " hl" : ""}">${w}</span>`).join("")}</div>`;
let railTargets = null;
function getRailTargets() {
  if (railTargets) return railTargets;
  const had = panel.innerHTML;
  build(stateAt(TL.panel));
  railTargets = ACC.map(a => panelPos($(`.rail-item.acc[data-id="${a.id}"] .avatar`, panel)));
  railTargets.brand = panelPos($(".brand-mark", panel));
  if (had) { panel.innerHTML = had; builtKey = null; }
  return railTargets;
}
function renderIntro(t) {
  if (t >= TL.panel) { intro.style.display = "none"; return; }
  intro.style.display = "";
  const targets = getRailTargets();
  cardEls.forEach((el, i) => {
    const c = ICARDS[i], tin = .35 + i * .28;
    const ap = E.spr(seg(t, tin, tin + .7));
    if (ap <= 0) { el.style.opacity = 0; return; }
    const drift = { x: 16 * Math.sin(t * .9 + i), y: 12 * Math.cos(t * .7 + i * 1.3), z: 40 * Math.sin(t * .5 + i * .8) };
    const fp = E.io(seg(t, TL.flyStart + i * .07, TL.flyEnd - (4 - i) * .04));
    const tg = targets[i];
    const x = lerp(c.x + drift.x, tg.x - 38, fp) - 120 * Math.sin(Math.PI * fp) * (i % 2 ? -1 : 1) * .4;
    const y = lerp(c.y + drift.y, tg.y - 56, fp) - 90 * Math.sin(Math.PI * fp);
    const z = lerp(c.z + drift.z, 160, fp) + 120 * Math.sin(Math.PI * fp);
    const rot = lerp(c.r, 0, fp), sc = lerp(1, 1, fp);
    el.style.opacity = Math.min(1, ap * 1.2).toFixed(3);
    el.style.transform = `translate3d(${px(x)}, ${px(y)}, ${px(z)}) rotateZ(${rot.toFixed(2)}deg) rotateY(${(lerp(-6 + i * 3, 0, fp)).toFixed(2)}deg) scale(${(lerp(.7, 1, ap) * sc).toFixed(4)})`;
    const dof = Math.min(4, Math.abs(z) / 110) * (1 - fp);
    el.style.filter = `blur(${(dof + 10 * (1 - Math.min(1, ap * 1.5))).toFixed(2)}px)`;
    // окно сворачивается в аватар: ширина и шапка схлопываются, остаётся кружок
    const fold = E.io(seg(fp, .15, .85));
    el.style.width = px(lerp(320, 48, fold)); el.style.borderRadius = px(lerp(18, 24, fold));
    el.style.background = fold > .9 ? "transparent" : "";
    el.style.borderColor = fold > .9 ? "transparent" : "";
    el.style.boxShadow = fold > .9 ? "none" : "";
    $(".bar", el).style.height = px(lerp(31, 0, fold)); $(".bar", el).style.opacity = clamp(1 - fold * 2).toFixed(2);
    $(".bar", el).style.overflow = "hidden"; $(".bar", el).style.padding = fold > .5 ? "0" : "";
    $(".row", el).style.padding = `${px(lerp(12, 0, fold))} ${px(lerp(14, 0, fold))} ${px(lerp(14, 0, fold))}`;
    $(".row .txt", el).style.opacity = $(".row .badge", el).style.opacity = clamp(1 - fold * 2.5).toFixed(2);
  });
  // заголовок: слова входят из размытия, затем «5 окон.» сдувается и приходит «Одно окно.»
  const w1 = $$(".t1 .w", titleEl), w2 = $$(".t2 .w", titleEl);
  w1.forEach((w, i) => {
    const pi = E.spr(seg(t, 1.9 + i * .22, 2.6 + i * .22)), po = E.in2(seg(t, 3.25 + i * .05, 3.6 + i * .05));
    w.style.opacity = (Math.min(1, pi * 1.3) * (1 - po)).toFixed(3);
    w.style.transform = `translateY(${lerp(40, 0, pi).toFixed(1)}px) scale(${(lerp(1.25, 1, pi) * lerp(1, .8, po)).toFixed(3)})`;
    w.style.filter = `blur(${(14 * (1 - E.out(seg(t, 1.9 + i * .22, 2.35 + i * .22))) + 12 * po).toFixed(1)}px)`;
    w.style.letterSpacing = `${lerp(.08, -.035, pi).toFixed(3)}em`;
  });
  w2.forEach((w, i) => {
    const pi = E.spr(seg(t, 3.55 + i * .12, 4.15 + i * .12)), po = E.in2(seg(t, 4.55, 4.8));
    w.style.opacity = (Math.min(1, pi * 1.3) * (1 - po)).toFixed(3);
    w.style.transform = `translateY(${lerp(50, 0, pi).toFixed(1)}px) scale(${(lerp(1.3, 1, pi) * lerp(1, 1.25, po)).toFixed(3)})`;
    w.style.filter = `blur(${(14 * (1 - E.out(seg(t, 3.55 + i * .12, 3.95 + i * .12))) + 16 * po).toFixed(1)}px)`;
  });
  titleEl.style.transform = `translateZ(${(60 + 10 * Math.sin(t * .8)).toFixed(1)}px)`;
}

/* ================= финал ================= */
const outro = $("#outro");
outro.innerHTML = `<div id="o-mark">${icon("plane")}</div>
  <div id="o-title">${Array.from("TG Panel").map(ch => `<span class="l">${ch}</span>`).join("")}</div>
  <div id="o-sub">Все Telegram-аккаунты — в одном окне</div>
  <div id="o-term"><span class="p">$ </span><span class="cmd"></span><span class="cur"></span></div>
  <div id="o-ok">✔ Панель запущена: http://localhost:8000</div>
  <div id="o-foot"><b>github.com/Dosash/web_panel_acc</b> · Python + FastAPI + Telethon · MIT</div>`;
const oMark = $("#o-mark"), oLetters = $$("#o-title .l"), oSub = $("#o-sub"), oTerm = $("#o-term"), oCmd = $("#o-term .cmd"), oCur = $("#o-term .cur"), oOk = $("#o-ok"), oFoot = $("#o-foot");
let brandStart = null;
function renderOutro(t) {
  if (t < TL.outro) { outro.style.display = "none"; return; }
  outro.style.display = "block";
  if (!brandStart) {   // откуда вылетает знак: проекция логотипа в рейке в момент начала финала
    const keep = [world.style.transform, world.style.filter];
    world.style.transform = camTransform(camAt(TL.outro)); world.style.filter = "none";
    const r = $(".brand-mark", panel).getBoundingClientRect(), sr = stage.getBoundingClientRect();
    brandStart = { x: r.left - sr.left, y: r.top - sr.top, w: r.width };
    [world.style.transform, world.style.filter] = keep;
  }
  const p = E.io(seg(t, TL.outro + .1, TL.outro + 1.3));
  const scale = lerp(brandStart.w / 148, 1, p), x = lerp(brandStart.x, 960 - 74, p), y = lerp(brandStart.y, 262, p) - 70 * Math.sin(Math.PI * p);
  const bob = 6 * Math.sin((t - TL.outro) * 1.4);
  oMark.style.transform = `translate(${px(x)}, ${px(y + bob * p)}) scale(${scale.toFixed(4)}) rotate(${(lerp(-30, 0, p)).toFixed(2)}deg)`;
  oLetters.forEach((l, i) => {
    const pi = E.spr(seg(t, 37.0 + i * .07, 37.7 + i * .07));
    l.style.opacity = Math.min(1, pi * 1.3).toFixed(3);
    l.style.transform = `translateY(${lerp(60, 0, pi).toFixed(1)}px) scale(${lerp(1.4, 1, pi).toFixed(3)})`;
    l.style.filter = `blur(${(16 * (1 - E.out(seg(t, 37.0 + i * .07, 37.45 + i * .07)))).toFixed(1)}px)`;
  });
  const ps = E.spr(seg(t, 38.3, 38.9));
  oSub.style.opacity = Math.min(1, ps * 1.3).toFixed(3); oSub.style.transform = `translateY(${lerp(24, 0, ps).toFixed(1)}px)`;
  const pt = E.spr(seg(t, 39.3, 39.9));
  oTerm.style.opacity = Math.min(1, pt * 1.3).toFixed(3); oTerm.style.transform = `translate(-50%, ${lerp(30, 0, pt).toFixed(1)}px) scale(${lerp(.9, 1, pt).toFixed(3)})`;
  const n = TERM_T.filter(x => x <= t).length;
  oCmd.textContent = TERM_CMD.slice(0, n);
  oCur.style.opacity = t < 41.3 ? (Math.floor(t * 2.5) % 2 ? .25 : 1) : 0;
  const pok = E.out(seg(t, 41.35, 41.8));
  oOk.style.opacity = pok.toFixed(3); oOk.style.transform = `translateY(${lerp(14, 0, pok).toFixed(1)}px)`;
  const pf = E.out(seg(t, 42.0, 42.6));
  oFoot.style.opacity = pf.toFixed(3); oFoot.style.transform = `translateY(${lerp(14, 0, pf).toFixed(1)}px)`;
  outro.style.transform = `scale(${(1 + .025 * seg(t, 38, 44.4)).toFixed(4)})`;
}

/* ================= главный рендер ================= */
const phone = $("#phone"), panelLight = $("#panel-light"), mbBlur = $("#mb-blur");
let phoneBuilt = false;
function renderAt(t) {
  t = Math.max(0, Math.min(DUR, t));
  const s = stateAt(t);
  if (s.key !== builtKey) build(s);
  document.documentElement.dataset.theme = s.theme;

  // камера + motion blur по скорости экрана
  const c = camAt(t), c0 = camAt(Math.max(0, t - 1 / FPS));
  const vx = (c.x - c0.x) + (c.ry - c0.ry) * 22 + (c.s - c0.s) * 500, vy = (c.y - c0.y) + (c.rx - c0.rx) * 22 + (c.s - c0.s) * 300 + (c.z - c0.z) * .25;
  let bx = Math.min(14, Math.abs(vx) * .42), by = Math.min(14, Math.abs(vy) * .42);
  const dof = 14 * E.io(seg(t, TL.outro + .1, TL.outro + 1.2));   // финал: панель уходит в глубину и из фокуса
  bx += dof; by += dof;
  world.style.transform = camTransform(c);
  if (bx > .45 || by > .45) { mbBlur.setAttribute("stdDeviation", `${bx.toFixed(2)} ${by.toFixed(2)}`); world.style.filter = "url(#mb)"; }
  else world.style.filter = "none";
  world.style.opacity = (1 - E.io(seg(t, TL.outro + .5, TL.outro + 1.8)) * .85).toFixed(3);

  renderIntro(t);
  // раскрытие панели из рейки: слои разнесены в глубину и сходятся в плоскость
  const sep = 1 - E.io(seg(t, TL.panel + .4, 7.9)) + .5 * E.io(seg(t, 34.4, 36.4));
  const rail = $(".rail", panel), side = $(".sidebar", panel), chat = $(".chat", panel), bot = $(".bot-view", panel);
  panel.style.visibility = t < TL.panel ? "hidden" : "";
  rail.style.transform = `translateZ(${px(160 * sep)})`;
  const su = E.sprS(seg(t, TL.panel, TL.panel + 1.1)), cu = E.sprS(seg(t, TL.panel + .18, TL.panel + 1.35));
  side.style.transform = `translateZ(${px(80 * sep)}) translateX(${px(lerp(-140, 0, su))}) rotateY(${lerp(-55, 0, su).toFixed(2)}deg)`;
  side.style.opacity = Math.min(1, su * 1.5).toFixed(3);
  side.style.filter = sep > .02 ? `blur(${(1.2 * sep).toFixed(2)}px)` : "";
  chat.style.transform = `translateX(${px(lerp(-80, 0, cu))}) rotateY(${lerp(-28, 0, cu).toFixed(2)}deg) scale(${lerp(.96, 1, cu).toFixed(4)})`;
  chat.style.opacity = Math.min(1, cu * 1.5).toFixed(3);
  chat.style.filter = sep > .02 ? `blur(${(2.6 * sep).toFixed(2)}px)` : "";

  // список диалогов: каскад появления после смены области
  const listT = s.scope ? TL.clickAcc : t >= TL.clickAll ? TL.clickAll : TL.panel + .25;
  $$(".dialog", panel).forEach((el, i) => {
    const p = E.spr(seg(t, listT + i * .055, listT + .5 + i * .055));
    el.style.opacity = Math.min(1, p * 1.4).toFixed(3);
    let ty = lerp(26, 0, p);
    // новое сообщение: «Иван Петров» всплывает наверх, «Магазин Demo» уступает место
    if (s.newMsg && s.scope === 1 && t < TL.newMsg + .9) {
      const q = E.io(seg(t, TL.newMsg, TL.newMsg + .55)), h = el.offsetHeight;
      if (el.dataset.id === "ivan") ty += lerp(h, 0, q); else if (el.dataset.id === "shop") ty += lerp(-h, 0, q);
      if (el.dataset.id === "ivan") { const b = $(".badge", el); if (b) b.style.transform = `scale(${lerp(0, 1, E.spr(seg(t, TL.newMsg + .15, TL.newMsg + .6))).toFixed(3)})`; }
    }
    el.style.transform = `translateY(${px(ty)})`;
  });
  if (s.newMsg && s.scope === 1) { const iv = $('.dialog[data-id="ivan"]', panel); if (iv) iv.style.boxShadow = `inset 0 0 0 1px rgb(79 140 255 / ${(.6 * (1 - E.out(seg(t, TL.newMsg, TL.newMsg + 1.6)))).toFixed(3)})`; }

  // сообщения: каскад при открытии чата, новое и отправленное — с пружиной
  const chatT = s.chat === "news" ? TL.chOpen : s.chat === "ivan" ? TL.chatOpen : TL.panel + .4;
  const msgs = $$(".messages > *", panel);
  msgs.forEach((el, i) => {
    let p = E.spr(seg(t, chatT + i * .05, chatT + .45 + i * .05)), ty = lerp(22, 0, p), sc = 1, ox = "left";
    if (el.dataset.mid === "new") { p = E.spr(seg(t, TL.newMsg, TL.newMsg + .5)); ty = lerp(18, 0, p); sc = lerp(.9, 1, p); }
    if (el.dataset.mid === "sent") { p = E.spr(seg(t, TL.sent, TL.sent + .55)); ty = lerp(60, 0, p); sc = lerp(.85, 1, p); ox = "right"; }
    el.style.opacity = Math.min(1, p * 1.4).toFixed(3);
    el.style.transformOrigin = `bottom ${ox}`;
    el.style.transform = `translateY(${px(ty)}) scale(${sc.toFixed(4)})`;
  });
  // набор текста в поле ввода
  const typed = $(".composer .typed", panel);
  if (typed && s.chat === "ivan") {
    const n = t >= TL.sent ? 0 : CHAR_T.filter(x => x <= t).length;
    typed.innerHTML = n ? `${esc(TYPED_CHARS.slice(0, n).join(""))}<span class="caret"></span>` : s.focus ? `<span class="ph">Сообщение</span><span class="caret"></span>` : `<span class="ph">Сообщение</span>`;
    const caret = $(".caret", typed); if (caret) caret.style.opacity = Math.floor(t * 2.2) % 2 ? .2 : 1;
  }
  const send = $(".composer .send", panel);
  if (send) { const q = seg(t, TL.clickSend, TL.clickSend + .3); send.style.transform = `scale(${(1 - .18 * Math.sin(Math.PI * q)).toFixed(3)}) rotate(${(-14 * Math.sin(Math.PI * q)).toFixed(1)}deg)`; }

  // мини-приложение
  const ov = $(".webapp-overlay", panel);
  if (ov) {
    const pin = E.out(seg(t, TL.overlayOpen, TL.overlayOpen + .25)), pout = E.in2(seg(t, TL.overlayClose, TL.overlayClose + .28));
    ov.style.opacity = (pin * (1 - pout)).toFixed(3);
    const ps = E.spr(seg(t, TL.overlayOpen, TL.overlayOpen + .55));
    $(".webapp", ov).style.transform = `translateY(${lerp(30, 0, ps).toFixed(1)}px) scale(${(lerp(.9, 1, ps) * (1 - .05 * pout)).toFixed(4)})`;
    const load = seg(t, TL.overlayOpen, TL.overlayLoaded);
    $(".wa-loading", ov).style.opacity = (1 - E.io(seg(t, TL.overlayLoaded - .15, TL.overlayLoaded + .1))).toFixed(3);
    $(".spinner", ov).style.transform = `rotate(${((t - TL.overlayOpen) * 420) % 360}deg)`;
    const pb = $(".wa-progress", ov); pb.style.transform = `scaleX(${E.out(load).toFixed(3)})`; pb.style.opacity = t > TL.overlayLoaded + .3 ? 0 : 1;
    const wa = $(".wa", ov); wa.style.opacity = E.out(seg(t, TL.overlayLoaded - .05, TL.overlayLoaded + .3)).toFixed(3);
    $$(".wa-card", ov).forEach((el, i) => { const p = E.spr(seg(t, TL.overlayLoaded + .05 + i * .09, TL.overlayLoaded + .6 + i * .09)); el.style.opacity = Math.min(1, p * 1.4).toFixed(3); el.style.transform = `translateY(${lerp(28, 0, p).toFixed(1)}px) scale(${lerp(.92, 1, p).toFixed(3)})`; });
    $(".wa-foot", ov).style.opacity = E.out(seg(t, TL.overlayLoaded + .5, TL.overlayLoaded + .8)).toFixed(3);
  }
  // панель бота: въезжает, карточки-показатели подпрыгивают, числа считаются
  if (bot) {
    const pb = E.sprS(seg(t, TL.botOpen, TL.botOpen + .9));
    bot.style.opacity = Math.min(1, pb * 1.5).toFixed(3);
    bot.style.transform = `translateX(${lerp(90, 0, pb).toFixed(1)}px) rotateY(${lerp(-6, 0, pb).toFixed(2)}deg)`;
    $$(".bd-stat", bot).forEach((el, i) => {
      const p = E.spr(seg(t, TL.botOpen + .3 + i * .09, TL.botOpen + .95 + i * .09));
      el.style.opacity = Math.min(1, p * 1.4).toFixed(3); el.style.transform = `translateY(${lerp(34, 0, p).toFixed(1)}px) scale(${lerp(.9, 1, p).toFixed(3)})`;
      const v = $(".v", el), n = +v.dataset.n, q = E.out5(seg(t, TL.botOpen + .4 + i * .09, TL.botOpen + 1.5 + i * .09));
      v.textContent = Math.round(n * q).toLocaleString("ru-RU");
    });
    $$(".bd-card", bot).forEach((el, i) => { const p = E.sprS(seg(t, TL.botOpen + .75 + i * .12, TL.botOpen + 1.5 + i * .12)); el.style.opacity = Math.min(1, p * 1.4).toFixed(3); el.style.transform = `translateY(${lerp(40, 0, p).toFixed(1)}px)`; });
    $$(".bd-row, .bd-day", bot).forEach((el, i) => { const p = E.out(seg(t, TL.botOpen + 1.0 + i * .05, TL.botOpen + 1.4 + i * .05)); el.style.opacity = p.toFixed(3); });
  }
  // смена темы: светлая копия панели раскрывается кругом от кнопки темы
  const rv = seg(t, TL.themeClick, TL.themeDone);
  if (rv > 0 && rv < 1) {
    if (lightKey !== s.key) {
      panelLight.innerHTML = ""; const cl = panel.cloneNode(true); cl.id = "panel-clone"; cl.classList.add("light-scope");
      cl.querySelectorAll("#cursor, #ripple").forEach(e => e.remove()); cl.style.position = "absolute"; cl.style.inset = "0";
      $("#toggle-theme span", cl).innerHTML = icon("moon");
      panelLight.appendChild(cl); lightKey = s.key;
    }
    panelLight.hidden = false;
    const o = panelPos($("#toggle-theme", panel));
    panelLight.style.clipPath = `circle(${px(2300 * E.in2(rv))} at ${px(o.x)} ${px(o.y)})`;
    panelLight.style.transform = rail.style.transform;
  } else { panelLight.hidden = true; if (rv >= 1) { panelLight.innerHTML = ""; lightKey = null; } }
  const themeBtn = $("#toggle-theme", panel);
  if (themeBtn) { const q = seg(t, TL.themeClick, TL.themeClick + .45); themeBtn.style.transform = `scale(${(1 - .2 * Math.sin(Math.PI * q)).toFixed(3)}) rotate(${(180 * E.io(q)).toFixed(1)}deg)`; }

  // телефон
  if (t >= TL.phone - .05) {
    if (!phoneBuilt) { phone.innerHTML = buildPhone(); fillIcons(phone); phoneBuilt = true; }
    phone.hidden = false;
    const p = E.sprS(seg(t, TL.phone, TL.phone + 1.1));
    phone.style.opacity = Math.min(1, p * 1.5).toFixed(3);
    phone.style.transform = `translate3d(${lerp(420, 0, p).toFixed(1)}px, ${(10 * Math.sin((t - TL.phone) * 1.1)).toFixed(1)}px, ${lerp(-100, 120, p).toFixed(1)}px) rotateY(${lerp(-40, -14, p).toFixed(2)}deg) rotateX(${(2 * Math.cos((t - TL.phone) * .9)).toFixed(2)}deg)`;
    $$(".msg", phone).forEach((el, i) => { const q = E.spr(seg(t, TL.phone + .5 + i * .06, TL.phone + 1 + i * .06)); el.style.opacity = Math.min(1, q * 1.4).toFixed(3); el.style.transform = `translateY(${lerp(16, 0, q).toFixed(1)}px)`; });
  } else phone.hidden = true;

  // курсор
  const cur = $("#cursor", panel), rip = $("#ripple", panel), pos = cursorAt(t);
  $$(".hov", panel).forEach(e => e.classList.remove("hov"));
  if (pos) {
    cur.style.display = ""; cur.style.transform = `translate(${px(pos.x - 4)}, ${px(pos.y - 3)})`;
    const tc = CLICKS.find(x => t >= x && t < x + .5);
    if (tc != null) {
      const q = seg(t, tc, tc + .22);
      cur.style.transform += ` scale(${(1 - .16 * Math.sin(Math.PI * q)).toFixed(3)})`;
      const r = E.out(seg(t, tc, tc + .5));
      rip.style.opacity = (.9 * (1 - r)).toFixed(3); rip.style.transform = `translate(${px(pos.x)}, ${px(pos.y)}) scale(${lerp(.25, 1.7, r).toFixed(3)})`;
    } else rip.style.opacity = 0;
    if (pos.target && pos.arrived) { const el = $(pos.target, panel); if (el) (el.closest(".dialog, .rail-item, .rail-tool, .kb-btn, .icon-btn") || el).classList.add("hov"); }
  } else cur.style.display = "none";

  renderCaps(t);
  renderOutro(t);
}
window.renderAt = renderAt;
window.DEMO = { TL, DUR, FPS, CHAR_T, TERM_T, CLICKS };
document.fonts.ready.then(() => { renderAt(0); window.DEMO_READY = true; });
