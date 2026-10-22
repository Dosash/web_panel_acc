"""Живые клиенты Telethon для всех аккаунтов и рассылка событий в веб-панель."""
import asyncio
import json
import logging
import time
from datetime import datetime
from urllib.parse import urlparse

from opentele.api import APIData
from opentele.tl import TelegramClient
from telethon import events, functions, types, utils
from telethon.errors import RPCError
from telethon.tl.custom import Dialog
from telethon.errors import AuthKeyUnregisteredError, UserDeactivatedBanError, UserDeactivatedError
from telethon.sessions import StringSession

from . import storage

log = logging.getLogger("panel")


def parse_proxy(url: str) -> dict | None:
    """socks5://user:pass@host:port или http://host:port → формат прокси Telethon."""
    if not url:
        return None
    u = urlparse(url if "://" in url else f"socks5://{url}")
    if not u.hostname or not u.port:
        raise ValueError("Прокси должен быть вида socks5://user:pass@host:port")
    return {"proxy_type": u.scheme, "addr": u.hostname, "port": u.port,
            "username": u.username, "password": u.password, "rdns": True}


# ---------- сериализация ----------

def peer_type(entity) -> str:
    if isinstance(entity, types.User):
        return "bot" if entity.bot else "user"
    if isinstance(entity, types.Channel):
        return "group" if entity.megagroup else "channel"
    return "group"


def username(entity) -> str | None:
    """Основное @имя. У каналов с коллекционными именами (Fragment) поле username пустое — они в usernames."""
    if getattr(entity, "username", None):
        return entity.username
    return next((u.username for u in getattr(entity, "usernames", None) or [] if u.active), None)


def display_name(entity) -> str:
    if entity is None:
        return ""
    if isinstance(entity, types.User):
        name = " ".join(filter(None, [entity.first_name, entity.last_name]))
        return name or (entity.username and f"@{entity.username}") or "Удалённый аккаунт"
    return getattr(entity, "title", "") or ""


def media_info(msg) -> dict | None:
    m = msg.media
    if m is None:
        return None
    spoiler = bool(getattr(m, "spoiler", False))
    if isinstance(m, types.MessageMediaPhoto):
        sizes = [s for s in getattr(m.photo, "sizes", []) if getattr(s, "w", None)]
        big = max(sizes, key=lambda s: s.w * s.h, default=None)
        return {"type": "photo", "w": big.w if big else None, "h": big.h if big else None,
                "spoiler": spoiler}
    if isinstance(m, types.MessageMediaDocument) and msg.document:
        doc = msg.document
        kind = "file"
        if msg.sticker:
            kind = "sticker"
        elif msg.gif:
            kind = "gif"
        elif msg.video_note:
            kind = "round"
        elif msg.video:
            kind = "video"
        elif msg.voice:
            kind = "voice"
        elif msg.audio:
            kind = "audio"
        name = next((a.file_name for a in doc.attributes
                     if isinstance(a, types.DocumentAttributeFilename)), "")
        dims = next((a for a in doc.attributes if isinstance(
            a, (types.DocumentAttributeVideo, types.DocumentAttributeImageSize))), None)
        return {"type": kind, "name": name, "size": doc.size, "mime": doc.mime_type,
                "w": getattr(dims, "w", None), "h": getattr(dims, "h", None), "spoiler": spoiler}
    if isinstance(m, types.MessageMediaWebPage):
        page = m.webpage
        if isinstance(page, types.WebPage):
            return {"type": "webpage", "url": page.url, "site": page.site_name or "",
                    "title": page.title or "", "description": (page.description or "")[:300]}
        return None
    if isinstance(m, types.MessageMediaGeo):
        return {"type": "geo"}
    if isinstance(m, types.MessageMediaContact):
        return {"type": "contact", "name": f"{m.first_name} {m.last_name}".strip(), "phone": m.phone_number}
    if isinstance(m, types.MessageMediaPoll):
        return {"type": "poll", "title": m.poll.question.text if hasattr(m.poll.question, "text") else str(m.poll.question)}
    return {"type": type(m).__name__.replace("MessageMedia", "").lower()}


