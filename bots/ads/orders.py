"""Работа с заказами: пост, оплата, публикация."""
import asyncio
import json
import logging
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bots.ads import db
from bots.ads.config import config
from bots.ads.cryptopay import CryptoPayError, client_for, cryptopay, cryptopay_test
from bots.ads.freekassa import FreeKassaError, freekassa
from bots.ads.prices import paid_amount
from bots.ads.xrocket import XRocketError, webhook_on, xrocket
from bots.ads.i18n import t
from bots.ads.screen import notify
from bots.ads.slots import fmt_ts
from bots.ads.ui import AdmCb, MenuCb, OrdCb, channel_title_link

log = logging.getLogger(__name__)


# ---------- пост ----------
# что берём из кнопки поста: цвет (style) и премиум-эмодзи на кнопке тоже, как их сделал @justpost
BUTTON_FIELDS = {"text", "url", "style", "icon_custom_emoji_id"}


def url_buttons(message: Message) -> list[list[dict]]:
    """Только URL-кнопки: callback-кнопки чужого бота у нас работать не будут."""
    markup = message.reply_markup
    if not isinstance(markup, InlineKeyboardMarkup):
        return []
    rows = [[b.model_dump(include=BUTTON_FIELDS, exclude_none=True) for b in row if b.url]
            for row in markup.inline_keyboard]
    return [r for r in rows if r]


def buttons_markup(rows: list[list[dict]]) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(**b) for b in r] for r in rows])


def extract_markup(message: Message) -> str | None:
    markup = buttons_markup(url_buttons(message))
    return markup.model_dump_json(exclude_none=True) if markup else None


def has_premium_emoji(message: Message) -> bool:
    """Премиум-эмодзи в тексте/подписи или на кнопках поста."""
    if any(e.type == "custom_emoji" for e in message.entities or message.caption_entities or []):
        return True
    return any("icon_custom_emoji_id" in b for row in url_buttons(message) for b in row)


MEDIA_KINDS = ("photo", "video", "animation", "document", "audio", "voice", "video_note", "sticker")


def media_file_id(message: Message) -> tuple[str | None, str | None]:
    """(тип вложения, file_id) — для фото берём самый крупный размер."""
    for kind in MEDIA_KINDS:
        obj = getattr(message, kind, None)
        if obj:
            return kind, (obj[-1].file_id if kind == "photo" else obj.file_id)
    return None, None


def post_snapshot(message: Message) -> str:
    """Снимок поста для веб-панели: текст в HTML, вложение и URL-кнопки."""
    kind, file_id = media_file_id(message)
    try:
        html = message.html_text if (message.text or message.caption) else ""
    except Exception:
        html = escape(message.text or message.caption or "")
    return json.dumps({"kind": kind or "text", "html": html, "file_id": file_id, "buttons": url_buttons(message)},
                      ensure_ascii=False)


def load_markup(raw: str | None) -> InlineKeyboardMarkup | None:
    return InlineKeyboardMarkup.model_validate_json(raw) if raw else None


def without_icons(markup: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup | None:
    """Те же кнопки без премиум-эмодзи; None — если эмодзи на кнопках и не было."""
    if not markup or not any(b.icon_custom_emoji_id for row in markup.inline_keyboard for b in row):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[b.model_copy(update={"icon_custom_emoji_id": None}) for b in row]
                                                 for row in markup.inline_keyboard])


async def copy_with_markup(bot: Bot, chat_id: int, from_chat_id: int, message_id: int,
                           markup: InlineKeyboardMarkup | None) -> int:
    """copy_message переносит текст со всеми entities, премиум-эмодзи тоже. Эмодзи на кнопках боту
    доступны не везде (в каналах — только с юзернеймом с Fragment): если Telegram из-за них отказал —
    шлём те же кнопки без эмодзи, цвет кнопок остаётся."""
    try:
        msg = await bot.copy_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id,
                                     reply_markup=markup)
    except TelegramBadRequest as e:
        plain = without_icons(markup)
        if plain is None:
            raise
        log.warning("copy to %s with button emoji failed (%s), retry without them", chat_id, e)
        msg = await bot.copy_message(chat_id=chat_id, from_chat_id=from_chat_id, message_id=message_id,
                                     reply_markup=plain)
    return msg.message_id


