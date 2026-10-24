import re
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bots.ads import db, i18n, slots
from bots.ads.config import config
from bots.ads.i18n import t
from bots.ads.orders import extract_markup, has_premium_emoji, notify_new_moderation, post_snapshot
from bots.ads.screen import CLOSE_CB, nav, remove_input, show
from bots.ads.prices import fmt_price, has_price, order_price, order_totals, short_price
from bots.ads.slots import fmt_day, fmt_ts
from bots.ads.ui import (TEST_MODE_TEXT, ChCb, LangCb, MenuCb, OrdCb, PostCb, SelCb, SlotCb, catalog_kb,
                    channel_card, channel_user_kb, home_btn, home_kb, kb, lang_kb, order_summary,
                    pay_kb, select_kb, status_title)

router = Router(name="user")


class Buy(StatesGroup):
    selecting = State()
    choosing_time = State()
    waiting_post = State()
    confirm = State()


class Lang(StatesGroup):
    choosing = State()      # первый запуск, язык не определён


# ---------- язык ----------
async def user_lang(user) -> str:
    """Язык пользователя: сохранённый, иначе по настройкам Telegram, иначе русский."""
    return await db.get_lang(user.id) or i18n.detect(user.language_code) or i18n.DEFAULT


def is_admin(user_id: int) -> bool:
    return user_id in config.admin_ids


async def in_test(user_id: int) -> bool:
    """Тестовый режим доступен только администраторам."""
    return is_admin(user_id) and await db.is_test_user(user_id)


# ---------- главное меню ----------
async def home_view(user, note: str = ""):
    lang = await user_lang(user)
    test = await in_test(user.id)
    text = ((note + "\n\n———\n\n" if note else "") +
            (t(lang, "test_mode_hdr") if test else "") +
            t(lang, "hello", name=f", {escape(user.first_name)}" if user.first_name else ""))
    return text, home_kb(lang, is_admin(user.id), test)


@router.message(CommandStart(), StateFilter("*"))
async def start(message: Message, command: CommandObject, state: FSMContext, bot: Bot):
    await state.clear()
    await remove_input(message)
    user = message.from_user
    token = (command.args or "").strip()
    await db.log_start(user.id)
    # убираем старую нижнюю клавиатуру, если осталась от прошлой версии бота
    tmp = await message.answer("…", reply_markup=ReplyKeyboardRemove())
    await remove_input(tmp)

    if not await db.get_lang(user.id):
        detected = i18n.detect(user.language_code)
        if detected:
            await db.set_lang(user.id, detected)
        else:
            # язык не определили — спрашиваем, а ссылку на канал запоминаем
            await state.set_state(Lang.choosing)
            await state.update_data(token=token)
            return await show(bot, user.id, t("ru", "choose_lang"), lang_kb(), fresh=True)

    if token and await open_deeplink(bot, user, token):
        return
    text, markup = await home_view(user)
    await show(bot, user.id, text, markup, fresh=True)


async def open_deeplink(bot: Bot, user, token: str) -> bool:
    """Ссылка из канала: сразу показываем карточку этого канала с кнопкой заказа."""
    ch = await db.get_channel_by_token(token)
    if not ch or not (ch["active"] and ch["bot_admin"] and has_price(ch)):
        return False
    lang = await user_lang(user)
    text = t(lang, "deeplink_hdr") + await card_text(ch, lang, user.id)
    await show(bot, user.id, text, channel_user_kb(lang, ch, deeplink=True), fresh=True)
    return True


@router.callback_query(LangCb.filter(), StateFilter("*"))
async def lang_chosen(call: CallbackQuery, callback_data: LangCb, state: FSMContext, bot: Bot):
    code = callback_data.code if callback_data.code in i18n.LANGS else i18n.DEFAULT
    await db.set_lang(call.from_user.id, code)
    data = await state.get_data()
    pending = data.get("token") if await state.get_state() == Lang.choosing.state else None
    await state.clear()
    await call.answer(t(code, "lang_set"))
    if pending and await open_deeplink(bot, call.from_user, pending):
        return
    text, markup = await home_view(call.from_user, t(code, "lang_set"))
    await nav(call, text, markup)