def action_text(msg) -> str:
    a = msg.action
    if a is None:
        return ""
    names = {
        types.MessageActionChatCreate: "создал(а) группу",
        types.MessageActionChannelCreate: "канал создан",
        types.MessageActionChatAddUser: "добавил(а) участника",
        types.MessageActionChatDeleteUser: "участник вышел",
        types.MessageActionChatJoinedByLink: "вступил(а) по ссылке",
        types.MessageActionChatEditTitle: "изменено название",
        types.MessageActionChatEditPhoto: "изменено фото",
        types.MessageActionPinMessage: "закрепил(а) сообщение",
        types.MessageActionContactSignUp: "теперь в Telegram",
        types.MessageActionPhoneCall: "звонок",
    }
    for cls, text in names.items():
        if isinstance(a, cls):
            return text
    return type(a).__name__.replace("MessageAction", "")


_ENTITY_TYPES = {
    types.MessageEntityBold: "bold", types.MessageEntityItalic: "italic",
    types.MessageEntityUnderline: "underline", types.MessageEntityStrike: "strike",
    types.MessageEntityCode: "code", types.MessageEntityPre: "pre",
    types.MessageEntitySpoiler: "spoiler", types.MessageEntityBlockquote: "quote",
    types.MessageEntityTextUrl: "link", types.MessageEntityUrl: "url",
    types.MessageEntityEmail: "email", types.MessageEntityPhone: "phone",
    types.MessageEntityMention: "mention", types.MessageEntityMentionName: "mention_name",
    types.MessageEntityHashtag: "hashtag", types.MessageEntityCashtag: "hashtag",
    types.MessageEntityBotCommand: "command",
}


def entities_list(msg) -> list[dict]:
    """Форматирование текста. Смещения в UTF-16 — так же считает длину строки JavaScript."""
    result = []
    for e in msg.entities or []:
        kind = _ENTITY_TYPES.get(type(e))
        if kind is None:
            continue
        item = {"type": kind, "offset": e.offset, "length": e.length}
        if kind == "link":
            item["url"] = e.url
        elif kind == "pre":
            item["language"] = e.language or ""
        elif kind == "mention_name":
            item["user_id"] = e.user_id
        result.append(item)
    return result


_BUTTON_KINDS = {
    types.InlineButtonTypeUrl: "url", types.InlineButtonTypeUrlAuth: "url",
    types.InlineButtonTypeWebView: "webview", types.InlineButtonTypeCallback: "callback",
    types.InlineButtonTypeGame: "game", types.InlineButtonTypeSwitchInline: "switch",
    types.InlineButtonTypeCopy: "copy", types.InlineButtonTypeUserProfile: "profile",
    types.InlineButtonTypeBuy: "buy", types.InlineButtonTypeDisabled: "disabled",
}


def buttons_list(msg) -> list[list[dict]] | None:
    """Inline-кнопки под сообщением (ссылки, кнопки ботов)."""
    markup = msg.reply_markup
    if not isinstance(markup, types.ReplyInlineMarkup):
        return None
    rows = []
    for row in markup.rows:
        out = []
        for b in row.buttons:
            t = b.type
            item = {"text": b.text, "kind": _BUTTON_KINDS.get(type(t), "other")}
            if getattr(t, "url", None):
                item["url"] = t.url
            if isinstance(t, types.InlineButtonTypeCopy):
                item["copy"] = t.copy_text
            if isinstance(t, types.InlineButtonTypeCallback) and t.requires_password:
                item["kind"] = "password"
            out.append(item)
        rows.append(out)
    return rows or None


def message_dict(account_id: int, msg, sender=None) -> dict:
    sender = sender or msg.sender
    return {
        "account_id": account_id,
        "chat_id": msg.chat_id,
        "id": msg.id,
        "date": msg.date.timestamp() if msg.date else 0,
        "edit_date": msg.edit_date.timestamp() if msg.edit_date else None,
        "out": bool(msg.out),
        "text": msg.message or "",
        "entities": entities_list(msg),
        "buttons": buttons_list(msg),
        "sender_id": msg.sender_id,
        "sender_name": display_name(sender),
        "reply_to": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
        "media": media_info(msg),
        "action": action_text(msg),
        "views": msg.views,
        "pinned": bool(msg.pinned),
    }


