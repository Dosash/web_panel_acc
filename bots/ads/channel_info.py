"""Получение информации о канале: название, подписчики, средние просмотры."""
import asyncio
import logging
import re

import aiohttp
from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from bots.ads import db

log = logging.getLogger(__name__)

VIEWS_RE = re.compile(r'class="tgme_widget_message_views">([^<]+)<')


def parse_count(s: str) -> int:
    s = s.strip().upper().replace(",", ".")
    mult = 1
    if s.endswith("K"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000, s[:-1]
    try:
        return int(float(s) * mult)
    except ValueError:
        return 0


async def fetch_avg_views(username: str) -> int | None:
    """Средние просмотры по публичной веб-ленте t.me/s/<username>.

    Самые свежие посты не учитываются — они ещё не набрали просмотры.
    Для приватных каналов вернёт None (просмотры задаются вручную в админке).
    """
    url = f"https://t.me/s/{username}"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(url, headers={"User-Agent": "Mozilla/5.0"}) as r:
                if r.status != 200:
                    return None
                html = await r.text()
    except (TimeoutError, aiohttp.ClientError) as e:
        log.warning("views fetch failed for %s: %s", username, e)
        return None
    views = [parse_count(v) for v in VIEWS_RE.findall(html)]
    if not views:
        return None
    if len(views) > 6:
        views = views[:-2]          # отбрасываем 2 самых свежих поста
    views = views[-15:]
    return int(sum(views) / len(views))


class ChannelError(Exception):
    pass


async def bot_is_admin(bot: Bot, chat_id: int) -> bool:
    """Бот — администратор канала с правом публикации."""
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
    except Exception:
        return False
    return me.status == ChatMemberStatus.ADMINISTRATOR and bool(getattr(me, "can_post_messages", False))


async def fetch_and_save(bot: Bot, chat_ref: int | str) -> int:
    """Берёт данные канала из Telegram, сохраняет в БД, возвращает id канала в БД.

    Канал добавляется, даже если бот ещё не администратор: тогда он помечается
    «бот не админ» и скрыт от пользователей, пока бота не назначат администратором.
    Если Telegram вообще не отдаёт канал (приватный, бот не в нём) — сохраняем
    заготовку по числовому ID, данные подтянутся, когда бота добавят.
    """
    try:
        chat = await bot.get_chat(chat_ref)
    except Exception as e:
        if isinstance(chat_ref, int):
            return await db.upsert_placeholder(chat_ref)
        raise ChannelError(f"Не удалось найти канал: {e}") from e
    if chat.type != "channel":
        raise ChannelError("Это не канал.")
    is_admin = await bot_is_admin(bot, chat.id)
    try:
        subscribers = await bot.get_chat_member_count(chat.id)
    except Exception:
        subscribers = 0
    avg_views = await fetch_avg_views(chat.username) if chat.username else None
    return await db.upsert_channel(
        chat_id=chat.id,
        title=chat.title or str(chat.id),
        username=chat.username,
        invite_link=chat.invite_link,
        description=chat.description,
        subscribers=subscribers,
        avg_views=avg_views,
        bot_admin=is_admin,
    )


async def refresh_all(bot: Bot) -> tuple[int, list[str]]:
    """Обновляет все каналы. Возвращает (обновлено, ошибки); каналы без бота-админа — не ошибка."""
    ok, errors = 0, []
    for ch in await db.list_channels():
        try:
            await fetch_and_save(bot, ch["chat_id"])
            ok += 1
        except ChannelError as e:
            errors.append(f"{ch['title']}: {e}")
        await asyncio.sleep(1)
    return ok, errors


async def refresh_loop(bot: Bot, interval: int = 3600) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            ok, errors = await refresh_all(bot)
            log.info("channels refreshed: %s ok, %s errors", ok, len(errors))
        except Exception:
            log.exception("refresh loop failed")


def channel_link(ch) -> str | None:
    if ch["username"]:
        return f"https://t.me/{ch['username']}"
    return ch["invite_link"]


# ---------- автообнаружение каналов ----------
# chat_id каналов, уже известных боту (чтобы не дёргать Telegram на каждый пост)
_known: set[int] | None = None
# новые каналы для сводки администратору
_found: list[str] = []
_lock = asyncio.Lock()


async def discover(bot: Bot, chat_id: int) -> bool:
    """Добавляет канал, если бот видит его впервые и он там админ. True — если добавлен."""
    global _known
    async with _lock:
        if _known is None:
            _known = await db.known_chat_ids()
        if chat_id in _known:
            return False
        _known.add(chat_id)
    if await db.get_setting(f"ignored:{chat_id}"):
        return False   # канал удалён администратором вручную
    if not await bot_is_admin(bot, chat_id):
        _known.discard(chat_id)   # проверим снова, когда бота назначат админом
        return False
    try:
        channel_id = await fetch_and_save(bot, chat_id)
    except ChannelError as e:
        log.warning("discover %s failed: %s", chat_id, e)
        return False
    ch = await db.get_channel(channel_id)
    if not (ch["price_stars"] or ch["price_usd"] or ch["price_rub"]):
        stars, usd, rub = await db.default_price()
        await db.update_channel(channel_id, price_stars=stars, price_usd=usd, price_rub=rub)
    _found.append(ch["title"])
    log.info("channel discovered: %s (%s)", ch["title"], chat_id)
    return True


def forget(chat_id: int) -> None:
    if _known is not None:
        _known.discard(chat_id)


def remember(chat_id: int) -> None:
    if _known is not None:
        _known.add(chat_id)


def take_found() -> list[str]:
    items = list(_found)
    _found.clear()
    return items
