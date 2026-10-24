import asyncio
import logging
import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, Message

from bots.ads import db
from bots.ads import channel_info, services
from bots.ads.channel_info import ChannelError, fetch_and_save, refresh_all
from bots.ads.config import config
from bots.ads.orders import notify_admins
from bots.ads import slots
from bots.ads.screen import nav, remove_input, show
from bots.ads.prices import PRICE_HINT, Price, ch_price, fmt_price, fmt_rub, has_price, parse_price, price_setting
from bots.ads.ui import (ADMIN_PAGE_SIZE, TEST_MODE_TEXT, AdmCb, MenuCb, admin_icon, channel_card, channel_deeplink, fmt_num,
                    fmt_usd, home_btn, kb, order_summary, page_row, paginate)

log = logging.getLogger(__name__)
router = Router(name="admin")
router.message.filter(F.from_user.id.in_(config.admin_ids))
router.callback_query.filter(F.from_user.id.in_(config.admin_ids))

# отдельный роутер для событий добавления/удаления бота из каналов
events = Router(name="admin_events")


class Adm(StatesGroup):
    add_channel = State()
    price = State()
    price_all = State()
    price_default = State()
    views = State()
    reject_reason = State()


BACK = ("⬅️ В админ-панель", AdmCb(action="panel"))
HOME = home_btn("ru")


async def safe_edit(call: CallbackQuery, text: str, reply_markup=None) -> None:
    await nav(call, text, reply_markup)


# ---------- главная ----------
async def panel_view(user_id: int):
    channels = await db.list_channels()
    n_mod = await db.count_status(db.MODERATION)
    n_wait = await db.count_status(db.APPROVED)
    test = await db.is_test_user(user_id)
    n_support = await db.support_unread_total()
    no_admin = sum(1 for c in channels if not c["bot_admin"])
    emoji = await db.premium_emoji()
    text = (
        "⚙️ <b>Админ-панель</b>\n"
        f"Режим: {'🧪 <b>тестовый</b>' if test else '🟢 рабочий'}\n\n"
        f"📢 Каналов: <b>{len(channels)}</b>"
        + (f" (⚠️ бот не админ: <b>{no_admin}</b>)" if no_admin else "") + "\n"
        f"🛡 На модерации: <b>{n_mod}</b>\n"
        f"💳 Ждут оплаты: <b>{n_wait}</b>\n"
        f"💬 Новых сообщений в обращениях: <b>{n_support}</b>\n"
        f"✨ Премиум-эмодзи: {'✅ доступны' if emoji else '❌ недоступны'}"
    )
    markup = kb([
        [(f"🛡 Модерация ({n_mod})", AdmCb(action="mod")), ("📅 Расписание", AdmCb(action="schedule"))],
        [(f"💬 Обращения{f' ({n_support} 🔴)' if n_support else ''}", AdmCb(action="support"))],
        [("📢 Каналы", AdmCb(action="channels")), ("➕ Добавить каналы", AdmCb(action="add"))],
        [("💰 Цена для всех каналов", AdmCb(action="priceall")), ("🔗 Ссылки на каналы", AdmCb(action="links"))],
        [("🆕 Цена для новых каналов", AdmCb(action="pricedef")), ("✨ Премиум-эмодзи", AdmCb(action="emoji"))],
        [("🔄 Обновить статистику", AdmCb(action="refreshall")), ("📊 Продажи", AdmCb(action="stats"))],
        [("🧪 Выключить тестовый режим" if test else "🧪 Включить тестовый режим", AdmCb(action="testmode")),
         ("🧹 Удалить тест-заказы", AdmCb(action="cleartest"))],
        [HOME],
    ])
    return text, markup


