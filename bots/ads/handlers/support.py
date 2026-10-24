"""Обратная связь: пользователь пишет администратору, у админа — диалоги по каждому пользователю."""
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bots.ads import db, slots
from bots.ads.config import config
from bots.ads.i18n import t
from bots.ads.orders import media_file_id
from bots.ads.screen import add_extra, close_button, nav, notify, remove_input, show
from bots.ads.ui import AdmCb, MenuCb, home_btn, kb, page_row, paginate

user_router = Router(name="support_user")
admin_router = Router(name="support_admin")
admin_router.message.filter(F.from_user.id.in_(config.admin_ids))
admin_router.callback_query.filter(F.from_user.id.in_(config.admin_ids))

# сверх этого числа непрочитанных уведомления админу не шлём (защита от спама)
NOTIFY_LIMIT = 5
PAGE = 10


class Support(StatesGroup):
    writing = State()        # пользователь пишет администратору


class SupportAdmin(StatesGroup):
    reply = State()          # администратор пишет ответ


def media_kind(message: Message) -> str | None:
    for kind in ("photo", "video", "document", "animation", "voice", "audio", "video_note", "sticker"):
        if getattr(message, kind):
            return kind
    return None


def short(text: str | None, n: int = 300) -> str:
    text = text or ""
    return escape(text[:n]) + ("…" if len(text) > n else "")


def history_lines(msgs, lang: str, admin_view: bool) -> str:
    lines = []
    for m in msgs:
        when = slots.ts_dt(m["created_at"]).strftime("%d.%m %H:%M")
        if admin_view:
            who = "🛡 Вы" if m["from_admin"] else "👤 Пользователь"
        else:
            who = f"🛡 {t(lang, 'support_admin')}" if m["from_admin"] else f"👤 {t(lang, 'support_you')}"
        body = short(m["text"])
        if m["media"]:
            body = (t(lang, "support_attach") + (" " + body if body else ""))
        lines.append(f"<b>{who}</b> · {when}\n{body or '—'}")
    return "\n\n".join(lines)


# ================= пользователь =================
async def support_screen(bot: Bot, user, note: str = "", fresh: bool = False) -> None:
    from bots.ads.handlers.user import user_lang
    lang = await user_lang(user)
    msgs = await db.support_messages(user.id, limit=6)
    text = (note + "\n\n" if note else "") + t(lang, "support_intro")
    if msgs:
        text += t(lang, "support_history", h=history_lines(msgs, lang, admin_view=False))
    await show(bot, user.id, text, kb([[home_btn(lang)]]), fresh=fresh)


