"""Красивые посты: форматирование, медиа, кнопки. Inline-кнопки у обычного аккаунта Telegram молча
отбрасывает, поэтому пост с кнопками публикует бот — администратор канала."""
import asyncio
import logging
import re
from urllib.parse import urlparse

from telethon import TelegramClient, functions, types
from telethon.errors import RPCError, UserNotParticipantError
from telethon.sessions import StringSession

log = logging.getLogger("panel")

TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024        # у бота подпись к медиа не длиннее 1024 (у аккаунта с Premium — больше)
ROW_LIMIT = 8               # кнопок в ряду
BUTTONS_LIMIT = 100
TOKEN_RE = re.compile(r"^\d{5,}:[\w-]{30,}$")

_ENTITIES = {
    "bold": types.MessageEntityBold, "italic": types.MessageEntityItalic,
    "underline": types.MessageEntityUnderline, "strike": types.MessageEntityStrike,
    "code": types.MessageEntityCode, "spoiler": types.MessageEntitySpoiler,
}


def normalize_url(raw: str | None) -> str:
    """Ссылка для кнопки или текста: без схемы → https://, допускаются только http(s) и tg://."""
    s = (raw or "").strip()
    if not s:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*:", s, re.I):
        s = "https://" + s.lstrip("/")
    u = urlparse(s)
    if u.scheme == "tg" or (u.scheme in ("http", "https") and u.hostname and "." in u.hostname):
        return s
    return ""


def entities(items: list[dict]) -> list:
    """Форматирование из редактора → сущности Telegram. Смещения уже в UTF-16 (так считает JavaScript)."""
    result = []
    for e in items or []:
        kind, offset, length = e.get("type"), int(e.get("offset", 0)), int(e.get("length", 0))
        if offset < 0 or length <= 0:
            continue
        if kind == "link":
            url = normalize_url(e.get("url"))
            if url:
                result.append(types.MessageEntityTextUrl(offset, length, url))
        elif kind == "pre":
            result.append(types.MessageEntityPre(offset, length, language=e.get("language") or ""))
        elif kind == "quote":
            result.append(types.MessageEntityBlockquote(offset, length, collapsed=bool(e.get("collapsed")) or None))
        elif kind in _ENTITIES:
            result.append(_ENTITIES[kind](offset, length))
    return result


def markup(rows: list[list[dict]] | None) -> types.ReplyInlineMarkup | None:
    """Кнопки из редактора: ссылка или «скопировать текст», цвет — primary / success / danger."""
    result, total = [], 0
    for row in rows or []:
        buttons = []
        for b in row:
            text = (b.get("text") or "").strip()
            if not text:
                raise ValueError("У одной из кнопок нет текста")
            if b.get("copy"):
                kind = types.InlineButtonTypeCopy(copy_text=str(b["copy"])[:256])
            else:
                url = normalize_url(b.get("url"))
                if not url:
                    raise ValueError(f"Кнопка «{text}»: укажите ссылку (https://… или t.me/…)")
                kind = types.InlineButtonTypeUrl(url)
            style = b.get("style")
            st = types.KeyboardButtonStyle(bg_primary=style == "primary" or None, bg_success=style == "success" or None,
                                           bg_danger=style == "danger" or None) if style in ("primary", "success", "danger") else None
            buttons.append(types.KeyboardInlineButton(text[:64], kind, style=st))
        if len(buttons) > ROW_LIMIT:
            raise ValueError(f"В одном ряду не больше {ROW_LIMIT} кнопок")
        total += len(buttons)
        if buttons:
            result.append(types.KeyboardInlineButtonRow(buttons))
    if total > BUTTONS_LIMIT:
        raise ValueError(f"Кнопок не больше {BUTTONS_LIMIT}")
    return types.ReplyInlineMarkup(result) if result else None


async def send(client, peer, text: str, ents: list, *, path=None, reply_markup=None, silent=False,
               no_preview=False, invert=False, spoiler=False, schedule=None):
    """Отправка сырым запросом: у send_file Telethon нет спойлера на медиа и «текста над картинкой»."""
    if path:
        _, media, _ = await client._file_to_media(str(path), supports_streaming=True)
        if spoiler and hasattr(media, "spoiler"):
            media.spoiler = True
        request = functions.messages.SendMediaRequest(
            peer, media, text, silent=silent or None, invert_media=invert or None, reply_markup=reply_markup,
            entities=ents or None, schedule_date=schedule)
    else:
        request = functions.messages.SendMessageRequest(
            peer, text, no_webpage=no_preview or None, silent=silent or None, invert_media=invert or None,
            reply_markup=reply_markup, entities=ents or None, schedule_date=schedule)
    result = await client(request)
    return client._get_response_message(request, result, peer)


# ---------- боты ----------

_bots: dict[str, TelegramClient] = {}
_lock = asyncio.Lock()


async def bot_client(token: str, session: str, api: dict, proxy: dict | None) -> TelegramClient:
    """Клиент бота держим подключённым: вход по токену Telegram ограничивает, а сессия сохраняется в базе."""
    async with _lock:
        client = _bots.get(token)
        if client is not None and client.is_connected():
            return client
        client = TelegramClient(StringSession(session or None), api["api_id"], api["api_hash"], proxy=proxy,
                                receive_updates=False, flood_sleep_threshold=30, device_model="TG Panel")
        await client.connect()
        try:
            if not await client.is_user_authorized():
                await client.sign_in(bot_token=token)
        except RPCError as e:
            await client.disconnect()
            if "TOKEN" in (e.message or ""):
                raise ValueError("Токен бота недействителен — возьмите актуальный у @BotFather") from None
            raise
        _bots[token] = client
        return client


async def drop_bot(token: str) -> None:
    client = _bots.pop(token, None)
    if client is not None:
        await client.disconnect()


async def close_all() -> None:
    await asyncio.gather(*(drop_bot(t) for t in list(_bots)), return_exceptions=True)


async def bot_admin(client, channel: types.Channel, bot) -> bool:
    """Может ли бот публиковать: в канале нужно право «публикация», в группе достаточно быть участником."""
    try:
        res = await client(functions.channels.GetParticipantRequest(channel, bot))
    except UserNotParticipantError:
        return False
    p = res.participant
    if isinstance(p, types.ChannelParticipantAdmin):
        return bool(p.admin_rights.post_messages) or channel.megagroup
    return channel.megagroup and not isinstance(p, (types.ChannelParticipantBanned, types.ChannelParticipantLeft))


async def promote_bot(client, channel: types.Channel, bot) -> None:
    rights = (types.ChatAdminRights(delete_messages=True, pin_messages=True) if channel.megagroup else
              types.ChatAdminRights(post_messages=True, edit_messages=True, delete_messages=True))
    await client(functions.channels.EditAdminRequest(channel, bot, rights, rank=""))