async def copy_post(bot: Bot, order_or_post, chat_id: int) -> int:
    return await copy_with_markup(bot, chat_id, order_or_post["from_chat_id"], order_or_post["message_id"],
                                  load_markup(order_or_post["reply_markup"]))


def post_url(ch, message_id: int) -> str:
    if ch["username"]:
        return f"https://t.me/{ch['username']}/{message_id}"
    return f"https://t.me/c/{str(ch['chat_id']).removeprefix('-100')}/{message_id}"


# ---------- уведомления ----------
def button(text: str, cb) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def orders_btn(lang):
    return [[button(t(lang, "btn_orders"), MenuCb(action="orders"))]]


async def notify_admins(bot: Bot, text: str, buttons=None) -> None:
    for admin_id in config.admin_ids:
        await notify(bot, admin_id, text, buttons)


async def notify_new_moderation(bot: Bot, order_id: int, is_test: bool = False) -> None:
    n = await db.count_status(db.MODERATION)
    await notify_admins(
        bot,
        f"🆕 {'🧪 Тестовый р' if is_test else 'Р'}екламный пост на модерации (заказ #{order_id}).\n"
        f"🛡 На проверке: <b>{n}</b>",
        [[button("🛡 Открыть модерацию", AdmCb(action="mod"))]],
    )


# ---------- оплата и публикация ----------
async def handle_paid(bot: Bot, order_id: int, method: str, **fields) -> None:
    """Вызывается при успешной оплате любым способом."""
    ok = await db.change_status(order_id, db.APPROVED, db.PAID, pay_method=method, paid_at=db.now(), **fields)
    if not ok:
        order = await db.get_order(order_id)
        await notify_admins(
            bot,
            f"⚠️ Получена оплата ({method}) по заказу #{order_id}, но его статус уже "
            f"«{db.STATUS_TITLES.get(order['status'] if order else '', '?')}». "
            f"Возможна двойная оплата — проверьте и при необходимости верните средства.\n"
            f"Данные: <code>{escape(str(fields))}</code>",
        )
        return
    order = await db.get_order(order_id)
    lang = await db.get_lang(order["user_id"])
    if order["is_test"] and method == "stars" and fields.get("charge_id"):
        await refund_test_stars(bot, order, lang)

    paid = paid_amount(order, method)
    # бронируем время только сейчас, после оплаты
    if order["publish_at"]:
        try:
            await db.book_order(order_id, order["publish_at"])
        except db.SlotBusy as e:
            taken = ", ".join(escape(c["title"]) for c in await db.get_channels(e.channel_ids))
            await db.update_order(order_id, status=db.NEED_TIME, publish_at=None)
            await notify(bot, order["user_id"],
                         t(lang, "n_need_time", id=order_id, t=fmt_ts(order["publish_at"], lang), names=taken),
                         [[button(t(lang, "btn_pick_time"), OrdCb(action="resched", id=order_id))]])
            await notify_admins(bot, f"⚠️ Заказ #{order_id} оплачен ({paid}, {method}), но его время заняли — "
                                     "пользователь выбирает новое.")
            return

    # время ещё не наступило — ставим в очередь, планировщик опубликует сам
    if order["publish_at"] and order["publish_at"] > db.now() + 30:
        await db.update_order(order_id, status=db.SCHEDULED)
        await notify(bot, order["user_id"],
                     t(lang, "n_scheduled", id=order_id, t=fmt_ts(order["publish_at"], lang)), orders_btn(lang))
        if not order["is_test"] or order["user_id"] not in config.admin_ids:
            await notify_admins(bot, f"💰 {'🧪 ' if order['is_test'] else ''}Заказ #{order_id} оплачен "
                                     f"({paid}, {method}) от {escape(order['user_name'] or '')}.\n"
                                     f"⏰ Публикация {fmt_ts(order['publish_at'])}.")
        return
    await publish(bot, order)