@user_router.callback_query(MenuCb.filter(F.action == "support"), StateFilter("*"))
async def support_open(call: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    await state.set_state(Support.writing)
    msg_id, _ = await db.get_screen(call.from_user.id)
    if call.message and call.message.message_id != msg_id:   # нажато в уведомлении
        await remove_input(call.message)
    await support_screen(bot, call.from_user)
    await call.answer()


@user_router.message(Support.writing)
async def support_incoming(message: Message, state: FSMContext, bot: Bot):
    from bots.ads.handlers.user import user_lang
    user = message.from_user
    lang = await user_lang(user)
    kind = media_kind(message)
    text = message.text or message.caption
    if not text and not kind:
        await remove_input(message)
        return await support_screen(bot, user, t(lang, "support_empty"))
    name = f"@{user.username}" if user.username else user.full_name

    # копия уходит администраторам сразу; вложение потом показываем из копии у первого админа
    src_chat, src_msg = None, None
    thread = await db.support_thread(user.id)
    unread = 0
    if thread:
        unread = next((th["unread"] for th in await db.support_threads() if th["user_id"] == user.id), 0)
    header = f"💬 <b>Сообщение от {escape(name)}</b> (<code>{user.id}</code>)"
    buttons = [[InlineKeyboardButton(text="✍️ Ответить", callback_data=AdmCb(action="sreply", id=user.id).pack()),
                InlineKeyboardButton(text="📂 Диалог", callback_data=AdmCb(action="sthread", id=user.id).pack())],
               [close_button()]]
    for admin_id in config.admin_ids:
        if unread >= NOTIFY_LIMIT:
            break
        try:
            if kind:
                caption = header + ("\n\n" + escape(text) if text else "")
                copy = await bot.copy_message(admin_id, user.id, message.message_id, caption=caption[:1024]
                                              if kind not in ("sticker", "video_note") else None,
                                              reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
                if src_msg is None:
                    src_chat, src_msg = admin_id, copy.message_id
            else:
                await notify(bot, admin_id, header + "\n\n" + escape(text), buttons[:1])
        except Exception:
            pass
    if kind and src_msg is None:
        # уведомление не ушло (лимит) — оставим источником сообщение пользователя
        src_chat, src_msg = user.id, message.message_id
    await db.support_add(user.id, name, False, text, kind, src_chat, src_msg, media_file_id(message)[1])
    if not (kind and src_chat == user.id):
        await remove_input(message)
    await support_screen(bot, user, t(lang, "support_sent"))


# ================= администратор =================
async def threads_view(page: int = 0, closed: bool = False):
    threads = await db.support_threads("closed" if closed else "open")
    items, page, pages = paginate(threads, page, PAGE)
    unread_total = await db.support_unread_total()
    rows = []
    for th in items:
        mark = f"🔴 {th['unread']}" if th["unread"] else "✅"
        title = th["user_name"] or str(th["user_id"])
        last = (th["last_text"] or "📎").replace("\n", " ")[:25]
        rows.append([(f"{mark} {title} · {last}", AdmCb(action="sthread", id=th["user_id"]))])
    nav_row = page_row("ru", page, pages, lambda p: AdmCb(action="closed" if closed else "support", p=p))
    if nav_row:
        rows.append(nav_row)
    rows.append([("📂 Открытые" if closed else "📁 Закрытые", AdmCb(action="support" if closed else "closed"))])
    rows.append([("⬅️ В админ-панель", AdmCb(action="panel"))])
    text = (f"💬 <b>Обращения — {'закрытые' if closed else 'открытые'}</b> ({len(threads)})\n"
            f"Непрочитанных сообщений: <b>{unread_total}</b>\n\n"
            + ("Нажмите на диалог, чтобы открыть переписку." if threads else "Обращений пока нет."))
    return text, kb(rows)


@admin_router.callback_query(AdmCb.filter(F.action.in_({"support", "closed"})), StateFilter("*"))
async def threads_cb(call: CallbackQuery, callback_data: AdmCb, state: FSMContext):
    await state.clear()
    text, markup = await threads_view(callback_data.p, closed=callback_data.action == "closed")
    await nav(call, text, markup)
    await call.answer()


async def thread_screen(bot: Bot, admin_id: int, user_id: int, note: str = "", fresh: bool = False,
                        call: CallbackQuery | None = None) -> None:
    thread = await db.support_thread(user_id)
    if not thread:
        text, markup = await threads_view()
        return await show(bot, admin_id, "Диалог не найден.\n\n" + text, markup)
    await db.support_mark_read(user_id)
    msgs = await db.support_messages(user_id, limit=15)
    has_media = any(m["media"] for m in msgs)
    is_open = thread["status"] == "open"
    rows = [[("✍️ Ответить", AdmCb(action="sreply", id=user_id))]]
    if has_media:
        rows.append([("📎 Показать вложения", AdmCb(action="smedia", id=user_id))])
    rows.append([("✅ Закрыть диалог" if is_open else "🔓 Открыть снова",
                  AdmCb(action="sclose" if is_open else "sreopen", id=user_id))])
    rows.append([("⬅️ К обращениям", AdmCb(action="support"))])
    text = ((note + "\n\n" if note else "") +
            f"💬 <b>Диалог с {escape(thread['user_name'] or str(user_id))}</b> "
            f"(<a href=\"tg://user?id={user_id}\">{user_id}</a>)"
            f"{' · 📁 закрыт' if not is_open else ''}\n\n" + (history_lines(msgs, 'ru', admin_view=True) or "—"))
    if call:
        await nav(call, text, kb(rows), fresh=fresh)
    else:
        await show(bot, admin_id, text, kb(rows), fresh=fresh)


@admin_router.callback_query(AdmCb.filter(F.action == "sthread"), StateFilter("*"))
async def thread_cb(call: CallbackQuery, callback_data: AdmCb, state: FSMContext, bot: Bot):
    await state.clear()
    await thread_screen(bot, call.from_user.id, callback_data.id, call=call)
    await call.answer()


@admin_router.callback_query(AdmCb.filter(F.action == "smedia"))
async def thread_media(call: CallbackQuery, callback_data: AdmCb, bot: Bot):
    """Показать вложения диалога над экраном (временные сообщения)."""
    msgs = [m for m in await db.support_messages(callback_data.id, limit=15) if m["media"] and m["src_msg_id"]]
    await thread_screen(bot, call.from_user.id, callback_data.id, call=call, fresh=True)
    for m in msgs[-10:]:
        try:
            copy = await bot.copy_message(call.from_user.id, m["src_chat_id"], m["src_msg_id"], reply_markup=None)
            await add_extra(call.from_user.id, copy.message_id)
        except Exception:
            pass
    await call.answer()


@admin_router.callback_query(AdmCb.filter(F.action.in_({"sclose", "sreopen"})))
async def thread_status(call: CallbackQuery, callback_data: AdmCb, bot: Bot):
    await db.support_set_status(callback_data.id, "closed" if callback_data.action == "sclose" else "open")
    await thread_screen(bot, call.from_user.id, callback_data.id, call=call,
                        note="✅ Диалог закрыт." if callback_data.action == "sclose" else "🔓 Диалог открыт.")
    await call.answer()


@admin_router.callback_query(AdmCb.filter(F.action == "sreply"), StateFilter("*"))
async def reply_start(call: CallbackQuery, callback_data: AdmCb, state: FSMContext, bot: Bot):
    await state.clear()
    if not await db.support_thread(callback_data.id):
        return await call.answer("Диалог не найден", show_alert=True)
    await state.set_state(SupportAdmin.reply)
    await state.update_data(user_id=callback_data.id)
    msg_id, _ = await db.get_screen(call.from_user.id)
    fresh = call.message is not None and call.message.message_id != msg_id
    if fresh:
        await remove_input(call.message)
    await thread_screen(bot, call.from_user.id, callback_data.id, fresh=fresh,
                        note="✍️ <b>Напишите ответ</b> — текст или вложение. Пользователь получит его в боте.")
    await call.answer()


@admin_router.message(SupportAdmin.reply)
async def reply_send(message: Message, state: FSMContext, bot: Bot):
    from bots.ads.handlers.user import user_lang  # noqa: F401  (язык берём из БД)
    user_id = (await state.get_data())["user_id"]
    kind = media_kind(message)
    text = message.text or message.caption
    if not text and not kind:
        await remove_input(message)
        return await thread_screen(bot, message.from_user.id, user_id, note="⚠️ Пришлите текст или вложение.")
    lang = await db.get_lang(user_id)
    reply_btn = [[InlineKeyboardButton(text=t(lang, "btn_support_reply"),
                                       callback_data=MenuCb(action="support").pack())]]
    note = "✅ Ответ отправлен."
    try:
        if kind:
            caption = t(lang, "support_reply", text=escape(text)) if text else None
            await bot.copy_message(user_id, message.chat.id, message.message_id,
                                   caption=caption if kind not in ("sticker", "video_note") else None,
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=reply_btn + [[close_button()]]))
        else:
            await bot.send_message(user_id, t(lang, "support_reply", text=escape(text)),
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=reply_btn + [[close_button()]]))
        # вложение админа храним как копию в его же чате — сообщение ниже удалять нельзя
        await db.support_add(user_id, None, True, text, kind,
                             message.chat.id if kind else None, message.message_id if kind else None,
                             media_file_id(message)[1])
    except Exception as e:
        note = f"❌ Не удалось доставить ответ (пользователь заблокировал бота?): {escape(str(e))}"
    if not kind:
        await remove_input(message)
    await state.clear()
    await thread_screen(bot, message.from_user.id, user_id, note=note, fresh=bool(kind))
