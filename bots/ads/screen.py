"""Одно «живое» сообщение-меню на пользователя.

Каждый экран редактирует одно и то же сообщение. Временные сообщения
(превью поста, счета) запоминаются как extra и удаляются при следующем переходе.
Уведомления приходят отдельными сообщениями с кнопкой «Скрыть».
"""
import asyncio
import logging
from collections import defaultdict

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bots.ads import db

log = logging.getLogger(__name__)

_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

CLOSE_CB = "ui:close"


async def _delete(bot: Bot, chat_id: int, msg_id: int | None) -> None:
    if not msg_id:
        return
    try:
        await bot.delete_message(chat_id, msg_id)
    except Exception:
        pass


async def show(bot: Bot, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None, *,
               fresh: bool = False, post=None, keep_extra: bool = False) -> None:
    """Показать экран.

    fresh — пересоздать меню внизу чата (нужно, если после меню появились другие сообщения).
    post — заказ/черновик, пост которого показать над меню (временное сообщение).
    keep_extra — не удалять временные сообщения прошлого экрана (меню только редактируется).
    """
    from bots.ads.orders import copy_post  # избегаем циклического импорта

    async with _locks[chat_id]:
        msg_id, extra = await db.get_screen(chat_id)
        if keep_extra and not fresh and post is None:
            new_extra = extra
        else:
            for mid in extra:
                await _delete(bot, chat_id, mid)
            new_extra = []

        if post is not None:
            fresh = True

        if not fresh and msg_id:
            try:
                await bot.edit_message_text(text=text, chat_id=chat_id, message_id=msg_id,
                                            reply_markup=markup, disable_web_page_preview=True)
                await db.save_screen(chat_id, msg_id, new_extra)
                return
            except TelegramBadRequest as e:
                if "not modified" in str(e):
                    await db.save_screen(chat_id, msg_id, new_extra)
                    return
                # сообщение удалено/слишком старое/не текстовое — отправим заново

        await _delete(bot, chat_id, msg_id)
        if post is not None:
            try:
                new_extra.append(await copy_post(bot, post, chat_id))
            except Exception as e:
                text = f"⚠️ Не удалось показать пост: {e}\n\n" + text
        msg = await bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
        await db.save_screen(chat_id, msg.message_id, new_extra)


async def nav(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None, *,
              post=None, fresh: bool = False) -> None:
    """Показать экран в ответ на нажатие кнопки.

    Если кнопка нажата не в текущем меню (уведомление, старое сообщение) —
    это сообщение удаляется, а меню показывается внизу чата.
    """
    msg_id, _ = await db.get_screen(call.from_user.id)
    if call.message and call.message.message_id != msg_id:
        await _delete(call.bot, call.from_user.id, call.message.message_id)
        fresh = True
    await show(call.bot, call.from_user.id, text, markup, fresh=fresh, post=post)


async def add_extra(chat_id: int, msg_id: int) -> None:
    """Временное сообщение (например, счёт) — удалится при следующем переходе."""
    async with _locks[chat_id]:
        menu_id, extra = await db.get_screen(chat_id)
        await db.save_screen(chat_id, menu_id, extra + [msg_id])


async def remove_input(message: Message) -> None:
    """Удалить сообщение пользователя (ввод цены, ID и т.п.), чтобы не засорять чат."""
    try:
        await message.delete()
    except Exception:
        pass


def close_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="✖️ Скрыть", callback_data=CLOSE_CB)


async def notify(bot: Bot, chat_id: int, text: str,
                 buttons: list[list[InlineKeyboardButton]] | None = None) -> None:
    """Уведомление отдельным сообщением с кнопкой «Скрыть»."""
    rows = list(buttons or [])
    rows.append([close_button()])
    try:
        await bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                               disable_web_page_preview=True)
    except Exception as e:
        log.warning("cannot notify %s: %s", chat_id, e)