async def refund_test_stars(bot: Bot, order, lang) -> None:
    try:
        await bot.refund_star_payment(order["user_id"], order["charge_id"])
        text = t(lang, "n_refund", id=order["id"], n=order["total_stars"])
    except Exception as e:
        log.exception("test refund failed")
        text = t(lang, "n_refund_fail", id=order["id"], e=escape(str(e)))
    await notify(bot, order["user_id"], text)


async def cleanup_source(bot: Bot, order) -> None:
    """После публикации исходный пост в чате пользователя больше не нужен."""
    try:
        await bot.delete_message(order["from_chat_id"], order["message_id"])
    except Exception:
        pass


async def publish(bot: Bot, order) -> None:
    if order["is_test"]:
        if await publish_test(bot, order):
            await cleanup_source(bot, order)
        return
    channels = await db.get_channels(db.order_channel_ids(order))
    done, failed = [], []
    for ch in channels:
        try:
            mid = await copy_post(bot, order, ch["chat_id"])
            await db.add_publication(order["id"], ch["id"], ch["chat_id"], mid, None)
            done.append(f'• <a href="{post_url(ch, mid)}">{escape(ch["title"])}</a>')
        except Exception as e:
            log.exception("publish failed order=%s channel=%s", order["id"], ch["chat_id"])
            await db.add_publication(order["id"], ch["id"], ch["chat_id"], None, str(e))
            failed.append(f"• {channel_title_link(ch)}: {escape(str(e))}")
        await asyncio.sleep(0.5)

    await db.update_order(order["id"], status=db.PUBLISHED)
    if not failed:  # при ошибках исходник оставляем — пригодится для повторной публикации
        await cleanup_source(bot, order)

    lang = await db.get_lang(order["user_id"])
    user_text = t(lang, "n_published", id=order["id"]) + ("\n".join(done) or "—")
    if failed:
        user_text += t(lang, "n_partial")
    await notify(bot, order["user_id"], user_text, orders_btn(lang))

    paid = paid_amount(order, order["pay_method"])
    admin_text = (f"💰 Заказ #{order['id']} оплачен ({paid}, {order['pay_method']}) "
                  f"от {escape(order['user_name'] or '')} (<code>{order['user_id']}</code>).\n\n"
                  f"Опубликовано:\n" + ("\n".join(done) or "—"))
    if failed:
        admin_text += "\n\n❌ Ошибки публикации:\n" + "\n".join(failed)
    await notify_admins(bot, admin_text)


async def publish_test(bot: Bot, order) -> bool:
    """Тестовый заказ: один пост только в тестовый канал, реальные каналы не трогаем."""
    channels = await db.get_channels(db.order_channel_ids(order))
    would = "\n".join(f"• {channel_title_link(c)}" for c in channels) or "—"
    result = "⚠️ TEST_CHANNEL_ID не задан — публикация пропущена."
    ok = False
    if config.test_channel_id:
        try:
            mid = await copy_post(bot, order, config.test_channel_id)
            chat = await bot.get_chat(config.test_channel_id)
            url = post_url({"username": chat.username, "chat_id": chat.id}, mid)
            await db.add_publication(order["id"], 0, config.test_channel_id, mid, None)
            ok = True
            result = f'✅ Опубликовано в тестовый канал: <a href="{url}">{escape(chat.title or "")}</a>'
        except Exception as e:
            log.exception("test publish failed")
            await db.add_publication(order["id"], 0, config.test_channel_id, None, str(e))
            result = f"❌ Ошибка публикации в тестовый канал: {escape(str(e))}"
    await db.update_order(order["id"], status=db.PUBLISHED)
    lang = await db.get_lang(order["user_id"])
    text = t(lang, "n_test_done", id=order["id"], m=order["pay_method"], result=result, would=would)
    await notify(bot, order["user_id"], text, orders_btn(lang))
    if order["user_id"] not in config.admin_ids:
        await notify_admins(bot, text)
    return ok


