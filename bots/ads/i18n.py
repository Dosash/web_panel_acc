"""Переводы пользовательского интерфейса. Админ-панель — только на русском."""
from datetime import date, datetime

LANGS = ("ru", "en")
DEFAULT = "ru"
LANG_NAMES = {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}

S: dict[str, dict[str, str]] = {
    # ---- общие ----
    "menu": {"ru": "🏠 Меню", "en": "🏠 Menu"},
    "cancel": {"ru": "❌ Отмена", "en": "❌ Cancel"},
    "back": {"ru": "⬅️ Назад", "en": "⬅️ Back"},
    "prev": {"ru": "◀️", "en": "◀️"},
    "next_page": {"ru": "▶️", "en": "▶️"},
    "page": {"ru": "Стр. {p}/{n}", "en": "Page {p}/{n}"},
    "hide": {"ru": "✖️ Скрыть", "en": "✖️ Hide"},
    "choose_action": {"ru": "Выберите действие в меню 👇", "en": "Choose an action from the menu 👇"},
    "stale": {"ru": "Эта кнопка устарела. Откройте меню заново.", "en": "This button is outdated. Open the menu again."},

    # ---- язык ----
    "choose_lang": {"ru": "🌐 Выберите язык / Choose your language", "en": "🌐 Выберите язык / Choose your language"},
    "lang_set": {"ru": "✅ Язык: Русский", "en": "✅ Language: English"},
    "btn_lang": {"ru": "🌐 Язык", "en": "🌐 Language"},
    "btn_support": {"ru": "💬 Связаться с нами", "en": "💬 Contact us"},

    # ---- главное меню ----
    "test_mode_hdr": {"ru": "🧪 <b>Тестовый режим</b>\n\n", "en": "🧪 <b>Test mode</b>\n\n"},
    "hello": {
        "ru": "👋 Привет{name}!\n\nЗдесь можно купить рекламу в наших Telegram-каналах. "
              "Выберите каналы, пришлите пост — после модерации оплатите звёздами ⭐ или криптой 💎, "
              "и пост будет опубликован автоматически.",
        "en": "👋 Hi{name}!\n\nHere you can buy ads in our Telegram channels. "
              "Pick channels, send your post — after moderation pay with Stars ⭐ or crypto 💎, "
              "and the post will be published automatically.",
    },
    "btn_channels": {"ru": "📢 Каналы", "en": "📢 Channels"},
    "btn_buy": {"ru": "🛒 Купить рекламу", "en": "🛒 Buy ads"},
    "btn_orders": {"ru": "📋 Мои заказы", "en": "📋 My orders"},
    "btn_help": {"ru": "ℹ️ Как это работает", "en": "ℹ️ How it works"},
    "btn_admin": {"ru": "⚙️ Админ-панель", "en": "⚙️ Admin panel"},
    "btn_test_on": {"ru": "🧪 Тестовый режим", "en": "🧪 Test mode"},
    "btn_test_off": {"ru": "🧪 Выйти из теста", "en": "🧪 Exit test mode"},

    "help": {
        "ru": "<b>Как купить рекламу</b>\n\n"
              "1️⃣ Откройте «📢 Каналы», чтобы посмотреть статистику и цены.\n"
              "2️⃣ Нажмите «🛒 Купить рекламу» и отметьте нужные каналы (или сразу все).\n"
              "📅 Выберите дату и время публикации: ✅ — свободно во всех выбранных каналах, "
              "🟡 — занято в части каналов, ❌ — занято везде. Время закрепляется за вами в момент оплаты; "
              "если его успеют занять раньше, бот предложит другое.\n"
              "3️⃣ Создайте рекламный пост в @justpost — с кнопками или без.\n"
              "4️⃣ Отправьте пост сюда: в поле ввода наберите <code>@justpost ID_поста</code> "
              "и выберите пост из появившегося списка. Можно и просто переслать готовый пост.\n"
              "5️⃣ Пост уйдёт на модерацию. После одобрения вы получите счёт.\n"
              "6️⃣ Оплатите звёздами Telegram ⭐ или криптовалютой через @CryptoBot — "
              "пост будет опубликован в выбранное время.",
        "en": "<b>How to buy ads</b>\n\n"
              "1️⃣ Open “📢 Channels” to see stats and prices.\n"
              "2️⃣ Tap “🛒 Buy ads” and select the channels you need (or all at once).\n"
              "📅 Pick the date and time: ✅ — free in all selected channels, "
              "🟡 — taken in some, ❌ — taken everywhere. The slot is locked for you at the moment of payment; "
              "if someone takes it first, the bot will suggest another one.\n"
              "3️⃣ Create your ad post in @justpost — with or without buttons.\n"
              "4️⃣ Send the post here: type <code>@justpost POST_ID</code> in the input field "
              "and pick the post from the list. You can also just forward a ready post.\n"
              "5️⃣ The post goes to moderation. Once approved, you'll get an invoice.\n"
              "6️⃣ Pay with Telegram Stars ⭐ or crypto via @CryptoBot — "
              "the post will be published at the chosen time.",
    },
    "post_prompt": {
        "ru": "📝 <b>Пришлите рекламный пост</b>\n\n"
              "Создайте пост в @justpost, затем наберите в поле ввода этого чата:\n"
              "<code>@justpost ID_поста</code>\n"
              "и выберите пост из появившегося списка — он отправится сюда вместе с кнопками.\n\n"
              "Также можно переслать готовый пост или отправить его обычным сообщением.",
        "en": "📝 <b>Send your ad post</b>\n\n"
              "Create the post in @justpost, then type in this chat's input field:\n"
              "<code>@justpost POST_ID</code>\n"
              "and pick the post from the list — it will be sent here with its buttons.\n\n"
              "You can also forward a ready post or send it as a regular message.",
    },
    "emoji_off": {"ru": "\n\n⚠️ Премиум-эмодзи недоступны: в канале они будут показаны обычными эмодзи.",
                  "en": "\n\n⚠️ Premium emoji are not available: they will be shown as regular emoji in the channel."},
    "emoji_on": {"ru": "\n\n✨ Премиум-эмодзи доступны — пост опубликуется вместе с ними.",
                 "en": "\n\n✨ Premium emoji are available — the post will be published with them."},

    # ---- каталог ----
    "catalog_title": {
        "ru": "📢 <b>Наши каналы</b> ({n})\nСуммарный охват: <b>{reach}</b> подписчиков\n\n"
              "Нажмите на канал, чтобы посмотреть подробности.",
        "en": "📢 <b>Our channels</b> ({n})\nTotal reach: <b>{reach}</b> subscribers\n\n"
              "Tap a channel to see details.",
    },
    "no_channels": {"ru": "Пока нет доступных каналов.", "en": "No channels available yet."},
    "ch_unavailable": {"ru": "Канал недоступен", "en": "Channel unavailable"},
    "subscribers": {"ru": "👥 Подписчиков: <b>{n}</b>", "en": "👥 Subscribers: <b>{n}</b>"},
    "views": {"ru": "👁 Просмотров на пост: <b>~{n}</b>", "en": "👁 Views per post: <b>~{n}</b>"},
    "views_na": {"ru": "👁 Просмотры: <i>нет данных</i>", "en": "👁 Views: <i>no data</i>"},
    "price": {"ru": "💰 Цена размещения: <b>{p}</b>", "en": "💰 Price per post: <b>{p}</b>"},
    "nearest": {"ru": "🕒 Ближайшее свободное время: <b>{t}</b>", "en": "🕒 Nearest free slot: <b>{t}</b>"},
    "none": {"ru": "нет", "en": "none"},
    "btn_order_here": {"ru": "🛒 Заказать рекламу в канале", "en": "🛒 Order an ad in this channel"},
    "btn_busy": {"ru": "📅 Занятость по дням", "en": "📅 Availability by day"},
    "btn_open": {"ru": "↗️ Открыть канал", "en": "↗️ Open channel"},
    "btn_to_list": {"ru": "⬅️ К списку", "en": "⬅️ To the list"},
    "btn_to_channel": {"ru": "⬅️ К каналу", "en": "⬅️ To channel"},
    "btn_order": {"ru": "🛒 Заказать", "en": "🛒 Order"},
    "busy_title": {
        "ru": "📅 <b>Занятость: {title}</b> ({tz})\nПубликации с {a:02d}:00 до {b:02d}:00, один пост в час.\n\n",
        "en": "📅 <b>Availability: {title}</b> ({tz})\nPosts from {a:02d}:00 to {b:02d}:00, one post per hour.\n\n",
    },
    "busy_line": {"ru": "<b>{day}</b> — свободно {free} из {total}", "en": "<b>{day}</b> — {free} of {total} free"},
    "busy_taken": {"ru": "\n   ❌ занято: {t}", "en": "\n   ❌ taken: {t}"},
    "no_dates": {"ru": "Нет доступных дат.", "en": "No available dates."},
    "deeplink_hdr": {
        "ru": "🔗 Вы перешли по ссылке из канала. Здесь можно заказать в нём рекламу.\n\n",
        "en": "🔗 You came via a link from the channel. You can order an ad in it here.\n\n",
    },
    "btn_more_channels": {"ru": "➕ Выбрать ещё каналы", "en": "➕ Pick more channels"},

    # ---- выбор каналов ----
    "sel_title": {
        "ru": "🛒 <b>Выберите каналы для размещения</b>\n\nВыбрано: <b>{k}</b> из {n}\n"
              "Охват: <b>{reach}</b> подписчиков\nИтого: <b>{total}</b>",
        "en": "🛒 <b>Select channels for your ad</b>\n\nSelected: <b>{k}</b> of {n}\n"
              "Reach: <b>{reach}</b> subscribers\nTotal: <b>{total}</b>",
    },
    "btn_all": {"ru": "✅ Выбрать все каналы", "en": "✅ Select all channels"},
    "btn_none": {"ru": "☑️ Снять все", "en": "☑️ Deselect all"},
    "btn_next": {"ru": "Далее ➡️ ({k})", "en": "Next ➡️ ({k})"},
    "pick_one": {"ru": "Выберите хотя бы один канал", "en": "Select at least one channel"},
    "no_common_cur": {"ru": "⚠️ У выбранных каналов нет общей валюты оплаты — оформите их отдельными заказами.",
                      "en": "⚠️ The selected channels have no common payment currency — order them separately."},
    "no_common_short": {"ru": "нет общей валюты оплаты", "en": "no common payment currency"},
    "btn_to_channels": {"ru": "⬅️ К каналам", "en": "⬅️ To channels"},
    "order_cancelled": {"ru": "🚫 Заказ отменён.", "en": "🚫 Order cancelled."},
    "channels_gone": {"ru": "Выбранные каналы больше недоступны. Начните заново.",
                      "en": "The selected channels are no longer available. Please start over."},

    # ---- дата и время ----
    "days_title": {
        "ru": "📅 <b>Выберите дату публикации</b> ({tz})\nКаналов в заказе: {n}\n\n"
              "Число — сколько часов в этот день свободно во всех выбранных каналах.\n"
              "✅ всё свободно · 🟡 часть занята · ❌ всё занято",
        "en": "📅 <b>Pick the publication date</b> ({tz})\nChannels in order: {n}\n\n"
              "The number shows how many hours that day are free in all selected channels.\n"
              "✅ all free · 🟡 partly taken · ❌ all taken",
    },
    "btn_now_test": {"ru": "⚡ Сразу после оплаты (тест)", "en": "⚡ Right after payment (test)"},
    "btn_to_order": {"ru": "⬅️ К заказу", "en": "⬅️ To order"},
    "hours_title": {
        "ru": "🕒 <b>{day}</b> — выберите время ({tz})\n\n✅ свободно во всех выбранных каналах\n"
              "🟡 занято в части каналов\n❌ занято во всех",
        "en": "🕒 <b>{day}</b> — pick a time ({tz})\n\n✅ free in all selected channels\n"
              "🟡 taken in some channels\n❌ taken in all",
    },
    "no_free_today": {"ru": "\n\nНа этот день свободного времени уже нет.", "en": "\n\nNo free time left on this day."},
    "btn_to_dates": {"ru": "⬅️ К датам", "en": "⬅️ To dates"},
    "slot_gone": {"ru": "⚠️ Это время уже недоступно, выберите другое.", "en": "⚠️ This time is no longer available, pick another."},
    "slot_all_taken": {"ru": "⚠️ Это время уже занято во всех каналах.", "en": "⚠️ This time is already taken in all channels."},
    "conflict": {
        "ru": "⛔️ <b>{t}</b> уже занято в каналах:\n{names}\n\n",
        "en": "⛔️ <b>{t}</b> is already taken in:\n{names}\n\n",
    },
    "conflict_suggest": {"ru": "Ближайшее время, когда свободны <b>все</b> выбранные каналы:",
                         "en": "Nearest time when <b>all</b> selected channels are free:"},
    "conflict_none": {"ru": "Свободного времени для всех выбранных каналов в ближайшие дни нет — уберите часть каналов.",
                      "en": "No time is free for all selected channels in the coming days — remove some channels."},
    "btn_drop": {"ru": "✂️ Убрать занятые, оставить {n} кан. на это время", "en": "✂️ Drop taken, keep {n} ch. at this time"},
    "btn_to_time": {"ru": "⬅️ К выбору времени", "en": "⬅️ Back to time"},
    "drop_resched": {"ru": "При переносе нельзя менять каналы — выберите другое время.",
                     "en": "Channels can't be changed when rescheduling — pick another time."},
    "test_only": {"ru": "Доступно только в тестовом режиме", "en": "Available in test mode only"},
    "slot_just_taken": {"ru": "⚠️ Это время только что заняли.", "en": "⚠️ This time was just taken."},
    "time_set": {"ru": "✅ Время публикации: {t}", "en": "✅ Publication time: {t}"},
    "booked_suffix": {"ru": " — забронировано.", "en": " — booked."},
    "time_locked": {"ru": "⚠️ Время этого заказа уже нельзя изменить.", "en": "⚠️ This order's time can no longer be changed."},
    "time_chosen": {"ru": "🕒 Время публикации: <b>{t}</b>\n\n", "en": "🕒 Publication time: <b>{t}</b>\n\n"},

    # ---- пост ----
    "album": {"ru": "⚠️ Альбомы (несколько фото/видео) не поддерживаются. Пришлите пост с одним медиафайлом или текстом.\n\n",
              "en": "⚠️ Albums (several photos/videos) are not supported. Send a post with one media file or text.\n\n"},
    "id_only": {
        "ru": "⚠️ Похоже, вы прислали только ID поста.\n\nНаберите в поле ввода <code>@justpost {id}</code>, "
              "дождитесь появления поста и нажмите на него — он отправится в этот чат.\n\n"
              "Если это и есть текст рекламы — пришлите текст подлиннее.",
        "en": "⚠️ Looks like you sent only a post ID.\n\nType <code>@justpost {id}</code> in the input field, "
              "wait for the post to appear and tap it — it will be sent to this chat.\n\n"
              "If this is actually your ad text — please send a longer text.",
    },
    "confirm": {
        "ru": "⬆️ Ваш пост выше — так он будет выглядеть в канале.\n\n🕒 Публикация: <b>{t}</b>\n"
              "📢 Каналы ({n}):\n{names}\n\n💰 Итого: <b>{total}</b>\n\n",
        "en": "⬆️ Your post is above — this is how it will look in the channel.\n\n🕒 Publication: <b>{t}</b>\n"
              "📢 Channels ({n}):\n{names}\n\n💰 Total: <b>{total}</b>\n\n",
    },
    "confirm_emoji": {"ru": "⚠️ В посте есть премиум-эмодзи — в канале они будут показаны обычными эмодзи.\n\n",
                      "en": "⚠️ Your post has premium emoji — they will be shown as regular emoji in the channel.\n\n"},
    "confirm_test": {"ru": "🧪 Тестовый заказ: публикация будет только в тестовый канал.\n\n",
                     "en": "🧪 Test order: it will be published to the test channel only.\n\n"},
    "confirm_q": {"ru": "Отправить пост на модерацию? Время закрепится за вами после оплаты.",
                  "en": "Send the post to moderation? The time slot is locked for you after payment."},
    "btn_submit": {"ru": "📤 Отправить на модерацию", "en": "📤 Send to moderation"},
    "btn_change_time": {"ru": "🕒 Изменить время", "en": "🕒 Change time"},
    "btn_replace": {"ru": "✏️ Заменить пост", "en": "✏️ Replace post"},
    "slot_unavailable": {"ru": "⚠️ Выбранное время уже недоступно — выберите другое.",
                         "en": "⚠️ The chosen time is no longer available — pick another."},
    "slot_paid_meanwhile": {"ru": "⚠️ Пока вы оформляли заказ, это время успели оплатить.",
                            "en": "⚠️ While you were placing the order, this time was paid for by someone else."},
    "submitted": {
        "ru": "📤 Заказ #{id} отправлен на модерацию{test}.\n🕒 Время <b>{t}</b> закрепится за вами после оплаты.\n"
              "Мы пришлём уведомление, как только администратор проверит пост.",
        "en": "📤 Order #{id} sent to moderation{test}.\n🕒 The slot <b>{t}</b> is locked for you after payment.\n"
              "We'll notify you as soon as the admin reviews the post.",
    },
    "test_suffix": {"ru": " (🧪 тестовый)", "en": " (🧪 test)"},
    "stale_post": {"ru": "Эта кнопка устарела. Начните заказ заново.", "en": "This button is outdated. Start the order again."},

    # ---- заказы ----
    "orders_title": {"ru": "📋 <b>Ваши заказы</b>", "en": "📋 <b>Your orders</b>"},
    "no_orders": {"ru": "У вас пока нет заказов.", "en": "You have no orders yet."},
    "order_nf": {"ru": "Заказ не найден", "en": "Order not found"},
    "order_card": {
        "ru": "{test}🧾 <b>Заказ #{id}</b>\nСтатус: {status}\n🕒 Публикация: <b>{t}</b>\n\n"
              "Каналы ({n}):\n{names}\n\nСумма: <b>{total}</b>",
        "en": "{test}🧾 <b>Order #{id}</b>\nStatus: {status}\n🕒 Publication: <b>{t}</b>\n\n"
              "Channels ({n}):\n{names}\n\nAmount: <b>{total}</b>",
    },
    "test_label": {"ru": "🧪 <b>ТЕСТОВЫЙ</b> ", "en": "🧪 <b>TEST</b> "},
    "channels_deleted": {"ru": "• (каналы удалены)", "en": "• (channels deleted)"},
    "reject_reason": {"ru": "\n\nПричина отказа: {r}", "en": "\n\nRejection reason: {r}"},
    "st_moderation": {"ru": "🕓 На модерации", "en": "🕓 In moderation"},
    "st_approved": {"ru": "💳 Ожидает оплаты", "en": "💳 Awaiting payment"},
    "st_rejected": {"ru": "❌ Отклонён", "en": "❌ Rejected"},
    "st_paid": {"ru": "⏳ Оплачен, публикуется", "en": "⏳ Paid, publishing"},
    "st_scheduled": {"ru": "⏰ Оплачен, ждёт публикации", "en": "⏰ Paid, scheduled"},
    "st_need_time": {"ru": "⚠️ Оплачен — выберите время", "en": "⚠️ Paid — pick a time"},
    "st_published": {"ru": "✅ Опубликован", "en": "✅ Published"},
    "st_cancelled": {"ru": "🚫 Отменён", "en": "🚫 Cancelled"},
    "st_expired": {"ru": "⌛ Бронь истекла", "en": "⌛ Booking expired"},
    "pay_note": {"ru": "ℹ️ Время закрепится за вами после оплаты.", "en": "ℹ️ The slot is locked for you after payment."},
    "need_new_time": {"ru": "⚠️ Нужно выбрать новое время: {why}.", "en": "⚠️ You need to pick a new time: {why}."},
    "why_taken": {"ru": "это время успели оплатить другие", "en": "this time was paid for by someone else"},
    "why_passed": {"ru": "время публикации уже прошло", "en": "the publication time has passed"},
    "btn_new_time": {"ru": "🕒 Выбрать новое время", "en": "🕒 Pick a new time"},
    "btn_resched": {"ru": "🕒 Перенести время", "en": "🕒 Reschedule"},
    "btn_cancel_order": {"ru": "🚫 Отменить заказ", "en": "🚫 Cancel order"},
    "btn_to_orders": {"ru": "⬅️ К заказам", "en": "⬅️ To orders"},
    "cant_cancel": {"ru": "Заказ уже нельзя отменить", "en": "The order can no longer be cancelled"},
    "cant_resched": {"ru": "Время этого заказа уже нельзя изменить", "en": "This order's time can no longer be changed"},

    # ---- оплата ----
    "btn_pay_stars": {"ru": "⭐ Telegram Stars ({n} ⭐)", "en": "⭐ Telegram Stars ({n} ⭐)"},
    "btn_pay_fk": {"ru": "💳 СБП / карта ({rub})", "en": "💳 Card / SBP ({rub})"},
    "fk_text": {
        "ru": "💳 Оплата <b>{rub}</b> по заказу #{id}.\nОткроется страница FreeKassa — выберите СБП, "
              "банковскую карту или другой способ. Оплата подтвердится автоматически в течение минуты.",
        "en": "💳 Payment of <b>{rub}</b> for order #{id}.\nThe FreeKassa page will open — choose SBP, "
              "a bank card or another method. The payment is confirmed automatically within a minute.",
    },
    "fk_fail": {"ru": "Оплата в рублях сейчас недоступна, попробуйте другой способ",
                "en": "Payment in rubles is unavailable right now, try another method"},
    "no_pay_methods": {"ru": "⚠️ Сейчас этот заказ нечем оплатить — напишите администратору («💬 Связаться с нами»).",
                       "en": "⚠️ There's no way to pay for this order right now — contact the admin (“💬 Contact us”)."},
    "btn_pay_xrocket": {"ru": "🚀 xRocket ({usd})", "en": "🚀 xRocket ({usd})"},
    "xrocket_text": {
        "ru": "🚀 Счёт на <b>{usd}</b> (USDT) по заказу #{id}.\nОплатите в @xRocket — "
              "оплата подтвердится автоматически в течение минуты.",
        "en": "🚀 Invoice for <b>{usd}</b> (USDT), order #{id}.\nPay in @xRocket — "
              "the payment is confirmed automatically within a minute.",
    },
    "xrocket_fail": {"ru": "Не удалось создать счёт xRocket, попробуйте другой способ оплаты",
                     "en": "Couldn't create an xRocket invoice, try another payment method"},
    "btn_pay_crypto": {"ru": "💎 CryptoBot ({usd})", "en": "💎 CryptoBot ({usd})"},
    "btn_pay_test": {"ru": "🧪 Тестовая оплата (без денег)", "en": "🧪 Test payment (no money)"},
    "inv_title": {"ru": "Реклама — заказ #{id}", "en": "Ad — order #{id}"},
    "inv_desc": {"ru": "Размещение рекламного поста в каналах ({n} шт.)", "en": "Ad post placement in channels ({n})"},
    "inv_label": {"ru": "Размещение рекламы", "en": "Ad placement"},
    "pay_status": {"ru": "Заказ: {s}", "en": "Order: {s}"},
    "pay_time_passed": {"ru": "Время публикации уже прошло — выберите новое в карточке заказа.",
                        "en": "The publication time has passed — pick a new one in the order."},
    "pay_slot_taken": {"ru": "Это время уже заняли — выберите другое в карточке заказа.",
                       "en": "This time is already taken — pick another one in the order."},
    "pc_bad": {"ru": "Некорректный счёт", "en": "Invalid invoice"},
    "pc_unavailable": {"ru": "Заказ уже оплачен или недоступен", "en": "Order already paid or unavailable"},
    "pc_passed": {"ru": "Время публикации прошло — выберите новое в заказе", "en": "Publication time has passed — pick a new one"},
    "pc_taken": {"ru": "Это время уже заняли — выберите другое в заказе", "en": "This time is already taken — pick another"},
    "pc_amount": {"ru": "Сумма не совпадает с заказом", "en": "Amount doesn't match the order"},
    "crypto_no_test": {"ru": "🧪 Для тестового заказа CryptoBot не настроен (нет CRYPTOPAY_TESTNET_TOKEN). "
                             "Используйте «Тестовая оплата» или звёзды — они вернутся автоматически.",
                       "en": "🧪 CryptoBot isn't configured for test orders (no CRYPTOPAY_TESTNET_TOKEN). "
                             "Use “Test payment” or Stars — they'll be refunded automatically."},
    "crypto_fail": {"ru": "Не удалось создать счёт, попробуйте позже", "en": "Couldn't create an invoice, try again later"},
    "crypto_text": {
        "ru": "💎 Счёт на <b>{usd}</b> по заказу #{id}.\n{test}Оплатить можно любой криптовалютой в @CryptoBot. "
              "Оплата подтвердится автоматически в течение минуты.",
        "en": "💎 Invoice for <b>{usd}</b>, order #{id}.\n{test}Pay with any cryptocurrency in @CryptoBot. "
              "The payment is confirmed automatically within a minute.",
    },
    "crypto_testnet": {"ru": "🧪 Тестовая сеть: оплачивайте ненастоящими монетами в @CryptoTestnetBot.\n",
                       "en": "🧪 Testnet: pay with test coins in @CryptoTestnetBot.\n"},
    "btn_go_pay": {"ru": "💎 Перейти к оплате", "en": "💎 Go to payment"},
    "btn_check": {"ru": "🔄 Я оплатил — проверить", "en": "🔄 I've paid — check"},
    "already_paid": {"ru": "✅ Заказ уже оплачен", "en": "✅ Order already paid"},
    "check_fail": {"ru": "Не удалось проверить, попробуйте позже", "en": "Couldn't check, try again later"},
    "paid_ok": {"ru": "✅ Оплата получена!", "en": "✅ Payment received!"},
    "not_paid": {"ru": "Оплата пока не поступила", "en": "Payment not received yet"},
    "test_paid": {"ru": "🧪 Тестовая оплата принята.", "en": "🧪 Test payment accepted."},
    "unavailable": {"ru": "Недоступно", "en": "Unavailable"},

    # ---- уведомления ----
    "n_approved": {
        "ru": "✅ Ваш рекламный пост (заказ #{id}) прошёл модерацию!\n\n🕒 Публикация: <b>{t}</b>\n"
              "К оплате: <b>{total}</b>\n"
              "Время закрепится за вами после оплаты — пока оно свободно для других.",
        "en": "✅ Your ad post (order #{id}) passed moderation!\n\n🕒 Publication: <b>{t}</b>\n"
              "To pay: <b>{total}</b>\n"
              "The slot is locked for you after payment — until then it's open to others.",
    },
    "n_approved_passed": {
        "ru": "✅ Ваш рекламный пост (заказ #{id}) прошёл модерацию!\n\n⚠️ Выбранное время уже прошло — выберите новое и оплатите заказ.",
        "en": "✅ Your ad post (order #{id}) passed moderation!\n\n⚠️ The chosen time has passed — pick a new one and pay for the order.",
    },
    "btn_go_to_pay": {"ru": "💳 Перейти к оплате", "en": "💳 Go to payment"},
    "n_rejected": {"ru": "❌ Ваш рекламный пост (заказ #{id}) не прошёл модерацию.",
                   "en": "❌ Your ad post (order #{id}) didn't pass moderation."},
    "n_reason": {"ru": "\n\nПричина: {r}", "en": "\n\nReason: {r}"},
    "n_fix": {"ru": "\n\nВы можете исправить пост и оформить новый заказ.", "en": "\n\nYou can fix the post and place a new order."},
    "btn_new_order": {"ru": "🛒 Новый заказ", "en": "🛒 New order"},
    "n_need_time": {
        "ru": "✅ Оплата заказа #{id} получена, но время <b>{t}</b> только что заняли ({names}).\n"
              "Выберите новое время — повторная модерация не нужна.",
        "en": "✅ Payment for order #{id} received, but the slot <b>{t}</b> was just taken ({names}).\n"
              "Pick a new time — no re-moderation needed.",
    },
    "btn_pick_time": {"ru": "🕒 Выбрать время", "en": "🕒 Pick a time"},
    "n_scheduled": {"ru": "✅ Оплата заказа #{id} получена!\n⏰ Время забронировано, пост будет опубликован {t}.",
                    "en": "✅ Payment for order #{id} received!\n⏰ The slot is booked, the post will be published {t}."},
    "n_published": {"ru": "🎉 Заказ #{id} опубликован:\n", "en": "🎉 Order #{id} has been published:\n"},
    "n_partial": {"ru": "\n\n⚠️ В некоторые каналы опубликовать не удалось — администратор свяжется с вами.",
                  "en": "\n\n⚠️ Publishing to some channels failed — the admin will contact you."},
    "n_refund": {"ru": "🧪 Тестовый заказ #{id}: звёзды ({n} ⭐) возвращены на ваш баланс.",
                 "en": "🧪 Test order #{id}: {n} ⭐ refunded to your balance."},
    "n_refund_fail": {"ru": "⚠️ Не удалось вернуть звёзды за тестовый заказ #{id}: {e}",
                      "en": "⚠️ Couldn't refund Stars for test order #{id}: {e}"},
    "n_test_done": {
        "ru": "🧪 Тестовый заказ #{id} обработан (оплата: {m}).\n\n{result}\n\nВ рабочем режиме пост ушёл бы в каналы:\n{would}",
        "en": "🧪 Test order #{id} processed (payment: {m}).\n\n{result}\n\nIn production the post would go to:\n{would}",
    },

    # ---- поддержка ----
    "support_intro": {
        "ru": "💬 <b>Связь с администратором</b>\n\nНапишите ваш вопрос одним или несколькими сообщениями — "
              "можно прикрепить фото, видео или файл. Администратор ответит здесь же, в боте.",
        "en": "💬 <b>Contact the admin</b>\n\nWrite your question in one or more messages — "
              "you can attach a photo, video or file. The admin will reply right here in the bot.",
    },
    "support_history": {"ru": "\n\n<b>Последние сообщения:</b>\n{h}", "en": "\n\n<b>Recent messages:</b>\n{h}"},
    "support_you": {"ru": "Вы", "en": "You"},
    "support_admin": {"ru": "Администратор", "en": "Admin"},
    "support_attach": {"ru": "📎 вложение", "en": "📎 attachment"},
    "support_sent": {"ru": "✅ Сообщение отправлено администратору. Можете написать ещё или вернуться в меню.",
                     "en": "✅ Message sent to the admin. You can write more or go back to the menu."},
    "support_reply": {"ru": "💬 <b>Ответ администратора:</b>\n\n{text}", "en": "💬 <b>Reply from the admin:</b>\n\n{text}"},
    "btn_support_reply": {"ru": "✍️ Ответить", "en": "✍️ Reply"},
    "support_empty": {"ru": "⚠️ Пришлите текст или вложение.", "en": "⚠️ Send a text or an attachment."},

    # ---- время ----
    "immediately": {"ru": "сразу после оплаты", "en": "right after payment"},
    "ts": {"ru": "{d} ({wd}) в {hm} {tz}", "en": "{wd} {d} at {hm} {tz}"},
    "tz_msk": {"ru": "МСК", "en": "MSK"},
}

WEEKDAYS = {
    "ru": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}


def t(lang: str | None, key: str, **kw) -> str:
    lang = lang if lang in LANGS else DEFAULT
    s = S[key][lang]
    return s.format(**kw) if kw else s


def detect(language_code: str | None) -> str | None:
    """Язык по настройкам Telegram. None — не определили, спросим пользователя."""
    code = (language_code or "").lower()
    if code.startswith("ru"):
        return "ru"
    if code.startswith("en"):
        return "en"
    return None


def weekday(lang: str | None, d: date | datetime) -> str:
    return WEEKDAYS[lang if lang in LANGS else DEFAULT][d.weekday()]
