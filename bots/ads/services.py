"""Операции, общие для бота и веб-панели: модерация, каналы, ответы в поддержку."""
from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bots.ads import channel_info, db, slots
from bots.ads.channel_info import ChannelError, fetch_and_save
from bots.ads.i18n import t
from bots.ads.screen import close_button, notify
from bots.ads.slots import fmt_ts
from bots.ads.prices import Price, fmt_price, has_price, order_price
from bots.ads.ui import MenuCb, OrdCb


class ServiceError(Exception):
    pass


# ---------- модерация ----------
async def approve_order(bot: Bot, order_id: int) -> None:
    if not await db.change_status(order_id, db.MODERATION, db.APPROVED):
        raise ServiceError("Заказ уже обработан или отменён")
    order = await db.get_order(order_id)
    lang = await db.get_lang(order["user_id"])
    if slots.slot_ok(order):
        text = t(lang, "n_approved", id=order["id"], t=fmt_ts(order["publish_at"], lang),
                 total=fmt_price(*order_price(order)))
    else:
        text = t(lang, "n_approved_passed", id=order["id"])
    await notify(bot, order["user_id"], text,
                 [[InlineKeyboardButton(text=t(lang, "btn_go_to_pay"),
                                        callback_data=OrdCb(action="view", id=order["id"]).pack())]])


async def reject_order(bot: Bot, order_id: int, reason: str | None) -> None:
    if not await db.change_status(order_id, db.MODERATION, db.REJECTED, reject_reason=reason):
        raise ServiceError("Заказ уже обработан или отменён")
    order = await db.get_order(order_id)
    lang = await db.get_lang(order["user_id"])
    text = t(lang, "n_rejected", id=order_id)
    if reason:
        text += t(lang, "n_reason", r=escape(reason))
    text += t(lang, "n_fix")
    await notify(bot, order["user_id"], text,
                 [[InlineKeyboardButton(text=t(lang, "btn_new_order"), callback_data=MenuCb(action="buy").pack())]])


# ---------- каналы ----------
async def add_channel(bot: Bot, ref: int | str, price: Price | None = None) -> int:
    """Добавляет канал; без цены — ставит цену по умолчанию. Бросает ChannelError."""
    channel_id = await fetch_and_save(bot, ref)
    ch = await db.get_channel(channel_id)
    if price:
        await set_price(channel_id, price)
    elif not has_price(ch):
        await set_price(channel_id, await db.default_price())
    await db.set_setting(f"ignored:{ch['chat_id']}", "")
    channel_info.remember(ch["chat_id"])
    return channel_id


async def set_price(channel_id: int, price: Price) -> None:
    await db.update_channel(channel_id, price_stars=price[0], price_usd=price[1], price_rub=price[2])


async def delete_channel(channel_id: int) -> None:
    ch = await db.get_channel(channel_id)
    await db.delete_channel(channel_id)
    if ch:
        # удалённый вручную канал не должен вернуться автообнаружением
        await db.set_setting(f"ignored:{ch['chat_id']}", "1")
        channel_info.remember(ch["chat_id"])


# ---------- поддержка ----------
async def support_reply_text(bot: Bot, user_id: int, text: str) -> None:
    """Текстовый ответ пользователю от администратора (из панели)."""
    lang = await db.get_lang(user_id)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_support_reply"), callback_data=MenuCb(action="support").pack())],
        [close_button()],
    ])
    await bot.send_message(user_id, t(lang, "support_reply", text=escape(text)), reply_markup=markup)
    await db.support_add(user_id, None, True, text)


__all__ = ["ServiceError", "ChannelError", "approve_order", "reject_order", "add_channel",
           "delete_channel", "support_reply_text"]