# ---------- CryptoBot ----------
async def check_crypto(bot: Bot, order) -> bool:
    """Проверяет счёт CryptoBot по заказу. True — если оплачен."""
    client = client_for(order)
    if not order["cp_invoice_id"] or not client:
        return False
    items = await client.get_invoices([order["cp_invoice_id"]])
    if items and items[0].get("status") == "paid":
        await handle_paid(bot, order["id"], "crypto")
        return True
    return False


async def check_xrocket(bot: Bot, order) -> bool:
    """Проверяет счёт xRocket по заказу. True — если оплачен."""
    if not order["xr_invoice_id"] or not xrocket.enabled:
        return False
    inv = await xrocket.get_invoice(order["xr_invoice_id"])
    if inv and inv.get("status") == "paid":
        return await xrocket_paid(bot, order["id"])
    return False


_xrocket_lock = asyncio.Lock()


async def xrocket_paid(bot: Bot, order_id: int) -> bool:
    """Оплата xRocket приходит тремя путями (опрос, вебхук, «Я оплатил») — засчитываем один раз,
    без ложного «возможна двойная оплата», если два пути сработали одновременно."""
    async with _xrocket_lock:
        order = await db.get_order(order_id)
        if not order or order["status"] != db.APPROVED:
            return bool(order) and order["pay_method"] == "xrocket"
        await handle_paid(bot, order_id, "xrocket")
        return True


async def check_freekassa(bot: Bot, order) -> bool:
    """Проверяет оплату FreeKassa по заказу. True — если оплачен."""
    if not order["fk_payment_id"] or not freekassa.enabled:
        return False
    if await freekassa.is_paid(order["fk_payment_id"]):
        await handle_paid(bot, order["id"], "freekassa")
        return True
    return False


XROCKET_BACKUP_POLL = 600   # с вебхуком счета xRocket перепроверяются раз в 10 минут — на случай пропущенного


async def crypto_poll_loop(bot: Bot, interval: int = 20) -> None:
    xr_polled = 0
    while True:
        await asyncio.sleep(interval)
        try:
            orders = await db.orders_with_crypto_invoice()
            for is_test, client in ((0, cryptopay), (1, cryptopay_test)):
                by_invoice = {o["cp_invoice_id"]: o for o in orders if o["is_test"] == is_test}
                if not by_invoice or not client.token:
                    continue
                for inv in await client.get_invoices(list(by_invoice)):
                    if inv.get("status") == "paid" and inv["invoice_id"] in by_invoice:
                        await handle_paid(bot, by_invoice[inv["invoice_id"]]["id"], "crypto")
        except CryptoPayError as e:
            log.warning("cryptopay poll error: %s", e)
        except Exception:
            log.exception("crypto poll loop failed")
        if xrocket.enabled and (not webhook_on() or db.now() - xr_polled >= XROCKET_BACKUP_POLL):
            xr_polled = db.now()
            try:
                pending = await db.orders_with_xrocket_invoice()
                if pending:
                    paid = await xrocket.paid_ids()
                    for order in pending:
                        if str(order["xr_invoice_id"]) in paid:
                            await xrocket_paid(bot, order["id"])
            except XRocketError as e:
                log.warning("xrocket poll error: %s", e)
            except Exception:
                log.exception("xrocket poll failed")
        if freekassa.enabled:
            # ссылки старше двух суток не опрашиваем — их проверит кнопка «Я оплатил»
            try:
                for order in await db.orders_with_fk_invoice(db.now() - 2 * 86400):
                    await check_freekassa(bot, order)
            except FreeKassaError as e:
                log.warning("freekassa poll error: %s", e)
            except Exception:
                log.exception("freekassa poll failed")


# ---------- планировщик ----------
async def scheduler_loop(bot: Bot, interval: int = 30) -> None:
    """Публикует оплаченные заказы в назначенное время."""
    while True:
        try:
            await run_scheduler(bot)
        except Exception:
            log.exception("scheduler failed")
        await asyncio.sleep(interval)


async def run_scheduler(bot: Bot) -> None:
    ts = db.now()
    for order in await db.due_scheduled(ts):
        # «захватываем» заказ, чтобы не опубликовать дважды
        if await db.change_status(order["id"], db.SCHEDULED, db.PAID):
            await publish(bot, await db.get_order(order["id"]))