MUTE_FOREVER = 2 ** 31 - 1


def is_muted(notify_settings) -> bool:
    """mute_until в прошлом — уведомления уже включились сами."""
    until = getattr(notify_settings, "mute_until", None)
    if not until:
        return False
    ts = until.timestamp() if isinstance(until, datetime) else int(until)
    return ts > time.time()


def dialog_dict(account_id: int, d) -> dict:
    last = d.message
    preview, last_media, last_action = "", None, ""
    if last is not None:
        preview = last.message or ""
        last_action = action_text(last)
        if last.media is not None:
            last_media = (media_info(last) or {}).get("type")
    entity = d.entity
    return {
        "account_id": account_id,
        "id": d.id,
        "title": display_name(entity),
        "type": peer_type(entity),
        "username": username(entity),
        "unread": d.unread_count,
        "mentions": d.unread_mentions_count,
        "pinned": d.pinned,
        "archived": d.archived,
        "muted": is_muted(d.dialog.notify_settings),
        "date": d.date.timestamp() if d.date else 0,
        "last_text": preview[:200],
        "last_media": last_media,
        "last_action": last_action,
        "last_out": bool(last and last.out),
        "is_creator": bool(getattr(entity, "creator", False)),
        "is_admin": bool(getattr(entity, "admin_rights", None)) or bool(getattr(entity, "creator", False)),
        "verified": bool(getattr(entity, "verified", False)),
    }


# ---------- менеджер ----------

class Hub:
    """WebSocket-подписчики панели."""

    def __init__(self):
        self.sockets: set = set()

    async def send(self, event: dict) -> None:
        data = json.dumps(event, ensure_ascii=False, default=str)
        for ws in list(self.sockets):
            try:
                await ws.send_text(data)
            except Exception:
                self.sockets.discard(ws)


class Live:
    """Состояние одного аккаунта в памяти."""

    def __init__(self, account: storage.Account):
        self.account = account
        self.client: TelegramClient | None = None
        self.status = "offline"   # offline | connecting | online | error
        self.error = ""
        self.dialogs_loaded = False