@router.message(Command("admin"), StateFilter("*"))
async def panel_msg(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await remove_input(message)
    text, markup = await panel_view(message.from_user.id)
    await show(bot, message.from_user.id, text, markup, fresh=True)


@router.callback_query(MenuCb.filter(F.action == "admin"), StateFilter("*"))
@router.callback_query(AdmCb.filter(F.action == "panel"), StateFilter("*"))
async def panel_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await panel_view(call.from_user.id)
    await safe_edit(call, text, reply_markup=markup)
    await call.answer()


@router.callback_query(AdmCb.filter(F.action == "testmode"))
async def testmode_cb(call: CallbackQuery):
    enable = not await db.is_test_user(call.from_user.id)
    await db.set_test_user(call.from_user.id, enable)
    text, markup = await panel_view(call.from_user.id)
    note = TEST_MODE_TEXT if enable else "✅ Тестовый режим выключен."
    await safe_edit(call, note + "\n\n———\n\n" + text, markup)
    await call.answer()


EMOJI_TEXT = (
    "✨ <b>Премиум-эмодзи в постах</b>\n\n"
    "Telegram показывает премиум-эмодзи в каналах, только если у бота есть дополнительный юзернейм, "
    'купленный на <a href="https://fragment.com">Fragment</a> (за TON) и привязанный к боту. Без него '
    "премиум-эмодзи в опубликованных постах заменяются обычными.\n\n"
    "Пока галочка выключена, покупатели видят, что премиум-эмодзи недоступны. Купили и привязали юзернейм — "
    "включите: покупатели увидят, что премиум-эмодзи доступны, и посты (уже оплаченные тоже) будут "
    "публиковаться с ними.\n\n"
    "Сейчас: {state}"
)


async def emoji_view():
    on = await db.premium_emoji()
    text = EMOJI_TEXT.format(state="✅ <b>доступны</b> — у бота есть юзернейм с Fragment" if on
                             else "❌ <b>недоступны</b>")
    toggle = ("❌ Выключить" if on else "✅ У бота есть юзернейм — включить", AdmCb(action="emojiset", id=0 if on else 1))
    return text, kb([[toggle], [BACK]])


@router.callback_query(AdmCb.filter(F.action == "emoji"))
async def emoji_cb(call: CallbackQuery):
    await safe_edit(call, *await emoji_view())
    await call.answer()


@router.callback_query(AdmCb.filter(F.action == "emojiset"))
async def emoji_set_cb(call: CallbackQuery, callback_data: AdmCb):
    await db.set_setting("premium_emoji", "1" if callback_data.id else "0")
    await safe_edit(call, *await emoji_view())
    await call.answer("Премиум-эмодзи включены" if callback_data.id else "Премиум-эмодзи выключены")


@router.callback_query(AdmCb.filter(F.action == "cleartest"))
async def cleartest_cb(call: CallbackQuery):
    n = await db.delete_test_orders()
    await call.answer(f"Удалено тестовых заказов: {n}", show_alert=True)
    text, markup = await panel_view(call.from_user.id)
    await safe_edit(call, text, reply_markup=markup)


@router.callback_query(AdmCb.filter(F.action == "schedule"))
async def schedule_cb(call: CallbackQuery):
    """Ближайшие забронированные публикации (в тестовом режиме — тестовые)."""
    is_test = await db.is_test_user(call.from_user.id)
    rows = await db.upcoming_bookings(db.now() - 3600, is_test)
    icons = {db.MODERATION: "🕓", db.APPROVED: "💳", db.PAID: "⏳", db.SCHEDULED: "⏰"}
    channels = {c["id"]: c["title"] for c in await db.list_channels()}
    lines, last_day = [], None
    for o in rows:
        dt = slots.ts_dt(o["publish_at"])
        if dt.date() != last_day:
            last_day = dt.date()
            lines.append(f"\n<b>{slots.fmt_day(last_day)}</b>")
        names = ", ".join(channels.get(i, "?") for i in db.order_channel_ids(o))
        lines.append(f"{icons.get(o['status'], '')} {dt:%H:%M} · #{o['id']} · {escape(names)}")
    text = (f"📅 <b>Расписание публикаций</b>{' 🧪 (тестовые)' if is_test else ''} ({slots.tz_label()})\n"
            "⏰ оплачено — время занято\n🕓 модерация · 💳 ждёт оплаты — время ещё свободно\n"
            + ("\n".join(lines) or "\nПока ничего не запланировано."))
    await safe_edit(call, text, kb([[("🔄 Обновить", AdmCb(action="schedule")), BACK]]))
    await call.answer()


@router.callback_query(AdmCb.filter(F.action == "stats"))
async def stats_cb(call: CallbackQuery):
    s = await db.stats()
    await safe_edit(call,
                    "📊 <b>Продажи</b>\n\n"
                    f"Оплаченных заказов: <b>{s['paid']}</b>\n"
                    f"Получено звёздами: <b>{s['stars']} ⭐</b>\n"
                    f"Получено через CryptoBot: <b>{fmt_usd(s['usd'])}</b>\n"
                    f"Получено через xRocket: <b>{fmt_usd(s['xrocket'])}</b>\n"
                    f"Получено через FreeKassa: <b>{fmt_rub(s['freekassa'])}</b>\n"
                    f"Уникальных клиентов: <b>{s['users']}</b>",
                    reply_markup=kb([[BACK]]))
    await call.answer()


# ---------- каналы ----------
@router.callback_query(AdmCb.filter(F.action == "channels"), StateFilter("*"))
async def channels_cb(call: CallbackQuery, callback_data: AdmCb | None = None, state: FSMContext | None = None):
    if state:
        await state.clear()
    page = callback_data.p if callback_data else 0
    channels = await db.list_channels()
    items, page, pages = paginate(channels, page, ADMIN_PAGE_SIZE)
    rows = [[(f"{admin_icon(c)} {c['title']} · {fmt_num(c['subscribers'])} · "
              f"{fmt_price(*ch_price(c))}", AdmCb(action="ch", id=c["id"], p=page))]
            for c in items]
    nav_row = page_row("ru", page, pages, lambda p: AdmCb(action="channels", p=p))
    if nav_row:
        rows.append(nav_row)
    rows.append([("➕ Добавить каналы", AdmCb(action="add")), ("🔗 Ссылки", AdmCb(action="links"))])
    rows.append([BACK])
    no_admin = sum(1 for c in channels if not c["bot_admin"])
    text = (f"📢 <b>Каналы</b> ({len(channels)})\n🟢 показывается · 🔴 скрыт · ⚠️ бот не администратор"
            + (f"\n\n⚠️ Бот не админ в <b>{no_admin}</b> кан. — они скрыты от пользователей. "
               "После добавления бота нажмите «🔄 Обновить статистику» или подождите автообновления."
               if no_admin else "")) if channels else "Каналов пока нет."
    await safe_edit(call, text, reply_markup=kb(rows))
    await call.answer()


@router.callback_query(AdmCb.filter(F.action == "links"), StateFilter("*"))
async def links_cb(call: CallbackQuery, callback_data: AdmCb, state: FSMContext):
    """Ссылки для размещения в каналах: t.me/<бот>?start=<токен> — ведут сразу на заказ в этом канале."""
    await state.clear()
    channels = await db.list_channels()
    items, page, pages = paginate(channels, callback_data.p, ADMIN_PAGE_SIZE)
    lines = [f"{admin_icon(c)} <b>{escape(c['title'])}</b>\n<code>{channel_deeplink(c)}</code>"
             for c in items]
    rows = []
    nav_row = page_row("ru", page, pages, lambda p: AdmCb(action="links", p=p))
    if nav_row:
        rows.append(nav_row)
    rows.append([("📢 Каналы", AdmCb(action="channels")), BACK])
    text = ("🔗 <b>Ссылки на каналы</b>\n"
            "Разместите ссылку в канале (в описании или посте) — по ней пользователь сразу попадёт "
            "на заказ рекламы в этом канале. Нажмите на ссылку, чтобы скопировать.\n\n"
            + ("\n\n".join(lines) or "Каналов пока нет."))
    await safe_edit(call, text, reply_markup=kb(rows))
    await call.answer()


@router.callback_query(AdmCb.filter(F.action == "newlink"))
async def newlink_cb(call: CallbackQuery, callback_data: AdmCb):
    """Перевыпустить ссылку канала (старая перестаёт работать)."""
    await db.regenerate_token(callback_data.id)
    await show_channel(call, callback_data.id, "✅ Новая ссылка создана, старая больше не работает.")
    await call.answer()


def channel_admin_kb(ch):
    i = ch["id"]
    return kb([
        [("💰 Цена", AdmCb(action="price", id=i)), ("👁 Просмотры", AdmCb(action="views", id=i))],
        [("🔄 Обновить данные", AdmCb(action="refresh", id=i)),
         ("🔴 Скрыть" if ch["active"] else "🟢 Показывать", AdmCb(action="toggle", id=i))],
        [("🔗 Новая ссылка", AdmCb(action="newlink", id=i)), ("🗑 Удалить", AdmCb(action="del", id=i))],
        [("⬅️ К каналам", AdmCb(action="channels")), HOME],
    ])


async def show_channel(call: CallbackQuery, channel_id: int, note: str = ""):
    ch = await db.get_channel(channel_id)
    if not ch:
        return await safe_edit(call, "Канал не найден.", reply_markup=kb([[BACK]]))
    await safe_edit(call, (note + "\n\n" if note else "") + channel_card(ch, admin=True),
                    reply_markup=channel_admin_kb(ch))


@router.callback_query(AdmCb.filter(F.action == "ch"), StateFilter("*"))
async def channel_cb(call: CallbackQuery, callback_data: AdmCb, state: FSMContext):
    await state.clear()
    await show_channel(call, callback_data.id)
    await call.answer()


@router.callback_query(AdmCb.filter(F.action == "refresh"))
async def channel_refresh(call: CallbackQuery, callback_data: AdmCb, bot: Bot):
    ch = await db.get_channel(callback_data.id)
    await call.answer("Обновляю…")
    try:
        await fetch_and_save(bot, ch["chat_id"])
        await show_channel(call, ch["id"], "✅ Данные обновлены")
    except ChannelError as e:
        await show_channel(call, ch["id"], f"❌ {escape(str(e))}")


@router.callback_query(AdmCb.filter(F.action == "toggle"))
async def channel_toggle(call: CallbackQuery, callback_data: AdmCb):
    ch = await db.get_channel(callback_data.id)
    await db.update_channel(ch["id"], active=0 if ch["active"] else 1)
    await show_channel(call, ch["id"])
    await call.answer()


@router.callback_query(AdmCb.filter(F.action == "del"))
async def channel_del(call: CallbackQuery, callback_data: AdmCb):
    ch = await db.get_channel(callback_data.id)
    await safe_edit(call, f"Удалить канал <b>{escape(ch['title'])}</b> из каталога?",
                    reply_markup=kb([[("🗑 Да, удалить", AdmCb(action="delok", id=ch["id"])),
                                      ("Отмена", AdmCb(action="ch", id=ch["id"]))]]))
    await call.answer()


@router.callback_query(AdmCb.filter(F.action == "delok"))
async def channel_del_ok(call: CallbackQuery, callback_data: AdmCb):
    ch = await db.get_channel(callback_data.id)
    await db.delete_channel(callback_data.id)
    if ch:
        # удалённый вручную канал не должен вернуться автообнаружением
        await db.set_setting(f"ignored:{ch['chat_id']}", "1")
        channel_info.remember(ch["chat_id"])
    await call.answer("Канал удалён")
    await channels_cb(call, None, None)


@router.callback_query(AdmCb.filter(F.action == "refreshall"))
async def refresh_all_cb(call: CallbackQuery, bot: Bot):
    await call.answer("Обновляю все каналы…")
    ok, errors = await refresh_all(bot)
    text = f"🔄 Обновлено каналов: <b>{ok}</b>"
    if errors:
        text += "\n\n❌ Ошибки:\n" + "\n".join(escape(e) for e in errors)
    await safe_edit(call, text, reply_markup=kb([[BACK]]))


# ---------- добавление каналов ----------
ADD_TEXT = ("➕ <b>Добавление каналов</b>\n\n"
            "1. Добавьте бота в каналы администратором с правом публикации сообщений.\n"
            "2. Пришлите каналы — по одному в строке, можно сразу с ценой "
            "(<b>звёзды</b>, <b>доллары</b>, <b>рубли</b>; <code>-</code> — валюта не принимается):\n"
            "<code>@channel | 100 5.0 450\n"
            "https://t.me/channel2 | - 12 1000\n"
            "-1001234567890</code>\n\n"
            "Без цены канал добавится скрытым от пользователей — цену можно задать потом.\n"
            "Бота можно добавить в каналы и позже: такие каналы будут помечены ⚠️ «бот не админ» "
            "(для приватных каналов указывайте числовой ID).\n"
            "Можно также просто переслать пост из канала.")
ADD_KB = kb([[("Отмена", AdmCb(action="panel"))]])


@router.callback_query(AdmCb.filter(F.action == "add"))
async def add_cb(call: CallbackQuery, state: FSMContext):
    await state.set_state(Adm.add_channel)
    await safe_edit(call, ADD_TEXT, ADD_KB)
    await call.answer()


def parse_ref(text: str) -> int | str | None:
    text = text.strip()
    if re.fullmatch(r"-?\d{5,}", text):
        return int(text)
    m = re.fullmatch(r"(?:https?://)?(?:t\.me|telegram\.me)/(?:s/)?([A-Za-z0-9_]{4,})/?", text)
    if m:
        return "@" + m.group(1)
    if re.fullmatch(r"@?[A-Za-z][A-Za-z0-9_]{3,}", text):
        return "@" + text.lstrip("@")
    return None


def parse_add_lines(text: str) -> list[tuple[str, int | str | None, Price | None]]:
    """Каждая строка: <канал> [| <звёзды> <доллары> [<рубли>]]. Возвращает (строка, ссылка-или-None, цена-или-None)."""
    result = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if "|" in line:
            ref_part, price_part = line.split("|", 1)
        else:
            # «@channel 100 5.0» без разделителя тоже понимаем
            parts = line.split()
            ref_part, price_part = parts[0], " ".join(parts[1:])
        price = parse_price(price_part) if price_part.strip() else None
        result.append((line, parse_ref(ref_part), price))
    return result


@router.message(Adm.add_channel)
async def add_channel_msg(message: Message, state: FSMContext, bot: Bot):
    await remove_input(message)
    uid = message.from_user.id
    origin = message.forward_origin
    if origin is not None and getattr(origin, "chat", None):
        if await add_channel(bot, uid, origin.chat.id):
            await state.clear()
        return
    lines = parse_add_lines(message.text or "")
    if not lines:
        return await show(bot, uid, "⚠️ Не понял, какие это каналы.\n\n" + ADD_TEXT, ADD_KB)
    if len(lines) == 1 and lines[0][1] is not None and lines[0][2] is None:
        if await add_channel(bot, uid, lines[0][1]):
            await state.clear()
        return
    await state.clear()
    await add_many(bot, uid, lines)


async def add_many(bot: Bot, uid: int, lines) -> None:
    """Добавляет каналы пачкой, обновляя прогресс на экране."""
    ok, errors = [], []
    total = len(lines)
    for i, (line, ref, price) in enumerate(lines, 1):
        if i == 1 or i % 5 == 0:
            await show(bot, uid, f"⏳ Добавляю каналы… {i}/{total}")
        if ref is None:
            errors.append(f"<code>{escape(line)}</code> — не похоже на канал")
            continue
        try:
            channel_id = await fetch_and_save(bot, ref)
        except ChannelError as e:
            errors.append(f"<code>{escape(line)}</code> — {escape(str(e))}")
            continue
        if price:
            await services.set_price(channel_id, price)
        ch = await db.get_channel(channel_id)
        await db.set_setting(f"ignored:{ch['chat_id']}", "")
        channel_info.remember(ch["chat_id"])
        notes = []
        if not ch["bot_admin"]:
            notes.append("⚠️ бот не админ")
        if not has_price(ch):
            notes.append("без цены")
        ok.append(f"<b>{escape(ch['title'])}</b>" + (f" ({', '.join(notes)})" if notes else ""))
    text = f"✅ Добавлено каналов: <b>{len(ok)}</b> из {total}"
    no_admin = sum(1 for x in ok if "бот не админ" in x)
    if no_admin:
        text += (f"\n⚠️ В {no_admin} кан. бот пока не администратор — они скрыты от пользователей, "
                 "пока вы не добавите бота админом.")
    if ok:
        text += "\n" + "\n".join(f"• {x}" for x in ok[:30]) + ("\n…" if len(ok) > 30 else "")
    if errors:
        text += f"\n\n❌ Не добавлено ({len(errors)}):\n" + "\n".join(f"• {x}" for x in errors[:30])
    await show(bot, uid, text, kb([[("📢 Каналы", AdmCb(action="channels")), ("🔗 Ссылки", AdmCb(action="links"))],
                                   [("➕ Добавить ещё", AdmCb(action="add")), BACK]]))


async def add_channel(bot: Bot, uid: int, ref: int | str) -> bool:
    await show(bot, uid, "⏳ Получаю данные канала…")
    try:
        channel_id = await fetch_and_save(bot, ref)
    except ChannelError as e:
        await show(bot, uid, f"❌ {escape(str(e))}\n\n" + ADD_TEXT, ADD_KB)
        return False
    ch = await db.get_channel(channel_id)
    await db.set_setting(f"ignored:{ch['chat_id']}", "")
    channel_info.remember(ch["chat_id"])
    if not has_price(ch):
        await services.set_price(channel_id, await db.default_price())
        ch = await db.get_channel(channel_id)
    note = "✅ Канал добавлен."
    if not ch["bot_admin"]:
        note += "\n⚠️ Бот пока не администратор — добавьте его в канал админом с правом публикации."
    if not ch["avg_views"]:
        note += "\n⚠️ Просмотры не удалось получить автоматически (канал приватный?) — укажите их вручную."
    await show(bot, uid, note + "\n\n" + channel_card(ch, admin=True), channel_admin_kb(ch))
    return True


@router.callback_query(AdmCb.filter(F.action == "addch"), StateFilter("*"))
async def add_from_event(call: CallbackQuery, callback_data: AdmCb, state: FSMContext, bot: Bot):
    await state.clear()
    await call.answer()
    await nav(call, "⏳ Получаю данные канала…")
    await add_channel(bot, call.from_user.id, callback_data.id)


# ---------- цены и просмотры ----------

@router.callback_query(AdmCb.filter(F.action == "price"))
async def price_cb(call: CallbackQuery, callback_data: AdmCb, state: FSMContext):
    ch = await db.get_channel(callback_data.id)
    await state.set_state(Adm.price)
    await state.update_data(channel_id=ch["id"])
    await safe_edit(call, f"💰 Цена для <b>{escape(ch['title'])}</b>\n"
                          f"Сейчас: {fmt_price(*ch_price(ch))}\n\n" + PRICE_HINT,
                    reply_markup=kb([[("Отмена", AdmCb(action="ch", id=ch["id"]))]]))
    await call.answer()


@router.message(Adm.price)
async def price_msg(message: Message, state: FSMContext, bot: Bot):
    await remove_input(message)
    channel_id = (await state.get_data())["channel_id"]
    price = parse_price(message.text)
    if not price:
        return await show(bot, message.from_user.id, "⚠️ Неверный формат. " + PRICE_HINT,
                          kb([[("Отмена", AdmCb(action="ch", id=channel_id))]]))
    await services.set_price(channel_id, price)
    await state.clear()
    ch = await db.get_channel(channel_id)
    await show(bot, message.from_user.id, "✅ Цена сохранена\n\n" + channel_card(ch, admin=True),
               channel_admin_kb(ch))


@router.callback_query(AdmCb.filter(F.action == "priceall"))
async def price_all_cb(call: CallbackQuery, state: FSMContext):
    await state.set_state(Adm.price_all)
    await safe_edit(call, "💰 <b>Цена сразу для всех каналов</b>\n\n" + PRICE_HINT,
                    reply_markup=kb([[("Отмена", AdmCb(action="panel"))]]))
    await call.answer()


@router.message(Adm.price_all)
async def price_all_msg(message: Message, state: FSMContext, bot: Bot):
    await remove_input(message)
    price = parse_price(message.text)
    if not price:
        return await show(bot, message.from_user.id, "⚠️ Неверный формат. " + PRICE_HINT,
                          kb([[("Отмена", AdmCb(action="panel"))]]))
    await db.set_price_all(*price)
    await state.clear()
    text, markup = await panel_view(message.from_user.id)
    await show(bot, message.from_user.id,
               f"✅ Для всех каналов установлена цена {fmt_price(*price)}\n\n" + text, markup)


@router.callback_query(AdmCb.filter(F.action == "pricedef"))
async def price_def_cb(call: CallbackQuery, state: FSMContext):
    price = await db.default_price()
    await state.set_state(Adm.price_default)
    await safe_edit(call, "🆕 <b>Цена для новых каналов</b>\n"
                          "Ставится автоматически каналам, которые бот находит сам "
                          "(когда его назначают админом или он видит пост в канале).\n"
                          f"Сейчас: {fmt_price(*price)}\n\n" + PRICE_HINT,
                    reply_markup=kb([[("Отмена", AdmCb(action="panel"))]]))
    await call.answer()


@router.message(Adm.price_default)
async def price_def_msg(message: Message, state: FSMContext, bot: Bot):
    await remove_input(message)
    price = parse_price(message.text)
    if not price:
        return await show(bot, message.from_user.id, "⚠️ Неверный формат. " + PRICE_HINT,
                          kb([[("Отмена", AdmCb(action="panel"))]]))
    await db.set_setting("default_price", price_setting(price))
    await state.clear()
    text, markup = await panel_view(message.from_user.id)
    await show(bot, message.from_user.id,
               f"✅ Новые каналы будут получать цену {fmt_price(*price)}\n\n" + text, markup)


@router.callback_query(AdmCb.filter(F.action == "views"))
async def views_cb(call: CallbackQuery, callback_data: AdmCb, state: FSMContext):
    ch = await db.get_channel(callback_data.id)
    await state.set_state(Adm.views)
    await state.update_data(channel_id=ch["id"])
    await safe_edit(call, f"👁 Просмотры для <b>{escape(ch['title'])}</b>\n\n"
                          "Пришлите среднее число просмотров на пост.\n"
                          "Отправьте <code>0</code>, чтобы снова считать автоматически (только для публичных каналов).",
                    reply_markup=kb([[("Отмена", AdmCb(action="ch", id=ch["id"]))]]))
    await call.answer()


@router.message(Adm.views)
async def views_msg(message: Message, state: FSMContext, bot: Bot):
    await remove_input(message)
    text = (message.text or "").replace(" ", "")
    channel_id = (await state.get_data())["channel_id"]
    if not text.isdigit():
        return await show(bot, message.from_user.id, "⚠️ Пришлите целое число просмотров.",
                          kb([[("Отмена", AdmCb(action="ch", id=channel_id))]]))
    views = int(text)
    if views:
        await db.update_channel(channel_id, avg_views=views, views_manual=1)
    else:
        await db.update_channel(channel_id, views_manual=0)
        ch = await db.get_channel(channel_id)
        try:
            await fetch_and_save(bot, ch["chat_id"])
        except ChannelError:
            pass
    await state.clear()
    ch = await db.get_channel(channel_id)
    await show(bot, message.from_user.id, "✅ Сохранено\n\n" + channel_card(ch, admin=True), channel_admin_kb(ch))


# ---------- модерация ----------
async def show_moderation(bot: Bot, chat_id: int, after_id: int = 0, note: str = ""):
    """Экран модерации: пост (временное сообщение) + карточка заказа с кнопками."""
    note = note + "\n\n" if note else ""
    queue = await db.moderation_queue()
    if not queue:
        return await show(bot, chat_id, note + "🛡 Очередь модерации пуста ✅", kb([[BACK]]))
    order = next((o for o in queue if o["id"] > after_id), queue[0])
    channels = await db.get_channels(db.order_channel_ids(order))
    rows = [[("✅ Одобрить", AdmCb(action="approve", id=order["id"])),
             ("❌ Отклонить", AdmCb(action="reject", id=order["id"]))]]
    if len(queue) > 1:
        rows.append([("⏭ Следующий", AdmCb(action="skip", id=order["id"]))])
    rows.append([BACK])
    await show(
        bot, chat_id,
        note + f"⬆️ Пост выше\n🛡 На модерации: <b>{len(queue)}</b>\n\n" + order_summary(order, channels, admin=True) +
        ("" if slots.slot_ok(order) else "\n\n⚠️ Время публикации уже прошло — после одобрения "
                                         "пользователь выберет новое.") +
        f"\n\n👤 Заказчик: {escape(order['user_name'] or '')} "
        f"(<a href=\"tg://user?id={order['user_id']}\">{order['user_id']}</a>)",
        kb(rows), post=order,
    )


@router.callback_query(AdmCb.filter(F.action == "mod"), StateFilter("*"))
async def mod_cb(call: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    msg_id, _ = await db.get_screen(call.from_user.id)
    if call.message.message_id != msg_id:   # нажато в уведомлении
        await remove_input(call.message)
    await call.answer()
    await show_moderation(bot, call.from_user.id)


@router.callback_query(AdmCb.filter(F.action == "skip"))
async def mod_skip(call: CallbackQuery, callback_data: AdmCb, bot: Bot):
    await call.answer()
    await show_moderation(bot, call.from_user.id, after_id=callback_data.id)


@router.callback_query(AdmCb.filter(F.action == "approve"))
async def mod_approve(call: CallbackQuery, callback_data: AdmCb, bot: Bot):
    try:
        await services.approve_order(bot, callback_data.id)
    except services.ServiceError as e:
        return await call.answer(str(e), show_alert=True)
    await call.answer("✅ Одобрено")
    await show_moderation(bot, call.from_user.id, after_id=callback_data.id,
                          note=f"✅ Заказ #{callback_data.id} одобрен, пользователю отправлен счёт.")


@router.callback_query(AdmCb.filter(F.action == "reject"))
async def mod_reject(call: CallbackQuery, callback_data: AdmCb, state: FSMContext, bot: Bot):
    order = await db.get_order(callback_data.id)
    if not order or order["status"] != db.MODERATION:
        return await call.answer("Заказ уже обработан или отменён", show_alert=True)
    await state.set_state(Adm.reject_reason)
    await state.update_data(order_id=order["id"])
    # пост оставляем на экране — меню редактируется под ним
    await show(bot, call.from_user.id,
               f"❌ Отклонение заказа #{order['id']}\n\nНапишите причину отказа — её увидит пользователь.",
               kb([[("Без причины", AdmCb(action="noreason", id=order["id"]))],
                   [("Отмена", AdmCb(action="mod"))]]),
               keep_extra=True)
    await call.answer()


async def do_reject(bot: Bot, admin_chat: int, order_id: int, reason: str | None):
    try:
        await services.reject_order(bot, order_id, reason)
    except services.ServiceError:
        return await show_moderation(bot, admin_chat, note="Заказ уже обработан или отменён.")
    await show_moderation(bot, admin_chat, after_id=order_id, note=f"❌ Заказ #{order_id} отклонён.")


@router.callback_query(AdmCb.filter(F.action == "noreason"), Adm.reject_reason)
async def mod_noreason(call: CallbackQuery, callback_data: AdmCb, state: FSMContext, bot: Bot):
    await state.clear()
    await call.answer()
    await do_reject(bot, call.from_user.id, callback_data.id, None)


@router.message(Adm.reject_reason)
async def mod_reason_msg(message: Message, state: FSMContext, bot: Bot):
    await remove_input(message)
    order_id = (await state.get_data())["order_id"]
    await state.clear()
    await do_reject(bot, message.chat.id, order_id, (message.text or message.caption or "").strip() or None)


# ---------- бот добавлен / удалён из канала ----------
@events.my_chat_member(F.chat.type == "channel")
async def bot_membership(update: ChatMemberUpdated, bot: Bot):
    member = update.new_chat_member
    chat = update.chat
    existing = await db.get_channel_by_chat(chat.id)
    can_post = member.status == ChatMemberStatus.ADMINISTRATOR and bool(getattr(member, "can_post_messages", False))
    if can_post:
        if existing:
            was_admin = existing["bot_admin"]
            try:
                await fetch_and_save(bot, chat.id)
            except ChannelError:
                await db.update_channel(existing["id"], bot_admin=1)
            if not was_admin:
                await notify_admins(bot, f"✅ Бот стал администратором канала <b>{escape(chat.title or '')}</b> — "
                                         "канал снова доступен пользователям (если задана цена).")
            return
        # новый канал — добавляем сразу с ценой по умолчанию, сводка придёт раз в минуту
        await channel_info.discover(bot, chat.id)
    elif existing and existing["bot_admin"]:
        await db.update_channel(existing["id"], bot_admin=0)
        await notify_admins(
            bot,
            f"⚠️ Бот больше не администратор канала <b>{escape(chat.title or '')}</b> (или нет права публикации). "
            "Канал скрыт из каталога до возврата прав.",
        )


@events.channel_post()
async def channel_post_seen(message: Message, bot: Bot):
    """Бот видит посты в каналах, где он админ, — так находим каналы, куда его добавили раньше."""
    await channel_info.discover(bot, message.chat.id)


async def discovery_report_loop(bot: Bot, interval: int = 60) -> None:
    """Раз в минуту — одна сводка о найденных каналах вместо уведомления на каждый."""
    while True:
        await asyncio.sleep(interval)
        found = channel_info.take_found()
        if not found:
            continue
        try:
            price = await db.default_price()
            shown = "\n".join(f"• {escape(x)}" for x in found[:40]) + (f"\n… и ещё {len(found) - 40}" if len(found) > 40 else "")
            await notify_admins(
                bot,
                f"🔎 Найдено и добавлено каналов: <b>{len(found)}</b> (цена {fmt_price(*price)})\n{shown}",
                [[InlineKeyboardButton(text="📢 Каналы", callback_data=AdmCb(action="channels").pack())]],
            )
        except Exception:
            log.exception("discovery report failed")
