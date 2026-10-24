"""Аудитория бота: кто пользуется ботом, кто его заблокировал, и приём поста для рассылки от админа."""
from typing import Any
from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMemberUpdated, Message, TelegramObject

from bots.ads import broadcast, db
from bots.ads.config import config
from bots.ads.screen import notify

router = Router(name="audience")


class TouchUser(BaseMiddleware):
    """Любое сообщение или нажатие кнопки в личке — пользователь есть и бот у него не заблокирован."""

    async def __call__(self, handler: Callable[[TelegramObject, dict], Awaitable[Any]],
                       event: TelegramObject, data: dict) -> Any:
        user = getattr(event, "from_user", None)
        chat = event.chat if isinstance(event, Message) else getattr(getattr(event, "message", None), "chat", None)
        if user and not user.is_bot and (chat is None or chat.type == "private"):
            try:
                await db.touch_user(user.id, user.first_name, user.username)
            except Exception:
                pass
        return await handler(event, data)


@router.my_chat_member(F.chat.type == "private")
async def private_membership(update: ChatMemberUpdated):
    """Пользователь заблокировал (kicked) или снова запустил бота."""
    await db.set_blocked(update.chat.id, update.new_chat_member.status == ChatMemberStatus.KICKED)


def _capturing(message: Message) -> bool:
    # команды (/start, /admin) работают как обычно и приём поста не сбивают
    return (broadcast.capture_active() and message.from_user is not None
            and message.from_user.id in config.admin_ids and not (message.text or "").startswith("/"))


@router.message(F.chat.type == "private", _capturing)
async def capture_post(message: Message, bot: Bot):
    """Панель ждёт пост для рассылки: первое сообщение админа становится черновиком."""
    if message.media_group_id:
        return await notify(bot, message.chat.id, "⚠️ Альбом разослать нельзя — пришлите один пост "
                                                  "(одно фото или видео с текстом).")
    broadcast.stop_capture()
    await broadcast.save_draft(message, "telegram")
    await notify(bot, message.chat.id, "✅ Пост сохранён как черновик рассылки.\n"
                                       "Проверьте его и запустите рассылку в веб-панели, раздел «Рассылка».\n"
                                       "<i>Не удаляйте пост из чата, пока рассылка не закончится.</i>")