class Manager:
    def __init__(self):
        self.hub = Hub()
        self.live: dict[int, Live] = {}
        self._media_slots: dict[int, asyncio.Semaphore] = {}

    def media_slot(self, account_id: int) -> asyncio.Semaphore:
        if account_id not in self._media_slots:
            self._media_slots[account_id] = asyncio.Semaphore(4)
        return self._media_slots[account_id]

    def get(self, account_id: int) -> Live:
        live = self.live.get(account_id)
        if live is None:
            raise KeyError(account_id)
        return live

    def client(self, account_id: int) -> TelegramClient:
        live = self.get(account_id)
        if live.client is None or live.status != "online":
            raise RuntimeError(f"Аккаунт «{live.account.name}» не подключён: {live.error or live.status}")
        return live.client

    def state(self, account_id: int) -> dict:
        live = self.get(account_id)
        return {**live.account.public(), "status": live.status, "error": live.error}

    async def start_all(self) -> None:
        await asyncio.gather(*(self.start(a) for a in storage.list_accounts()))

    async def stop_all(self) -> None:
        await asyncio.gather(*(self.stop(i) for i in list(self.live)))

    async def start(self, account: storage.Account) -> None:
        await self.stop(account.id)
        live = Live(account)
        self.live[account.id] = live
        live.status = "connecting"
        await self._status(live)
        try:
            api = APIData(**account.api)
            client = TelegramClient(StringSession(account.session), api=api,
                                    proxy=parse_proxy(account.proxy), flood_sleep_threshold=30)
            live.client = client
            await client.connect()
            if not await client.is_user_authorized():
                raise AuthKeyUnregisteredError(None)
            me = await client.get_me()
            storage.update_account(account.id, phone=me.phone or "", username=me.username or "",
                                   full_name=" ".join(filter(None, [me.first_name, me.last_name])))
            live.account = storage.get_account(account.id)
            self._bind(live)
            live.status, live.error = "online", ""
        except (AuthKeyUnregisteredError, UserDeactivatedError, UserDeactivatedBanError) as e:
            live.status = "error"
            live.error = "Сессия недействительна или аккаунт заблокирован" if not isinstance(
                e, UserDeactivatedBanError) else "Аккаунт заблокирован Telegram"
            await self._drop_client(live)
        except Exception as e:
            log.exception("Не удалось подключить аккаунт %s", account.name)
            live.status, live.error = "error", str(e) or type(e).__name__
            await self._drop_client(live)
        await self._status(live)

    async def stop(self, account_id: int) -> None:
        live = self.live.pop(account_id, None)
        if live:
            await self._drop_client(live)

    async def _drop_client(self, live: Live) -> None:
        if live.client is not None:
            try:
                await live.client.disconnect()
            except Exception:
                pass
            live.client = None

    async def _status(self, live: Live) -> None:
        await self.hub.send({"type": "account", "account": {
            **live.account.public(), "status": live.status, "error": live.error}})

    def _bind(self, live: Live) -> None:
        client, aid = live.client, live.account.id

        @client.on(events.NewMessage())
        async def on_new(event):
            sender = await event.get_sender()
            chat = await event.get_chat()
            await self.hub.send({"type": "message", "message": message_dict(aid, event.message, sender),
                                 "chat_title": display_name(chat), "chat_type": peer_type(chat)})

        @client.on(events.MessageEdited())
        async def on_edit(event):
            await self.hub.send({"type": "edit", "message": message_dict(aid, event.message)})

        @client.on(events.MessageDeleted())
        async def on_delete(event):
            await self.hub.send({"type": "delete", "account_id": aid, "chat_id": event.chat_id,
                                 "ids": event.deleted_ids})

        @client.on(events.MessageRead())
        async def on_read(event):
            if event.contents:
                return
            # Входящие прочитаны в другом клиенте (телефон, Desktop) — Telegram сообщает, сколько осталось
            unread = getattr(getattr(event, "original_update", None), "still_unread_count", None)
            await self.hub.send({"type": "read", "account_id": aid, "chat_id": event.chat_id,
                                 "max_id": event.max_id, "outbox": event.outbox, "unread": unread})

    # ---------- помощники ----------

    async def entity(self, account_id: int, chat_id: int):
        """Находит собеседника по id. После перезапуска кэш пуст — догружаем диалоги один раз."""
        client = self.client(account_id)
        live = self.get(account_id)
        try:
            return await client.get_input_entity(chat_id)
        except ValueError:
            if live.dialogs_loaded:
                raise
            await client.get_dialogs(limit=None)
            live.dialogs_loaded = True
            return await client.get_input_entity(chat_id)

    async def read_chat(self, account_id: int, entity, max_id: int = 0) -> None:
        """Отмечает чат прочитанным. max_id=0 («всё») каналы молча игнорируют — передаём id последнего сообщения."""
        client = self.client(account_id)
        if not max_id:
            last = await client.get_messages(entity, limit=1)
            max_id = last[0].id if last else 0
        if max_id:
            await client.send_read_acknowledge(entity, max_id=max_id)

    def peer_id(self, entity) -> int:
        return utils.get_peer_id(entity)

    async def peer_dialogs(self, account_id: int, chat_ids: list[int]) -> list[dict]:
        """Диалоги по списку id одним запросом — для папок, где чаты могут быть далеко за первой сотней."""
        client = self.client(account_id)
        peers = []
        for cid in chat_ids:
            try:
                peers.append(types.InputDialogPeer(await self.entity(account_id, cid)))
            except (ValueError, RPCError):
                log.info("Чат %s аккаунта %s недоступен — пропускаю", cid, account_id)
        if not peers:
            return []
        res = await client(functions.messages.GetPeerDialogsRequest(peers=peers))
        entities = {utils.get_peer_id(e): e for e in [*res.users, *res.chats]}
        messages = {}
        for m in res.messages:
            m._finish_init(client, entities, None)
            messages[(utils.get_peer_id(m.peer_id), m.id)] = m
        result = []
        for dlg in res.dialogs:
            message = messages.get((utils.get_peer_id(dlg.peer), dlg.top_message))
            result.append(dialog_dict(account_id, Dialog(client, dlg, entities, message)))
        return result