@router.callback_query(MenuCb.filter(F.action == "lang"), StateFilter("*"))
async def lang_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await nav(call, t(await user_lang(call.from_user), "choose_lang"), lang_kb())
    await call.answer()


@router.message(Command("lang", "language"), StateFilter("*"))
async def lang_cmd(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await remove_input(message)
    await show(bot, message.from_user.id, t(await user_lang(message.from_user), "choose_lang"), lang_kb())


@router.callback_query(MenuCb.filter(F.action == "home"), StateFilter("*"))
async def home_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await home_view(call.from_user)
    await nav(call, text, markup)
    await call.answer()


@router.callback_query(F.data == CLOSE_CB, StateFilter("*"))
async def close_cb(call: CallbackQuery):
    await remove_input(call.message)
    await call.answer()


@router.callback_query(F.data == "noop", StateFilter("*"))
async def noop_cb(call: CallbackQuery):
    await call.answer()


@router.callback_query(MenuCb.filter(F.action == "help"), StateFilter("*"))
async def help_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    lang = await user_lang(call.from_user)
    await nav(call, t(lang, "help"), kb([[home_btn(lang)]]))
    await call.answer()


# ---------- тестовый режим (только админ) ----------
async def toggle_test_mode(bot: Bot, user) -> None:
    enable = not await db.is_test_user(user.id)
    await db.set_test_user(user.id, enable)
    note = TEST_MODE_TEXT if enable else "✅ Тестовый режим выключен. Новые заказы снова будут настоящими."
    text, markup = await home_view(user, note)
    await show(bot, user.id, text, markup)


@router.callback_query(MenuCb.filter(F.action == "test"), F.from_user.id.in_(config.admin_ids), StateFilter("*"))
async def test_cb(call: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    msg_id, _ = await db.get_screen(call.from_user.id)
    if call.message.message_id != msg_id:
        await remove_input(call.message)
    await toggle_test_mode(bot, call.from_user)
    await call.answer()


@router.message(Command("test"), F.from_user.id.in_(config.admin_ids), StateFilter("*"))
async def test_cmd(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await remove_input(message)
    await toggle_test_mode(bot, message.from_user)


# ---------- каталог ----------
async def available_channels(user_id: int):
    """Каналы для заказа. В тестовом режиме (только админ) видны и скрытые."""
    return await db.list_channels(only_active=True, include_hidden=await in_test(user_id))


async def catalog_view(user, page: int = 0):
    lang = await user_lang(user)
    channels = await available_channels(user.id)
    if not channels:
        return t(lang, "no_channels"), kb([[home_btn(lang)]])
    total = sum(c["subscribers"] for c in channels)
    text = t(lang, "catalog_title", n=len(channels), reach=f"{total:,}".replace(",", " "))
    return text, catalog_kb(lang, channels, page)


@router.callback_query(MenuCb.filter(F.action == "channels"), StateFilter("*"))
async def catalog_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await catalog_view(call.from_user)
    await nav(call, text, markup)
    await call.answer()


@router.callback_query(ChCb.filter(F.action == "list"), StateFilter("*"))
async def catalog_cb(call: CallbackQuery, callback_data: ChCb, state: FSMContext):
    await state.clear()
    text, markup = await catalog_view(call.from_user, callback_data.id)
    await nav(call, text, markup)
    await call.answer()


async def card_text(ch, lang: str, user_id: int) -> str:
    nearest = await slots.nearest_free([ch["id"]], await in_test(user_id))
    return channel_card(ch, lang) + "\n" + t(lang, "nearest", t=fmt_ts(nearest, lang) if nearest else t(lang, "none"))


async def visible_channel(call: CallbackQuery, channel_id: int):
    ch = await db.get_channel(channel_id)
    ok = (ch and ch["bot_admin"] and has_price(ch)
          and (ch["active"] or await in_test(call.from_user.id)))
    if not ok:
        await call.answer(t(await user_lang(call.from_user), "ch_unavailable"), show_alert=True)
        return None
    return ch


@router.callback_query(ChCb.filter(F.action == "view"), StateFilter("*"))
async def channel_view(call: CallbackQuery, callback_data: ChCb, state: FSMContext):
    await state.clear()
    ch = await visible_channel(call, callback_data.id)
    if not ch:
        return
    lang = await user_lang(call.from_user)
    await nav(call, await card_text(ch, lang, call.from_user.id), channel_user_kb(lang, ch))
    await call.answer()


@router.callback_query(ChCb.filter(F.action == "busy"), StateFilter("*"))
async def channel_busy(call: CallbackQuery, callback_data: ChCb):
    ch = await visible_channel(call, callback_data.id)
    if not ch:
        return
    lang = await user_lang(call.from_user)
    busy = await slots.load_busy(await in_test(call.from_user.id))
    lines = []
    for day in slots.booking_days()[:7]:
        day_slots = slots.day_slots(day)
        if not day_slots:
            continue
        taken = [slots.ts_dt(ts).strftime("%H:%M") for ts in day_slots if ch["id"] in busy.get(ts, set())]
        line = t(lang, "busy_line", day=fmt_day(day, lang), free=len(day_slots) - len(taken), total=len(day_slots))
        if taken:
            line += t(lang, "busy_taken", t=", ".join(taken))
        lines.append(line)
    text = (t(lang, "busy_title", title=escape(ch["title"]), tz=slots.tz_label(lang),
              a=config.work_start, b=config.work_end) + ("\n".join(lines) or t(lang, "no_dates")))
    await nav(call, text, kb([[(t(lang, "btn_order"), ChCb(action="order", id=ch["id"]))],
                              [(t(lang, "btn_to_channel"), ChCb(action="view", id=ch["id"])), home_btn(lang)]]))
    await call.answer()


@router.callback_query(ChCb.filter(F.action == "order"), StateFilter("*"))
async def channel_order(call: CallbackQuery, callback_data: ChCb, state: FSMContext):
    await start_selection(call, state, preselected=[callback_data.id])
    await call.answer()


# ---------- выбор каналов ----------
def total_text(lang, channels) -> str:
    """Итого по всем валютам, в которых можно оплатить все выбранные каналы."""
    totals = order_totals(channels)
    if channels and not any(totals):
        return "⚠️ " + t(lang, "no_common_short")
    return fmt_price(*totals)


def selection_text(lang, channels, selected: set[int]) -> str:
    chosen = [c for c in channels if c["id"] in selected]
    reach = sum(c["subscribers"] for c in chosen)
    return t(lang, "sel_title", k=len(chosen), n=len(channels),
             reach=f"{reach:,}".replace(",", " "), total=total_text(lang, chosen))


async def start_selection(call: CallbackQuery, state: FSMContext, preselected: list[int]):
    await state.clear()
    lang = await user_lang(call.from_user)
    channels = await available_channels(call.from_user.id)
    if not channels:
        return await nav(call, t(lang, "no_channels"), kb([[home_btn(lang)]]))
    selected = {i for i in preselected if any(c["id"] == i for c in channels)}
    await state.set_state(Buy.selecting)
    await state.update_data(selected=list(selected), page=0)
    await nav(call, selection_text(lang, channels, selected), select_kb(lang, channels, selected, 0))


@router.callback_query(MenuCb.filter(F.action == "buy"), StateFilter("*"))
@router.callback_query(SelCb.filter(F.action == "start"), StateFilter("*"))
async def sel_start(call: CallbackQuery, state: FSMContext):
    await start_selection(call, state, preselected=[])
    await call.answer()


@router.callback_query(SelCb.filter(F.action.in_({"toggle", "all", "none", "page"})), Buy.selecting)
async def sel_change(call: CallbackQuery, callback_data: SelCb, state: FSMContext):
    lang = await user_lang(call.from_user)
    channels = await available_channels(call.from_user.id)
    data = await state.get_data()
    selected = set(data.get("selected", []))
    if callback_data.action == "toggle":
        selected ^= {callback_data.id}
    elif callback_data.action == "all":
        selected = {c["id"] for c in channels}
    elif callback_data.action == "none":
        selected = set()
    selected &= {c["id"] for c in channels}
    await state.update_data(selected=list(selected), page=callback_data.p)
    await nav(call, selection_text(lang, channels, selected), select_kb(lang, channels, selected, callback_data.p))
    await call.answer()


@router.callback_query(SelCb.filter(F.action == "cancel"), StateFilter("*"))
async def sel_cancel(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await delete_msg(bot, call.from_user.id, data.get("message_id"))
    await state.clear()
    lang = await user_lang(call.from_user)
    text, markup = await home_view(call.from_user, t(lang, "order_cancelled"))
    await nav(call, text, markup)
    await call.answer()


def cancel_kb(lang):
    return kb([[(t(lang, "cancel"), SelCb(action="cancel"))]])


@router.callback_query(SelCb.filter(F.action == "next"), Buy.selecting)
async def sel_next(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("selected"):
        return await call.answer(t(await user_lang(call.from_user), "pick_one"), show_alert=True)
    if not any(order_totals(await db.get_channels(data["selected"]))):
        return await call.answer(t(await user_lang(call.from_user), "no_common_cur"), show_alert=True)
    await state.update_data(mode="buy")
    await days_screen(call, state)
    await call.answer()


@router.callback_query(SelCb.filter(F.action == "back"), StateFilter(Buy.choosing_time, Buy.waiting_post, Buy.confirm))
async def sel_back(call: CallbackQuery, state: FSMContext):
    """Вернуться к выбору каналов, сохранив отмеченные."""
    lang = await user_lang(call.from_user)
    data = await state.get_data()
    channels = await available_channels(call.from_user.id)
    selected = set(data.get("selected", [])) & {c["id"] for c in channels}
    page = data.get("page", 0)
    await state.set_state(Buy.selecting)
    await state.update_data(selected=list(selected))
    await nav(call, selection_text(lang, channels, selected), select_kb(lang, channels, selected, page))
    await call.answer()


@router.callback_query(SelCb.filter(), StateFilter("*"))
async def sel_stale(call: CallbackQuery):
    await call.answer(t(await user_lang(call.from_user), "stale"), show_alert=True)


# ---------- выбор даты и времени ----------
async def time_context(state: FSMContext, uid: int):
    """Каналы, тестовый ли заказ и какой заказ исключить из занятости (при переносе)."""
    data = await state.get_data()
    if data.get("mode") == "resched":
        order = await db.get_order(data["order_id"])
        return data["selected"], bool(order["is_test"]), order["id"]
    return data.get("selected", []), await in_test(uid), None


def back_from_time(lang, data) -> tuple:
    if data.get("mode") == "resched":
        return (t(lang, "btn_to_order"), OrdCb(action="view", id=data["order_id"]))
    return (t(lang, "btn_to_channels"), SelCb(action="back"))


async def days_screen(call: CallbackQuery, state: FSMContext, note: str = ""):
    await state.set_state(Buy.choosing_time)
    lang = await user_lang(call.from_user)
    data = await state.get_data()
    channel_ids, is_test, exclude = await time_context(state, call.from_user.id)
    busy = await slots.load_busy(is_test, exclude)
    rows, row = [], []
    for day in slots.booking_days():
        day_slots = slots.day_slots(day)
        if not day_slots:
            continue
        free = sum(1 for ts in day_slots if not slots.busy_in(busy, ts, channel_ids))
        mark = "✅" if free == len(day_slots) else ("🟡" if free else "❌")
        row.append((f"{mark} {fmt_day(day, lang)} · {free}", SlotCb(action="day", v=slots.day_code(day))))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if is_test:
        rows.append([(t(lang, "btn_now_test"), SlotCb(action="now"))])
    if data.get("mode") == "resched":
        rows.append([back_from_time(lang, data)])
    else:
        rows.append([back_from_time(lang, data), (t(lang, "cancel"), SelCb(action="cancel"))])
    text = (note + "\n\n" if note else "") + t(lang, "days_title", tz=slots.tz_label(lang), n=len(channel_ids))
    await nav(call, text, kb(rows))


async def hours_screen(call: CallbackQuery, state: FSMContext, day_code: int, note: str = ""):
    lang = await user_lang(call.from_user)
    data = await state.get_data()
    channel_ids, is_test, exclude = await time_context(state, call.from_user.id)
    busy = await slots.load_busy(is_test, exclude)
    day = slots.code_day(day_code)
    rows, row = [], []
    for ts in slots.day_slots(day):
        taken = slots.busy_in(busy, ts, channel_ids)
        mark = "✅" if not taken else ("❌" if len(taken) == len(channel_ids) else "🟡")
        row.append((f"{mark} {slots.ts_dt(ts):%H:%M}", SlotCb(action="t", v=ts)))
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    has_slots = bool(rows)
    rows.append([(t(lang, "btn_to_dates"), SlotCb(action="days")), back_from_time(lang, data)])
    text = (note + "\n\n" if note else "") + t(lang, "hours_title", day=fmt_day(day, lang), tz=slots.tz_label(lang))
    if not has_slots:
        text += t(lang, "no_free_today")
    await nav(call, text, kb(rows))


async def conflict_screen(call: CallbackQuery, state: FSMContext, ts: int, busy_ids: set[int], note: str = ""):
    lang = await user_lang(call.from_user)
    data = await state.get_data()
    channel_ids, is_test, exclude = await time_context(state, call.from_user.id)
    busy = await slots.load_busy(is_test, exclude)
    taken = await db.get_channels(sorted(busy_ids))
    names = "\n".join(f"• {escape(c['title'])}" for c in taken)
    suggestions = slots.free_slots(busy, channel_ids, after=ts - 1, limit=4)
    rows = [[(f"✅ {fmt_ts(s_ts, lang)}", SlotCb(action="t", v=s_ts))] for s_ts in suggestions]
    left = len(channel_ids) - len(busy_ids)
    if left > 0 and data.get("mode") != "resched":
        rows.append([(t(lang, "btn_drop", n=left), SlotCb(action="drop", v=ts))])
    rows.append([(t(lang, "btn_to_time"), SlotCb(action="day", v=slots.day_code(slots.ts_dt(ts).date())))])
    text = ((note + "\n\n" if note else "") + t(lang, "conflict", t=fmt_ts(ts, lang), names=names)
            + t(lang, "conflict_suggest" if suggestions else "conflict_none"))
    await nav(call, text, kb(rows))


@router.callback_query(SlotCb.filter(F.action == "days"), Buy.choosing_time)
async def slot_days(call: CallbackQuery, state: FSMContext):
    await days_screen(call, state)
    await call.answer()


@router.callback_query(SlotCb.filter(F.action == "day"), Buy.choosing_time)
async def slot_day(call: CallbackQuery, callback_data: SlotCb, state: FSMContext):
    await hours_screen(call, state, callback_data.v)
    await call.answer()


@router.callback_query(SlotCb.filter(F.action == "t"), Buy.choosing_time)
async def slot_pick(call: CallbackQuery, callback_data: SlotCb, state: FSMContext, bot: Bot):
    ts = callback_data.v
    lang = await user_lang(call.from_user)
    if not slots.is_bookable(ts):
        await days_screen(call, state, t(lang, "slot_gone"))
        return await call.answer()
    channel_ids, is_test, exclude = await time_context(state, call.from_user.id)
    taken = slots.busy_in(await slots.load_busy(is_test, exclude), ts, channel_ids)
    if taken:
        await conflict_screen(call, state, ts, taken)
        return await call.answer()
    await apply_time(call, state, bot, ts)


@router.callback_query(SlotCb.filter(F.action == "drop"), Buy.choosing_time)
async def slot_drop(call: CallbackQuery, callback_data: SlotCb, state: FSMContext, bot: Bot):
    lang = await user_lang(call.from_user)
    data = await state.get_data()
    if data.get("mode") == "resched":
        return await call.answer(t(lang, "drop_resched"), show_alert=True)
    channel_ids, is_test, _ = await time_context(state, call.from_user.id)
    taken = slots.busy_in(await slots.load_busy(is_test), callback_data.v, channel_ids)
    left = [c for c in channel_ids if c not in taken]
    if not left:
        await days_screen(call, state, t(lang, "slot_all_taken"))
        return await call.answer()
    await state.update_data(selected=left)
    await apply_time(call, state, bot, callback_data.v)


@router.callback_query(SlotCb.filter(F.action == "now"), Buy.choosing_time)
async def slot_now(call: CallbackQuery, state: FSMContext, bot: Bot):
    _, is_test, _ = await time_context(state, call.from_user.id)
    if not is_test or not is_admin(call.from_user.id):
        return await call.answer(t(await user_lang(call.from_user), "test_only"), show_alert=True)
    await apply_time(call, state, bot, 0)


async def apply_time(call: CallbackQuery, state: FSMContext, bot: Bot, ts: int):
    """Время выбрано: в заказе — переносим, в оформлении — идём дальше."""
    lang = await user_lang(call.from_user)
    data = await state.get_data()
    if data.get("mode") == "resched":
        order = await db.get_order(data["order_id"])
        if not order or order["user_id"] != call.from_user.id or order["status"] not in db.RESCHEDULABLE:
            await state.clear()
            return await order_screen(call, data["order_id"], t(lang, "time_locked"))
        # оплаченный заказ без времени — после выбора сразу бронируем и ставим в очередь
        new_status = db.SCHEDULED if order["status"] == db.NEED_TIME else None
        try:
            await db.reschedule_order(order["id"], ts or None, new_status)
        except db.SlotBusy as e:
            await conflict_screen(call, state, ts, set(e.channel_ids), t(lang, "slot_just_taken"))
            return await call.answer()
        await state.clear()
        booked = (new_status or order["status"]) in db.HOLDING
        return await order_screen(call, order["id"],
                                  t(lang, "time_set", t=fmt_ts(ts, lang)) + (t(lang, "booked_suffix") if booked else ""))

    await state.update_data(publish_at=ts)
    if data.get("message_id"):   # пост уже прислан (меняли время) — сразу к подтверждению
        await state.set_state(Buy.confirm)
        text, markup = await confirm_view(state, call.from_user, lang)
        await nav(call, text, markup)
    else:
        await state.set_state(Buy.waiting_post)
        await nav(call, t(lang, "time_chosen", t=fmt_ts(ts, lang)) + await post_prompt(lang), cancel_kb(lang))
    await call.answer()


@router.callback_query(SlotCb.filter(), StateFilter("*"))
async def slot_stale(call: CallbackQuery):
    await call.answer(t(await user_lang(call.from_user), "stale"), show_alert=True)


# ---------- получение поста ----------
async def post_prompt(lang: str) -> str:
    return t(lang, "post_prompt") + t(lang, "emoji_on" if await db.premium_emoji() else "emoji_off")


LOOKS_LIKE_ID = re.compile(r"[\w\-]{3,64}")


async def delete_msg(bot: Bot, chat_id: int, msg_id: int | None) -> None:
    if msg_id:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass


@router.message(Buy.waiting_post)
async def got_post(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    lang = await user_lang(message.from_user)
    if message.media_group_id:
        await remove_input(message)
        return await show(bot, uid, t(lang, "album") + await post_prompt(lang), cancel_kb(lang))
    if (message.text and not message.via_bot and not message.forward_origin
            and LOOKS_LIKE_ID.fullmatch(message.text.strip())):
        await remove_input(message)
        return await show(bot, uid, t(lang, "id_only", id=escape(message.text.strip())), cancel_kb(lang))

    # предыдущий присланный вариант поста больше не нужен
    data = await state.get_data()
    await delete_msg(bot, uid, data.get("message_id"))

    await state.update_data(from_chat_id=message.chat.id, message_id=message.message_id,
                            reply_markup=extract_markup(message), post_json=post_snapshot(message),
                            premium=has_premium_emoji(message))
    await state.set_state(Buy.confirm)
    # сам пост остаётся в чате (он — источник для публикации), меню переезжает под него
    text, markup = await confirm_view(state, message.from_user, lang)
    await show(bot, uid, text, markup, fresh=True)


async def confirm_view(state: FSMContext, user, lang: str):
    data = await state.get_data()
    channels = await db.get_channels(data["selected"])
    names = "\n".join(f"• {escape(c['title'])}" for c in channels)
    text = (t(lang, "confirm", t=fmt_ts(data.get("publish_at"), lang), n=len(channels), names=names,
              total=total_text(lang, channels))
            + (t(lang, "confirm_emoji") if data.get("premium") and not await db.premium_emoji() else "")
            + (t(lang, "confirm_test") if await in_test(user.id) else "") + t(lang, "confirm_q"))
    markup = kb([
        [(t(lang, "btn_submit"), PostCb(action="submit"))],
        [(t(lang, "btn_change_time"), PostCb(action="time")), (t(lang, "btn_replace"), PostCb(action="replace"))],
        [(t(lang, "cancel"), SelCb(action="cancel"))],
    ])
    return text, markup


@router.callback_query(PostCb.filter(), Buy.confirm)
async def post_confirm(call: CallbackQuery, callback_data: PostCb, state: FSMContext, bot: Bot):
    uid = call.from_user.id
    lang = await user_lang(call.from_user)
    if callback_data.action == "replace":
        await state.set_state(Buy.waiting_post)
        await nav(call, await post_prompt(lang), cancel_kb(lang))
        return await call.answer()
    if callback_data.action == "time":
        await days_screen(call, state)
        return await call.answer()

    data = await state.get_data()
    publish_at = data.get("publish_at") or None
    if publish_at and not slots.is_bookable(publish_at):
        await days_screen(call, state, t(lang, "slot_unavailable"))
        return await call.answer()
    allowed = {c["id"] for c in await available_channels(uid)}
    channels = [c for c in await db.get_channels(data["selected"]) if c["id"] in allowed]
    if not channels:
        await state.clear()
        await nav(call, t(lang, "channels_gone"), kb([[home_btn(lang)]]))
        return await call.answer()
    totals = order_totals(channels)
    if not any(totals):
        return await call.answer(t(lang, "no_common_cur"), show_alert=True)
    user = call.from_user
    is_test = await in_test(uid)
    try:
        order_id = await db.create_order(
            user_id=uid,
            user_name=f"@{user.username}" if user.username else user.full_name,
            from_chat_id=data["from_chat_id"],
            message_id=data["message_id"],
            reply_markup=data.get("reply_markup"),
            channel_ids=[c["id"] for c in channels],
            total_stars=totals[0],
            total_usd=totals[1],
            total_rub=totals[2],
            is_test=is_test,
            publish_at=publish_at,
            post_json=data.get("post_json"),
        )
    except db.SlotBusy as e:
        # пока пользователь оформлял, это время оплатил кто-то другой
        await state.update_data(selected=[c["id"] for c in channels], mode="buy")
        await state.set_state(Buy.choosing_time)
        await conflict_screen(call, state, publish_at, set(e.channel_ids), t(lang, "slot_paid_meanwhile"))
        return await call.answer()
    await state.clear()
    await nav(call, t(lang, "submitted", id=order_id, test=t(lang, "test_suffix") if is_test else "",
                      t=fmt_ts(publish_at, lang)),
              kb([[(t(lang, "btn_orders"), OrdCb(action="list")), home_btn(lang)]]))
    await call.answer()
    await notify_new_moderation(bot, order_id, is_test=is_test)


@router.callback_query(PostCb.filter(), StateFilter("*"))
async def post_confirm_stale(call: CallbackQuery):
    await call.answer(t(await user_lang(call.from_user), "stale_post"), show_alert=True)


# ---------- мои заказы ----------
async def orders_view(user):
    lang = await user_lang(user)
    orders = await db.user_orders(user.id)
    if not orders:
        return t(lang, "no_orders"), kb([[home_btn(lang)]])
    rows = [[(f"{'🧪 ' if o['is_test'] else ''}#{o['id']} · {status_title(lang, o['status'])} · {short_price(*order_price(o))}",
              OrdCb(action="view", id=o["id"]))] for o in orders]
    rows.append([home_btn(lang)])
    return t(lang, "orders_title"), kb(rows)


@router.callback_query(MenuCb.filter(F.action == "orders"), StateFilter("*"))
@router.callback_query(OrdCb.filter(F.action == "list"), StateFilter("*"))
async def orders_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await orders_view(call.from_user)
    await nav(call, text, markup)
    await call.answer()


async def own_order(call: CallbackQuery, order_id: int):
    """Заказ, принадлежащий нажавшему пользователю, иначе None (с алертом)."""
    order = await db.get_order(order_id)
    if not order or order["user_id"] != call.from_user.id:
        await call.answer(t(await user_lang(call.from_user), "order_nf"), show_alert=True)
        return None
    return order


async def order_screen(call: CallbackQuery, order_id: int, note: str = ""):
    order = await own_order(call, order_id)
    if not order:
        return
    lang = await user_lang(call.from_user)
    channels = await db.get_channels(db.order_channel_ids(order))
    rows, extra = [], []
    time_ok = slots.slot_ok(order)
    taken = False
    if order["publish_at"] and order["status"] in (db.MODERATION, db.APPROVED):
        busy = await slots.load_busy(bool(order["is_test"]), exclude_order=order["id"])
        taken = bool(slots.busy_in(busy, order["publish_at"], db.order_channel_ids(order)))
    notes = [note] if note else []
    if order["status"] == db.APPROVED and time_ok and not taken:
        rows = pay_kb(lang, order).inline_keyboard
        notes.append(t(lang, "pay_note") if rows else t(lang, "no_pay_methods"))
    if order["status"] in db.RESCHEDULABLE:
        if order["status"] == db.NEED_TIME or not time_ok or taken:
            why = t(lang, "why_taken" if (taken or order["status"] == db.NEED_TIME) else "why_passed")
            notes.append(t(lang, "need_new_time", why=why))
            extra.append([(t(lang, "btn_new_time"), OrdCb(action="resched", id=order["id"]))])
        else:
            extra.append([(t(lang, "btn_resched"), OrdCb(action="resched", id=order["id"]))])
    if order["status"] == db.MODERATION:
        extra.append([(t(lang, "btn_cancel_order"), OrdCb(action="cancel", id=order["id"]))])
    extra.append([(t(lang, "btn_to_orders"), OrdCb(action="list")), home_btn(lang)])
    markup = kb(extra)
    markup.inline_keyboard[:0] = rows
    text = ("\n\n".join(notes) + "\n\n" if notes else "") + order_summary(order, channels, lang)
    await nav(call, text, markup)
    await call.answer()


@router.callback_query(OrdCb.filter(F.action == "view"), StateFilter("*"))
async def order_view(call: CallbackQuery, callback_data: OrdCb, state: FSMContext):
    await state.clear()
    await order_screen(call, callback_data.id)


@router.callback_query(OrdCb.filter(F.action == "resched"), StateFilter("*"))
async def order_resched(call: CallbackQuery, callback_data: OrdCb, state: FSMContext):
    order = await own_order(call, callback_data.id)
    if not order:
        return
    if order["status"] not in db.RESCHEDULABLE:
        return await call.answer(t(await user_lang(call.from_user), "cant_resched"), show_alert=True)
    await state.clear()
    await state.update_data(mode="resched", order_id=order["id"], selected=db.order_channel_ids(order))
    await days_screen(call, state)
    await call.answer()


@router.callback_query(OrdCb.filter(F.action == "cancel"), StateFilter("*"))
async def order_cancel(call: CallbackQuery, callback_data: OrdCb):
    order = await own_order(call, callback_data.id)
    if not order:
        return
    lang = await user_lang(call.from_user)
    if not await db.change_status(order["id"], db.MODERATION, db.CANCELLED):
        return await call.answer(t(lang, "cant_cancel"), show_alert=True)
    await order_screen(call, order["id"], t(lang, "order_cancelled"))


# ---------- всё остальное ----------
@router.message(F.chat.type == "private", ~F.successful_payment, StateFilter("*"))
async def fallback(message: Message, state: FSMContext, bot: Bot):
    """Случайные сообщения удаляем; вне сценария — показываем главное меню."""
    await remove_input(message)
    if await state.get_state() is None:
        text, markup = await home_view(message.from_user)
        await show(bot, message.from_user.id, text, markup)
