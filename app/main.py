import asyncio
import json
import logging
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import aiohttp
import yarl
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel
from starlette.background import BackgroundTask
from telethon import functions, types
from telethon.errors import BotResponseTimeoutError, RPCError

from . import bots, poster, storage, updates
from .config import BASE_DIR, CACHE_DIR, COOKIE_SECRET, TMP_DIR, VERSION, WEB_PASSWORD, WEB_PREFIX
from .manager import MUTE_FOREVER, Manager, dialog_dict, display_name, message_dict, parse_proxy, peer_type, username
from .tdata_import import ImportError_, convert, save_upload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("panel")

manager = Manager()
signer = URLSafeTimedSerializer(COOKIE_SECRET, salt="panel-login")
COOKIE = "panel_auth"
COOKIE_AGE = 30 * 24 * 3600


AUTH_ENABLED = bool(WEB_PASSWORD)
# cookie только для пути панели: за общим nginx у соседних панелей могут быть свои cookie с тем же именем
COOKIE_PATH = WEB_PREFIX or "/"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not AUTH_ENABLED:
        log.warning("WEB_PASSWORD пуст — панель открыта без пароля. Не выставляйте её в интернет.")
    log.info("TG Panel %s: путь %s", VERSION, (WEB_PREFIX or "") + "/")
    storage.init_db()
    task = asyncio.create_task(manager.start_all())
    await bots.start_all()
    yield
    task.cancel()
    # боты и аккаунты — параллельно: программа для ПК ждёт остановку сервера недолго (desktop/server.py)
    await asyncio.gather(bots.stop_all(), manager.stop_all(), return_exceptions=True)
    await close_bot_proxy()
    await poster.close_all()


app = FastAPI(title="TG Panel", version=VERSION, lifespan=lifespan)


class PrefixMiddleware:
    """Панель под путём WEB_PREFIX. nginx передаёт путь как есть (/accounts/api/...), Starlette
    отрезает root_path при поиске маршрута. Без префикса панель тоже отвечает — для проверок на сервере."""

    def __init__(self, app, prefix: str):
        self.app, self.prefix = app, prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            path = scope["path"]
            if path == self.prefix and scope["type"] == "http":
                query = scope.get("query_string", b"").decode("latin-1")
                return await RedirectResponse(self.prefix + "/" + ("?" + query if query else ""))(scope, receive, send)
            if path.startswith(self.prefix + "/"):
                scope = {**scope, "root_path": scope.get("root_path", "") + self.prefix}
        await self.app(scope, receive, send)


if WEB_PREFIX:
    app.add_middleware(PrefixMiddleware, prefix=WEB_PREFIX)


# ---------- ошибки ----------

RPC_MESSAGES = {
    "PINNED_DIALOGS_TOO_MUCH": "Слишком много закреплённых чатов: Telegram разрешает 5 (с Premium — 10). Открепите какой-нибудь",
    "CHANNELS_TOO_MUCH": "Аккаунт состоит в слишком большом числе каналов и групп",
    "USERNAME_OCCUPIED": "Эта ссылка уже занята",
    "USERNAME_INVALID": "Недопустимая ссылка: латиница, цифры и _, от 5 символов",
    "CHAT_ADMIN_REQUIRED": "Нужны права администратора",
    "INVITE_HASH_EXPIRED": "Ссылка-приглашение устарела",
    "USER_ALREADY_PARTICIPANT": "Аккаунт уже состоит в этом чате",
    "USER_PRIVACY_RESTRICTED": "Настройки приватности пользователя не позволяют добавить его",
    "USER_NOT_MUTUAL_CONTACT": "Пользователь должен быть у аккаунта во взаимных контактах",
    "USER_NOT_PARTICIPANT": "Пользователь не состоит в этом чате",
    "USER_CREATOR": "Права владельца изменить нельзя",
    "USER_ID_INVALID": "Пользователь не найден",
    "USERNAME_NOT_OCCUPIED": "Пользователя с таким именем нет",
    "ADMINS_TOO_MUCH": "Достигнут предел числа администраторов",
    "RIGHT_FORBIDDEN": "Нельзя выдать право, которого нет у самого аккаунта",
    "ADMIN_RANK_INVALID": "Должность: до 16 символов, без эмодзи",
    "ADMIN_RANK_EMOJI_NOT_ALLOWED": "Должность: до 16 символов, без эмодзи",
    "BOT_GROUPS_BLOCKED": "Этого бота нельзя добавить в группу",
    "CHAT_NOT_MODIFIED": "Ничего не изменилось",
    "SECONDS_INVALID": "Недопустимый интервал медленного режима",
    "INVITE_REQUEST_SENT": "Заявка отправлена — вступление после одобрения администратором",
    "INVITE_HASH_INVALID": "Ссылка-приглашение недействительна",
    "CHANNEL_PRIVATE": "Канал закрыт или аккаунт в нём заблокирован",
    "BOT_APP_INVALID": "У бота нет такого мини-приложения",
    "BOT_INVALID": "Это не бот или у него нет мини-приложения",
    "QUERY_ID_INVALID": "Сеанс мини-приложения истёк — откройте его заново",
    "MESSAGE_TOO_LONG": "Текст длиннее 4096 символов",
    "MEDIA_CAPTION_TOO_LONG": "Подпись к медиа слишком длинная: до 1024 символов (с Premium — до 4096)",
    "BUTTON_URL_INVALID": "Telegram не принял ссылку в одной из кнопок",
    "ENTITY_BOUNDS_INVALID": "Форматирование выходит за границы текста — попробуйте убрать его и задать заново",
    "SCHEDULE_DATE_TOO_LATE": "Отложить можно не дальше чем на год",
    "SCHEDULE_TOO_MUCH": "В канале слишком много отложенных постов",
    "CHAT_WRITE_FORBIDDEN": "Нет права публиковать в этот чат",
    "ACCESS_TOKEN_INVALID": "Токен бота недействителен — возьмите актуальный у @BotFather",
}


@app.exception_handler(RPCError)
async def rpc_error(_: Request, e: RPCError):
    code = e.message or type(e).__name__
    return JSONResponse({"detail": RPC_MESSAGES.get(code, f"Telegram: {code}")}, status_code=400)


@app.exception_handler(RuntimeError)
async def runtime_error(_: Request, e: RuntimeError):
    return JSONResponse({"detail": str(e)}, status_code=409)


@app.exception_handler(KeyError)
async def key_error(_: Request, e: KeyError):
    return JSONResponse({"detail": f"Аккаунт {e} не найден"}, status_code=404)


@app.exception_handler(bots.NoSuchBot)
async def no_such_bot(_: Request, e: bots.NoSuchBot):
    return JSONResponse({"detail": f"Нет такого бота: {e}"}, status_code=404)


@app.exception_handler(ValueError)
async def value_error(_: Request, e: ValueError):
    return JSONResponse({"detail": str(e)}, status_code=400)


# ---------- вход в панель ----------

def is_authed(token: str | None) -> bool:
    if not AUTH_ENABLED:
        return True
    if not token:
        return False
    try:
        signer.loads(token, max_age=COOKIE_AGE)
        return True
    except BadSignature:
        return False


def auth(request: Request) -> None:
    if not is_authed(request.cookies.get(COOKIE)):
        raise HTTPException(401, "Нужен вход в панель")


class LoginIn(BaseModel):
    password: str


@app.post("/api/login")
async def login(body: LoginIn):
    if body.password != WEB_PASSWORD:
        await asyncio.sleep(1.5)  # замедляем подбор пароля
        raise HTTPException(401, "Неверный пароль")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE, signer.dumps("admin"), max_age=COOKIE_AGE, path=COOKIE_PATH,
                    httponly=True, samesite="strict")
    return resp


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path=COOKIE_PATH)
    return resp


@app.get("/api/session", dependencies=[Depends(auth)])
async def session():
    return {"ok": True, "auth": AUTH_ENABLED, "version": VERSION}


@app.get("/api/health")
async def health():
    """Без входа: для HEALTHCHECK Docker и карточки панели в хабе."""
    states = [live.status for live in manager.live.values()]
    errors = states.count("error")
    return {"status": "degraded" if errors else "ok", "version": VERSION,
            "accounts": len(storage.list_accounts()), "online": states.count("online"), "errors": errors,
            "bots": {name: bot.status for name, bot in bots.bots.items() if bot.configured}}


@app.get("/api/update", dependencies=[Depends(auth)])
async def update_status(force: bool = False):
    """Последний релиз на GitHub и новее ли он этой панели (ответ GitHub кэшируется на 6 часов)."""
    return await updates.status(force)


# ---------- аккаунты ----------

A = [Depends(auth)]


@app.get("/api/accounts", dependencies=A)
async def accounts():
    known = {a.id: a for a in storage.list_accounts()}
    result = []
    for aid, acc in known.items():
        if aid in manager.live:
            result.append(manager.state(aid))
        else:
            result.append({**acc.public(), "status": "offline", "error": ""})
    return result


@app.post("/api/accounts/import", dependencies=A)
async def import_account(
    name: str = Form(...),
    passcode: str = Form(""),
    password_2fa: str = Form(""),
    new_session: bool = Form(False),
    proxy: str = Form(""),
    files: list[UploadFile] = File(...),
):
    name = name.strip()
    if not name:
        raise HTTPException(400, "Укажите имя аккаунта")
    proxy_cfg = parse_proxy(proxy.strip())
    uploaded = [(f.filename or "", await f.read()) for f in files]
    work = save_upload(uploaded)
    try:
        session_str, api, me = await convert(work, unique_id=uuid.uuid4().hex, passcode=passcode,
                                             new_session=new_session, password_2fa=password_2fa,
                                             proxy=proxy_cfg)
    except ImportError_ as e:
        raise HTTPException(400, str(e))
    except (OSError, ConnectionError) as e:
        raise HTTPException(502, f"Нет связи с Telegram: {e}")

    existing = storage.find_by_user_id(me["id"])
    if existing:
        # Повторная загрузка того же аккаунта обновляет его сессию
        account = storage.update_account(existing.id, session=session_str, api=api,
                                         name=name, proxy=proxy.strip())
        updated = True
    else:
        account = storage.add_account(name, session_str, api, proxy.strip(), me)
        updated = False
    await manager.start(account)
    return {**manager.state(account.id), "updated": updated}


class AccountPatch(BaseModel):
    name: str | None = None
    color: str | None = None
    proxy: str | None = None


@app.patch("/api/accounts/{aid}", dependencies=A)
async def patch_account(aid: int, body: AccountPatch):
    if body.proxy is not None:
        parse_proxy(body.proxy.strip())
    account = storage.update_account(aid, name=body.name, color=body.color,
                                     proxy=body.proxy.strip() if body.proxy is not None else None)
    if account is None:
        raise HTTPException(404, "Аккаунт не найден")
    if body.proxy is not None:
        await manager.start(account)
    elif aid in manager.live:
        manager.live[aid].account = account
    return manager.state(aid) if aid in manager.live else account.public()


@app.post("/api/accounts/{aid}/reconnect", dependencies=A)
async def reconnect(aid: int):
    account = storage.get_account(aid)
    if account is None:
        raise HTTPException(404, "Аккаунт не найден")
    await manager.start(account)
    return manager.state(aid)


@app.delete("/api/accounts/{aid}", dependencies=A)
async def remove_account(aid: int, logout: bool = False):
    if logout:
        await manager.client(aid).log_out()
    await manager.stop(aid)
    storage.delete_account(aid)  # заодно убирает чаты аккаунта из папок
    for f in CACHE_DIR.glob(f"*_{aid}_*"):
        f.unlink(missing_ok=True)
    return {"ok": True}


# ---------- профиль и сеансы ----------

@app.get("/api/accounts/{aid}/profile", dependencies=A)
async def profile(aid: int):
    client = manager.client(aid)
    full = await client(functions.users.GetFullUserRequest("me"))
    me = full.users[0]
    return {"id": me.id, "first_name": me.first_name or "", "last_name": me.last_name or "",
            "username": me.username or "", "phone": me.phone or "", "about": full.full_user.about or "",
            "premium": bool(me.premium)}


class ProfileIn(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    about: str | None = None
    username: str | None = None


@app.post("/api/accounts/{aid}/profile", dependencies=A)
async def update_profile(aid: int, body: ProfileIn):
    client = manager.client(aid)
    if any(v is not None for v in (body.first_name, body.last_name, body.about)):
        await client(functions.account.UpdateProfileRequest(
            first_name=body.first_name, last_name=body.last_name, about=body.about))
    if body.username is not None:
        current = (await client.get_me()).username or ""
        if body.username.lstrip("@") != current:
            await client(functions.account.UpdateUsernameRequest(body.username.lstrip("@")))
    await manager.start(storage.get_account(aid))
    return await profile(aid)


async def _save_upload_tmp(file: UploadFile) -> Path:
    folder = TMP_DIR / uuid.uuid4().hex
    folder.mkdir(parents=True)
    path = folder / Path(file.filename or "file").name
    with path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return path


@app.post("/api/accounts/{aid}/photo", dependencies=A)
async def update_photo(aid: int, file: UploadFile = File(...)):
    client = manager.client(aid)
    path = await _save_upload_tmp(file)
    try:
        await client(functions.photos.UploadProfilePhotoRequest(file=await client.upload_file(path)))
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)
    for f in CACHE_DIR.glob(f"a_{aid}_me*"):
        f.unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/accounts/{aid}/authorizations", dependencies=A)
async def authorizations(aid: int):
    res = await manager.client(aid)(functions.account.GetAuthorizationsRequest())
    return [{
        "hash": str(a.hash), "current": bool(a.current), "device": a.device_model,
        "platform": a.platform, "system": a.system_version, "app": f"{a.app_name} {a.app_version}",
        "ip": a.ip, "country": a.country, "active": a.date_active.timestamp(),
    } for a in res.authorizations]


@app.delete("/api/accounts/{aid}/authorizations/{auth_hash}", dependencies=A)
async def reset_authorization(aid: int, auth_hash: str):
    await manager.client(aid)(functions.account.ResetAuthorizationRequest(hash=int(auth_hash)))
    return {"ok": True}


# ---------- диалоги и сообщения ----------

@app.get("/api/dialogs", dependencies=A)
async def dialogs(account_id: int | None = None, archived: bool = False, limit: int = 100,
                  folder_id: int | None = None):
    online = [i for i, l in manager.live.items() if l.status == "online"]

    if folder_id is not None:
        # Папка панели: чаты из разных аккаунтов, грузим ровно их
        by_account: dict[int, list[int]] = {}
        for item in storage.folder_items(folder_id):
            if item["account_id"] in online and (account_id is None or item["account_id"] == account_id):
                by_account.setdefault(item["account_id"], []).append(item["chat_id"])

        async def load(aid: int):
            try:
                return await manager.peer_dialogs(aid, by_account[aid])
            except Exception as e:
                log.warning("Папка %s, аккаунт %s: %s", folder_id, aid, e)
                return []
        chunks = await asyncio.gather(*(load(i) for i in by_account))
    else:
        ids = [account_id] if account_id else online

        async def load(aid: int):
            try:
                ds = await manager.client(aid).get_dialogs(limit=limit, archived=archived)
                return [dialog_dict(aid, d) for d in ds]
            except Exception as e:
                log.warning("Диалоги аккаунта %s: %s", aid, e)
                return []
        chunks = await asyncio.gather(*(load(i) for i in ids))

    merged = [d for chunk in chunks for d in chunk]
    merged.sort(key=lambda d: (not d["pinned"], -d["date"]))
    return merged


class PinIn(BaseModel):
    pinned: bool


@app.post("/api/accounts/{aid}/chats/{cid}/pin", dependencies=A)
async def pin_dialog(aid: int, cid: int, body: PinIn):
    entity = await manager.entity(aid, cid)
    await manager.client(aid)(functions.messages.ToggleDialogPinRequest(
        peer=types.InputDialogPeer(entity), pinned=body.pinned))
    return {"ok": True, "pinned": body.pinned}


class MuteIn(BaseModel):
    muted: bool


@app.post("/api/accounts/{aid}/chats/{cid}/mute", dependencies=A)
async def mute_dialog(aid: int, cid: int, body: MuteIn):
    entity = await manager.entity(aid, cid)
    await manager.client(aid)(functions.account.UpdateNotifySettingsRequest(
        peer=types.InputNotifyPeer(entity),
        settings=types.InputPeerNotifySettings(mute_until=MUTE_FOREVER if body.muted else 0)))
    return {"ok": True, "muted": body.muted}


class ArchiveIn(BaseModel):
    archived: bool


@app.post("/api/accounts/{aid}/chats/{cid}/archive", dependencies=A)
async def archive_dialog(aid: int, cid: int, body: ArchiveIn):
    await manager.client(aid).edit_folder(await manager.entity(aid, cid), 1 if body.archived else 0)
    return {"ok": True, "archived": body.archived}


# ---------- папки панели ----------

class FolderIn(BaseModel):
    name: str


class FolderItemIn(BaseModel):
    account_id: int
    chat_id: int


def _folder_or_404(folder_id: int) -> dict:
    folder = storage.get_folder(folder_id)
    if folder is None:
        raise HTTPException(404, "Папка не найдена")
    return folder


@app.get("/api/folders", dependencies=A)
async def folders():
    return storage.list_folders()


@app.post("/api/folders", dependencies=A)
async def create_folder(body: FolderIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Укажите название папки")
    return storage.create_folder(name[:40])


@app.patch("/api/folders/{folder_id}", dependencies=A)
async def rename_folder(folder_id: int, body: FolderIn):
    _folder_or_404(folder_id)
    if not body.name.strip():
        raise HTTPException(400, "Укажите название папки")
    return storage.rename_folder(folder_id, body.name.strip()[:40])


@app.delete("/api/folders/{folder_id}", dependencies=A)
async def delete_folder(folder_id: int):
    _folder_or_404(folder_id)
    storage.delete_folder(folder_id)
    return {"ok": True}


@app.post("/api/folders/{folder_id}/items", dependencies=A)
async def add_folder_item(folder_id: int, body: FolderItemIn):
    _folder_or_404(folder_id)
    storage.add_folder_item(folder_id, body.account_id, body.chat_id)
    return storage.get_folder(folder_id)


@app.delete("/api/folders/{folder_id}/items", dependencies=A)
async def remove_folder_item(folder_id: int, account_id: int, chat_id: int):
    _folder_or_404(folder_id)
    storage.remove_folder_item(folder_id, account_id, chat_id)
    return storage.get_folder(folder_id)


# Права администратора; "other" интерфейс не показывает, но Telegram ставит его всем админам
ADMIN_RIGHTS = ("change_info", "post_messages", "edit_messages", "delete_messages", "ban_users", "invite_users",
                "pin_messages", "add_admins", "anonymous", "manage_call", "post_stories", "edit_stories",
                "delete_stories", "manage_topics", "other")

# Разрешения участников группы → поля ChatBannedRights (True в них — запрет)
PERMISSIONS = {
    "send_plain": ("send_plain",), "send_photos": ("send_photos",), "send_videos": ("send_videos",),
    "stickers": ("send_stickers", "send_gifs", "send_games", "send_inline"),
    "send_audios": ("send_audios",), "send_docs": ("send_docs",), "send_voices": ("send_voices",),
    "send_roundvideos": ("send_roundvideos",), "embed_links": ("embed_links",), "send_polls": ("send_polls",),
    "invite_users": ("invite_users",), "pin_messages": ("pin_messages",), "change_info": ("change_info",),
}
MEDIA_FIELDS = ("send_photos", "send_videos", "send_stickers", "send_gifs", "send_games", "send_inline",
                "send_audios", "send_docs", "send_voices", "send_roundvideos")
SLOWMODE = (0, 10, 30, 60, 300, 900, 3600)


def rights_dict(rights) -> dict:
    return {k: bool(getattr(rights, k, False)) for k in ADMIN_RIGHTS} if rights else {}


def my_rights(entity) -> dict:
    if getattr(entity, "creator", False):
        return {k: True for k in ADMIN_RIGHTS}
    return rights_dict(getattr(entity, "admin_rights", None))


def permissions_dict(banned) -> dict:
    """Что участникам разрешено. Старые клиенты запрещают всё разом через send_messages/send_media."""
    if banned is None:
        return {k: True for k in PERMISSIONS}
    result = {}
    for key, fields in PERMISSIONS.items():
        off = any(getattr(banned, f, False) for f in fields)
        if fields[0].startswith("send_"):
            off = off or bool(banned.send_messages) or (key != "send_plain" and bool(banned.send_media))
        result[key] = not off
    return result


def banned_rights(allowed: dict[str, bool]) -> types.ChatBannedRights:
    kw = {f: True for key, fields in PERMISSIONS.items() if not allowed.get(key, True) for f in fields}
    if all(kw.get(f) for f in MEDIA_FIELDS):
        kw["send_media"] = True
    return types.ChatBannedRights(until_date=None, **kw)


async def _full_entity(aid: int, cid: int):
    return await manager.client(aid).get_entity(await manager.entity(aid, cid))


@app.get("/api/accounts/{aid}/chats/{cid}", dependencies=A)
async def chat_info(aid: int, cid: int):
    client = manager.client(aid)
    entity = await _full_entity(aid, cid)
    info = {"account_id": aid, "id": cid, "title": display_name(entity), "type": peer_type(entity),
            "username": username(entity), "about": "", "members": None,
            "is_creator": bool(getattr(entity, "creator", False)),
            "is_admin": bool(getattr(entity, "admin_rights", None)) or bool(getattr(entity, "creator", False)),
            "can_send": True, "phone": getattr(entity, "phone", None)}
    if isinstance(entity, types.User):
        full = await client(functions.users.GetFullUserRequest(entity))
        info["about"] = full.full_user.about or ""
        if entity.bot:
            info["about"] = info["about"] or getattr(full.full_user.bot_info, "description", None) or ""
            info["webapp"] = bot_webapp(entity, full.full_user)
    elif isinstance(entity, types.Channel):
        full = await client(functions.channels.GetFullChannelRequest(entity))
        info["about"] = full.full_chat.about or ""
        info["members"] = full.full_chat.participants_count
        info["joined"] = not entity.left
        if entity.broadcast and not info["is_admin"]:
            info["can_send"] = False
        if info["is_admin"]:
            info["settings"] = {
                "signatures": bool(entity.signatures), "noforwards": bool(entity.noforwards),
                "slowmode": full.full_chat.slowmode_seconds or 0,
                "hidden_prehistory": bool(full.full_chat.hidden_prehistory),
                "permissions": permissions_dict(entity.default_banned_rights),
            }
    elif isinstance(entity, types.Chat):
        full = await client(functions.messages.GetFullChatRequest(entity.id))
        info["about"] = full.full_chat.about or ""
        info["members"] = entity.participants_count
        info["joined"] = not entity.left
        info["legacy"] = True  # обычная группа: админы и медленный режим — только у супергрупп
        if info["is_admin"]:
            info["settings"] = {"noforwards": bool(entity.noforwards),
                                "permissions": permissions_dict(entity.default_banned_rights)}
    if info["is_admin"] and not isinstance(entity, types.User):
        invite = getattr(full.full_chat, "exported_invite", None)
        info["invite"] = getattr(invite, "link", None)
        info["my_rights"] = my_rights(entity)
    return info


class ChatSettingsIn(BaseModel):
    signatures: bool | None = None
    noforwards: bool | None = None
    slowmode: int | None = None
    hidden_prehistory: bool | None = None
    permissions: dict[str, bool] | None = None


@app.post("/api/accounts/{aid}/chats/{cid}/settings", dependencies=A)
async def chat_settings(aid: int, cid: int, body: ChatSettingsIn):
    client = manager.client(aid)
    entity = await _full_entity(aid, cid)
    channel = isinstance(entity, types.Channel)
    requests = []
    if body.signatures is not None and channel:
        requests.append(functions.channels.ToggleSignaturesRequest(entity, signatures_enabled=body.signatures))
    if body.noforwards is not None:
        requests.append(functions.messages.ToggleNoForwardsRequest(entity, body.noforwards))
    if body.slowmode is not None and channel:
        if body.slowmode not in SLOWMODE:
            raise HTTPException(400, "Недопустимый интервал медленного режима")
        requests.append(functions.channels.ToggleSlowModeRequest(entity, body.slowmode))
    if body.hidden_prehistory is not None and channel:
        requests.append(functions.channels.TogglePreHistoryHiddenRequest(entity, body.hidden_prehistory))
    if body.permissions is not None:
        requests.append(functions.messages.EditChatDefaultBannedRightsRequest(entity, banned_rights(body.permissions)))
    for request in requests:
        try:
            await client(request)
        except RPCError as e:
            if e.message != "CHAT_NOT_MODIFIED":
                raise
    return await chat_info(aid, cid)


async def _admin_channel(aid: int, cid: int) -> types.Channel:
    entity = await _full_entity(aid, cid)
    if not isinstance(entity, types.Channel):
        raise HTTPException(400, "Администраторы настраиваются только в каналах и супергруппах")
    return entity


@app.get("/api/accounts/{aid}/chats/{cid}/admins", dependencies=A)
async def chat_admins(aid: int, cid: int):
    client = manager.client(aid)
    channel = await _admin_channel(aid, cid)
    res = await client(functions.channels.GetParticipantsRequest(
        channel, types.ChannelParticipantsAdmins(), offset=0, limit=200, hash=0))
    users = {u.id: u for u in res.users}
    result = []
    for p in res.participants:
        if not isinstance(p, (types.ChannelParticipantAdmin, types.ChannelParticipantCreator)):
            continue
        u = users.get(p.user_id)
        creator = isinstance(p, types.ChannelParticipantCreator)
        result.append({"id": p.user_id, "name": display_name(u), "username": getattr(u, "username", None),
                       "bot": bool(getattr(u, "bot", False)), "self": bool(getattr(u, "is_self", False)),
                       "rank": p.rank or "", "creator": creator, "can_edit": bool(getattr(p, "can_edit", False)),
                       "rights": rights_dict(p.admin_rights)})
    result.sort(key=lambda a: (not a["creator"], a["name"].lower()))
    return result


async def _resolve_user(aid: int, raw: str):
    """@username, ссылка t.me/…, телефон контакта или числовой id → InputPeerUser."""
    s = raw.strip()
    if re.fullmatch(r"\d+", s):
        peer = await manager.entity(aid, int(s))
    else:
        name = re.sub(r"^(https?://)?(t\.me|telegram\.me)/", "", s).lstrip("@").split("/")[0]
        if not name:
            raise HTTPException(400, "Укажите пользователя")
        try:
            peer = await manager.client(aid).get_input_entity(name)
        except ValueError:
            raise HTTPException(400, f"Пользователь «{s}» не найден")
    if not isinstance(peer, (types.InputPeerUser, types.InputPeerSelf)):
        raise HTTPException(400, "Администратором можно назначить только пользователя или бота")
    return peer


class AdminIn(BaseModel):
    user: str               # @username, ссылка, телефон или id (при правке существующего админа)
    rights: dict[str, bool]
    rank: str = ""


@app.post("/api/accounts/{aid}/chats/{cid}/admins", dependencies=A)
async def set_admin(aid: int, cid: int, body: AdminIn):
    channel = await _admin_channel(aid, cid)
    rights = {k: True for k, v in body.rights.items() if v and k in ADMIN_RIGHTS and k != "other"}
    if not rights:
        raise HTTPException(400, "Отметьте хотя бы одно право")
    if my_rights(channel).get("other"):
        rights["other"] = True
    user = await _resolve_user(aid, body.user)
    await manager.client(aid)(functions.channels.EditAdminRequest(
        channel, user, types.ChatAdminRights(**rights), rank=body.rank.strip()[:16]))
    return await chat_admins(aid, cid)


@app.delete("/api/accounts/{aid}/chats/{cid}/admins/{uid}", dependencies=A)
async def remove_admin(aid: int, cid: int, uid: int):
    channel = await _admin_channel(aid, cid)
    await manager.client(aid)(functions.channels.EditAdminRequest(
        channel, await manager.entity(aid, uid), types.ChatAdminRights(), rank=""))
    return await chat_admins(aid, cid)


@app.delete("/api/accounts/{aid}/chats/{cid}", dependencies=A)
async def delete_chat(aid: int, cid: int):
    """Удалить канал или супергруппу целиком — только владелец."""
    channel = await _admin_channel(aid, cid)
    if not channel.creator:
        raise HTTPException(403, "Удалить может только владелец")
    await manager.client(aid)(functions.channels.DeleteChannelRequest(channel))
    return {"ok": True}


@app.get("/api/accounts/{aid}/chats/{cid}/messages", dependencies=A)
async def messages(aid: int, cid: int, offset_id: int = 0, limit: int = 40):
    client = manager.client(aid)
    entity = await manager.entity(aid, cid)
    msgs = await client.get_messages(entity, limit=min(limit, 100), offset_id=offset_id)
    return [message_dict(aid, m) for m in reversed(msgs) if not isinstance(m, types.MessageEmpty)]


class SendIn(BaseModel):
    text: str
    reply_to: int | None = None
    silent: bool = False
    no_preview: bool = False


@app.post("/api/accounts/{aid}/chats/{cid}/messages", dependencies=A)
async def send_message(aid: int, cid: int, body: SendIn):
    client = manager.client(aid)
    msg = await client.send_message(await manager.entity(aid, cid), body.text, reply_to=body.reply_to,
                                    silent=body.silent, link_preview=not body.no_preview)
    return message_dict(aid, msg)


@app.post("/api/accounts/{aid}/chats/{cid}/files", dependencies=A)
async def send_file(aid: int, cid: int, file: UploadFile = File(...), caption: str = Form(""),
                    reply_to: int | None = Form(None), as_document: bool = Form(False)):
    client = manager.client(aid)
    path = await _save_upload_tmp(file)
    try:
        msg = await client.send_file(await manager.entity(aid, cid), path, caption=caption,
                                     reply_to=reply_to, force_document=as_document)
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)
    return message_dict(aid, msg)


# ---------- красивые посты ----------

async def _post_target(aid: int, cid: int):
    entity = await _full_entity(aid, cid)
    if isinstance(entity, types.User) or not (getattr(entity, "creator", False) or getattr(entity, "admin_rights", None)):
        raise HTTPException(403, "Оформленные посты доступны администраторам каналов и групп")
    return entity


async def _bot_state(aid: int, entity, saved: dict | None) -> dict | None:
    if not saved:
        return None
    state = {"id": saved["bot_id"], "username": saved["username"], "admin": None}
    if isinstance(entity, types.Channel):
        try:
            bot = await manager.client(aid).get_input_entity(saved["username"] or saved["bot_id"])
            state["admin"] = await poster.bot_admin(manager.client(aid), entity, bot)
        except (ValueError, RPCError):
            state["admin"] = False
    return state


@app.get("/api/accounts/{aid}/chats/{cid}/post", dependencies=A)
async def post_info(aid: int, cid: int):
    entity = await _post_target(aid, cid)
    return {"bot": await _bot_state(aid, entity, storage.get_post_bot(aid, cid)),
            "buttons_supported": isinstance(entity, types.Channel),
            "can_promote": bool(my_rights(entity).get("add_admins"))}


class PostBotIn(BaseModel):
    token: str


@app.post("/api/accounts/{aid}/chats/{cid}/post/bot", dependencies=A)
async def set_post_bot(aid: int, cid: int, body: PostBotIn):
    """Подключить бота к каналу: проверить токен и, если можем, сразу назначить его администратором."""
    entity = await _post_target(aid, cid)
    if not isinstance(entity, types.Channel):
        raise HTTPException(400, "Кнопки под постами работают только в каналах и супергруппах")
    token = body.token.strip()
    if not token and storage.get_post_bot(aid, cid):   # пустой токен — повторить с сохранённым (назначить админом)
        token = storage.get_post_bot(aid, cid)["token"]
    if not poster.TOKEN_RE.match(token):
        raise HTTPException(400, "Это не похоже на токен бота. Он выглядит так: 123456789:AAH…, его выдаёт @BotFather")
    account = manager.get(aid).account
    bot = await poster.bot_client(token, "", account.api, parse_proxy(account.proxy))
    me = await bot.get_me()
    storage.set_post_bot(aid, cid, me.id, me.username or "", token, bot.session.save())
    client = manager.client(aid)
    bot_peer = await client.get_input_entity(me.username)
    if not await poster.bot_admin(client, entity, bot_peer):
        if not my_rights(entity).get("add_admins"):
            raise HTTPException(400, f"Бот @{me.username} подключён, но не администратор. У аккаунта нет права "
                                     "назначать админов — добавьте бота с правом публикации вручную")
        await poster.promote_bot(client, entity, bot_peer)
    return await post_info(aid, cid)


@app.delete("/api/accounts/{aid}/chats/{cid}/post/bot", dependencies=A)
async def delete_post_bot(aid: int, cid: int):
    saved = storage.get_post_bot(aid, cid)
    storage.delete_post_bot(aid, cid)
    if saved:   # если тот же бот подключён к другому каналу, он переподключится там по своей сессии
        await poster.drop_bot(saved["token"])
    return {"ok": True}


class PostIn(BaseModel):
    text: str = ""
    entities: list[dict] = []
    buttons: list[list[dict]] = []
    silent: bool = False
    no_preview: bool = False
    invert: bool = False         # текст над медиа / над превью ссылки
    spoiler: bool = False        # фото или видео под спойлером
    schedule: float | None = None


@app.post("/api/accounts/{aid}/chats/{cid}/post", dependencies=A)
async def send_post(aid: int, cid: int, data: str = Form(...), file: UploadFile | None = File(None)):
    """Пост с форматированием, медиа и цветными кнопками. С кнопками публикует бот канала, без — сам аккаунт."""
    body = PostIn.model_validate_json(data)
    entity = await _post_target(aid, cid)
    text = body.text.strip()
    if not text and file is None:
        raise HTTPException(400, "Пост пустой: добавьте текст или медиа")
    if len(text.encode("utf-16-le")) // 2 > poster.TEXT_LIMIT:
        raise HTTPException(400, f"Текст длиннее {poster.TEXT_LIMIT} символов")
    ents = poster.entities(body.entities)
    reply_markup = poster.markup(body.buttons)
    schedule = None
    if body.schedule:
        if body.schedule < time.time() + 30:
            raise HTTPException(400, "Время публикации уже прошло")
        schedule = datetime.fromtimestamp(body.schedule, timezone.utc)
    client = manager.client(aid)
    sender, peer = client, await manager.entity(aid, cid)
    if reply_markup is not None:
        saved = storage.get_post_bot(aid, cid)
        if not saved:
            raise HTTPException(400, "Кнопки публикует бот канала — подключите его в разделе «Кнопки»")
        if schedule:
            raise HTTPException(400, "Пост с кнопками нельзя отложить: его публикует бот, а боты не умеют отложенную отправку")
        if file is not None and len(text.encode("utf-16-le")) // 2 > poster.CAPTION_LIMIT:
            raise HTTPException(400, f"Подпись к медиа у поста с кнопками — до {poster.CAPTION_LIMIT} символов")
        account = manager.get(aid).account
        sender = await poster.bot_client(saved["token"], saved["session"], account.api, parse_proxy(account.proxy))
        try:
            peer = await sender.get_input_entity(cid)
        except (ValueError, RPCError):
            raise HTTPException(400, f"Бот @{saved['username']} не видит канал — проверьте, что он администратор")
    path = await _save_upload_tmp(file) if file is not None else None
    try:
        msg = await poster.send(sender, peer, text, ents, path=path, reply_markup=reply_markup, silent=body.silent,
                                no_preview=body.no_preview, invert=body.invert, spoiler=body.spoiler, schedule=schedule)
    finally:
        if path:
            shutil.rmtree(path.parent, ignore_errors=True)
    if schedule:
        return {"scheduled": True}
    if sender is not client:
        # пост бота перечитываем глазами аккаунта: так он выглядит в ленте одинаково с остальными
        msg = await client.get_messages(entity, ids=msg.id) or msg
    return message_dict(aid, msg)


class EditIn(BaseModel):
    text: str


@app.patch("/api/accounts/{aid}/chats/{cid}/messages/{mid}", dependencies=A)
async def edit_message(aid: int, cid: int, mid: int, body: EditIn):
    client = manager.client(aid)
    msg = await client.edit_message(await manager.entity(aid, cid), mid, body.text)
    return message_dict(aid, msg)


@app.delete("/api/accounts/{aid}/chats/{cid}/messages/{mid}", dependencies=A)
async def delete_message(aid: int, cid: int, mid: int, revoke: bool = True):
    client = manager.client(aid)
    await client.delete_messages(await manager.entity(aid, cid), [mid], revoke=revoke)
    return {"ok": True}


@app.post("/api/accounts/{aid}/chats/{cid}/messages/{mid}/pin", dependencies=A)
async def pin_message(aid: int, cid: int, mid: int, unpin: bool = False):
    client = manager.client(aid)
    entity = await manager.entity(aid, cid)
    if unpin:
        await client.unpin_message(entity, mid)
    else:
        await client.pin_message(entity, mid, notify=False)
    return {"ok": True}


class ForwardIn(BaseModel):
    to_chat_id: int


@app.post("/api/accounts/{aid}/chats/{cid}/messages/{mid}/forward", dependencies=A)
async def forward_message(aid: int, cid: int, mid: int, body: ForwardIn):
    client = manager.client(aid)
    msg = await client.forward_messages(await manager.entity(aid, body.to_chat_id), mid,
                                        await manager.entity(aid, cid))
    return message_dict(aid, msg)


class ClickIn(BaseModel):
    row: int
    col: int


@app.post("/api/accounts/{aid}/chats/{cid}/messages/{mid}/click", dependencies=A)
async def click_button(aid: int, cid: int, mid: int, body: ClickIn):
    """Нажатие inline-кнопки бота. Ссылки открывает браузер сам, сюда приходят только callback и игры."""
    client = manager.client(aid)
    entity = await manager.entity(aid, cid)
    msg = await client.get_messages(entity, ids=mid)
    if msg is None or not isinstance(msg.reply_markup, types.ReplyInlineMarkup):
        raise HTTPException(404, "У сообщения больше нет кнопок")
    try:
        button = msg.reply_markup.rows[body.row].buttons[body.col]
    except IndexError:
        raise HTTPException(404, "Кнопка не найдена — возможно, бот обновил сообщение")
    kind = button.type
    if isinstance(kind, types.InlineButtonTypeCallback):
        if kind.requires_password:
            raise HTTPException(400, "Эта кнопка требует облачный пароль — пока не поддерживается")
        request = functions.messages.GetBotCallbackAnswerRequest(peer=entity, msg_id=mid, data=kind.data)
    elif isinstance(kind, types.InlineButtonTypeGame):
        request = functions.messages.GetBotCallbackAnswerRequest(peer=entity, msg_id=mid, game=True)
    elif isinstance(kind, types.InlineButtonTypeWebView):
        # Мини-приложение открывает интерфейс (POST /webapp); бот — тот, кто прислал сообщение
        bot = msg.via_bot_id or msg.sender_id
        if not bot or bot < 0:
            return {"message": "", "alert": False, "url": kind.url}
        return {"message": "", "alert": False, "url": "",
                "webapp": {"bot": str(bot), "mode": "button", "url": kind.url}}
    else:
        raise HTTPException(400, "Эта кнопка не нажимается из панели")
    try:
        res = await client(request)
    except BotResponseTimeoutError:
        return {"message": "Бот не ответил вовремя", "alert": False, "url": ""}
    return {"message": res.message or "", "alert": bool(res.alert), "url": res.url or ""}


@app.post("/api/accounts/{aid}/chats/{cid}/read", dependencies=A)
async def mark_read(aid: int, cid: int):
    await manager.read_chat(aid, await manager.entity(aid, cid))
    return {"ok": True}


@app.post("/api/accounts/{aid}/read_all", dependencies=A)
async def read_all(aid: int):
    """«Прочитать все»: все диалоги аккаунта, включая архив и упоминания."""
    client = manager.client(aid)
    count = 0
    async for d in client.iter_dialogs():
        marked = bool(getattr(d.dialog, "unread_mark", False))
        if not (d.unread_count or d.unread_mentions_count or marked):
            continue
        try:
            if d.unread_count or d.unread_mentions_count:
                await client.send_read_acknowledge(d.input_entity, max_id=d.dialog.top_message,
                                                   clear_mentions=bool(d.unread_mentions_count))
            if marked:
                await client(functions.messages.MarkDialogUnreadRequest(
                    peer=types.InputDialogPeer(d.input_entity), unread=False))
            count += 1
        except RPCError as e:
            log.warning("Прочитать все, аккаунт %s, чат %s: %s", aid, d.id, e)
    return {"ok": True, "count": count}


@app.get("/api/accounts/{aid}/chats/{cid}/messages/{mid}/media", dependencies=A)
async def message_media(aid: int, cid: int, mid: int, thumb: bool = False):
    prefix = f"m_{aid}_{cid}_{mid}{'_t' if thumb else ''}"
    cached = next(CACHE_DIR.glob(prefix + ".*"), None) or next(CACHE_DIR.glob(prefix), None)
    if cached is None:
        client = manager.client(aid)
        msg = await client.get_messages(await manager.entity(aid, cid), ids=mid)
        if msg is None or msg.media is None:
            raise HTTPException(404, "Медиа не найдено")
        path = await client.download_media(msg, file=str(CACHE_DIR / prefix), thumb=-1 if thumb else None)
        if not path:
            raise HTTPException(404, "Медиа не найдено")
        cached = Path(path)
    return FileResponse(cached, headers={"Cache-Control": "private, max-age=86400"})


AVATAR_TTL = 24 * 3600


def _fresh(path: Path) -> bool:
    return path.exists() and time.time() - path.stat().st_mtime < AVATAR_TTL


@app.get("/api/accounts/{aid}/avatar/{peer}", dependencies=A)
async def avatar(aid: int, peer: str):
    if peer != "me" and not re.fullmatch(r"-?\d+", peer):
        raise HTTPException(400, "Неверный id")
    path = CACHE_DIR / f"a_{aid}_{peer}.jpg"
    missing = CACHE_DIR / f"a_{aid}_{peer}.none"
    if not _fresh(path):
        if _fresh(missing):
            raise HTTPException(404, "Нет фото")
        # Не больше нескольких загрузок на аккаунт одновременно, чтобы не ловить flood wait
        async with manager.media_slot(aid):
            if not _fresh(path):
                client = manager.client(aid)
                entity = "me" if peer == "me" else await manager.entity(aid, int(peer))
                got = await client.download_profile_photo(entity, file=str(path), download_big=False)
                if not got:
                    path.unlink(missing_ok=True)
                    missing.touch()
                    raise HTTPException(404, "Нет фото")
                missing.unlink(missing_ok=True)
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


# ---------- поиск, вступление, каналы ----------

@app.get("/api/accounts/{aid}/search", dependencies=A)
async def search(aid: int, q: str):
    client = manager.client(aid)
    q = q.strip()
    found: dict[int, dict] = {}

    def add(entity):
        pid = manager.peer_id(entity)
        found[pid] = {"id": pid, "title": display_name(entity), "type": peer_type(entity),
                      "username": username(entity)}

    if len(q) >= 2:
        res = await client(functions.contacts.SearchRequest(q=q.lstrip("@"), limit=20))
        for e in [*res.users, *res.chats]:
            add(e)
    if re.fullmatch(r"\+?\d{7,15}", q):
        try:
            add(await client.get_entity(q if q.startswith("+") else f"+{q}"))
        except (ValueError, RPCError):
            pass
    return list(found.values())


class JoinIn(BaseModel):
    link: str = ""
    chat_id: int | None = None   # публичный канал, уже найденный по ссылке (у него может не быть @имени)


@app.post("/api/accounts/{aid}/join", dependencies=A)
async def join(aid: int, body: JoinIn):
    client = manager.client(aid)
    if body.chat_id:
        entity = await client.get_entity(await manager.entity(aid, body.chat_id))
        if isinstance(entity, types.Channel):
            await client(functions.channels.JoinChannelRequest(entity))
        return {"id": manager.peer_id(entity), "title": display_name(entity), "type": peer_type(entity)}
    link = body.link.strip()
    m = re.search(r"(?:t\.me|telegram\.me)/(?:\+|joinchat/)([\w-]+)", link)
    if m:
        res = await client(functions.messages.ImportChatInviteRequest(m.group(1)))
        chat = res.chats[0]
    else:
        username = re.sub(r"^(https?://)?(t\.me|telegram\.me)/", "", link).lstrip("@").split("/")[0]
        entity = await client.get_entity(username)
        if isinstance(entity, types.Channel):
            await client(functions.channels.JoinChannelRequest(entity))
        chat = entity
    return {"id": manager.peer_id(chat), "title": display_name(chat), "type": peer_type(chat)}


class ChannelIn(BaseModel):
    title: str
    about: str = ""
    kind: str = "channel"   # channel | group
    username: str = ""


@app.post("/api/accounts/{aid}/channels", dependencies=A)
async def create_channel(aid: int, body: ChannelIn):
    client = manager.client(aid)
    res = await client(functions.channels.CreateChannelRequest(
        title=body.title, about=body.about, broadcast=body.kind == "channel",
        megagroup=body.kind == "group"))
    channel = res.chats[0]
    warning = ""
    if body.username.strip():
        try:
            await client(functions.channels.UpdateUsernameRequest(channel, body.username.strip().lstrip("@")))
        except RPCError as e:
            warning = f"Канал создан, но ссылку занять не удалось: {e.message}"
    return {"id": manager.peer_id(channel), "title": channel.title, "type": peer_type(channel),
            "warning": warning}


class ChatEditIn(BaseModel):
    title: str | None = None
    about: str | None = None
    username: str | None = None


@app.post("/api/accounts/{aid}/chats/{cid}/edit", dependencies=A)
async def edit_chat(aid: int, cid: int, body: ChatEditIn):
    client = manager.client(aid)
    entity = await client.get_entity(await manager.entity(aid, cid))
    if body.title and body.title != display_name(entity):
        if isinstance(entity, types.Channel):
            await client(functions.channels.EditTitleRequest(entity, body.title))
        else:
            await client(functions.messages.EditChatTitleRequest(entity.id, body.title))
    if body.about is not None:
        await client(functions.messages.EditChatAboutRequest(entity, body.about))
    if body.username is not None and isinstance(entity, types.Channel) \
            and body.username.lstrip("@") != (entity.username or ""):
        await client(functions.channels.UpdateUsernameRequest(entity, body.username.lstrip("@")))
    return await chat_info(aid, cid)


@app.post("/api/accounts/{aid}/chats/{cid}/photo", dependencies=A)
async def edit_chat_photo(aid: int, cid: int, file: UploadFile = File(...)):
    client = manager.client(aid)
    entity = await client.get_entity(await manager.entity(aid, cid))
    path = await _save_upload_tmp(file)
    try:
        photo = types.InputChatUploadedPhoto(file=await client.upload_file(path))
        if isinstance(entity, types.Channel):
            await client(functions.channels.EditPhotoRequest(entity, photo))
        else:
            await client(functions.messages.EditChatPhotoRequest(entity.id, photo))
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)
    for f in CACHE_DIR.glob(f"a_{aid}_{cid}.*"):
        f.unlink(missing_ok=True)
    return {"ok": True}


@app.post("/api/accounts/{aid}/chats/{cid}/invite", dependencies=A)
async def invite_link(aid: int, cid: int):
    client = manager.client(aid)
    res = await client(functions.messages.ExportChatInviteRequest(await manager.entity(aid, cid)))
    return {"link": res.link}


@app.post("/api/accounts/{aid}/chats/{cid}/leave", dependencies=A)
async def leave_chat(aid: int, cid: int):
    client = manager.client(aid)
    await client.delete_dialog(await manager.entity(aid, cid))
    return {"ok": True}


# ---------- ссылки t.me и мини-приложения ----------

TG_HOSTS = {"t.me", "telegram.me", "telegram.dog"}
# служебные пути t.me, которые не являются именем канала или бота
TG_RESERVED = {"addstickers", "addemoji", "addtheme", "addlist", "setlanguage", "share", "proxy", "socks", "login",
               "confirmphone", "iv", "bg", "invoice", "boost", "contact", "giftcode", "nft", "m", "stars", "premium"}
WEBAPP_PLATFORM = "weba"   # как у Telegram Web: приложения рассчитаны на работу во фрейме


def parse_tg_link(link: str) -> dict:
    """t.me/… и tg://… → что открыть: username (+ post, app, start, startapp), invite или channel_id."""
    u = urlparse(link if "://" in link else f"https://{link}")
    q = parse_qs(u.query, keep_blank_values=True)
    one = lambda k: q[k][0] if k in q else None
    if u.scheme == "tg":
        if u.netloc == "join" and one("invite"):
            return {"invite": one("invite")}
        if u.netloc == "resolve" and one("domain"):
            post = one("post")
            return {"username": one("domain"), "post": int(post) if post and post.isdigit() else None,
                    "app": one("appname"), "start": one("start"), "startapp": one("startapp")}
        return {}
    if (u.hostname or "").lower().removeprefix("www.") not in TG_HOSTS:
        return {}
    parts = [p for p in u.path.split("/") if p]
    if parts[:1] == ["s"]:   # t.me/s/name — веб-превью канала
        parts = parts[1:]
    if not parts:
        return {}
    head = parts[0]
    if head.startswith("+") and not head[1:].isdigit():
        return {"invite": head[1:]}
    if head == "joinchat" and len(parts) > 1:
        return {"invite": parts[1]}
    if head == "c" and len(parts) > 1 and parts[1].isdigit():
        return {"channel_id": int(parts[1]), "post": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None}
    if head.lower() in TG_RESERVED or not re.fullmatch(r"[A-Za-z]\w{3,31}", head):
        return {}
    result = {"username": head, "post": None, "app": None, "start": one("start"), "startapp": one("startapp")}
    if len(parts) > 1:
        if parts[1].isdigit():
            result["post"] = int(parts[1])
        elif re.fullmatch(r"\w+", parts[1]):
            result["app"] = parts[1]
    return result


def bot_webapp(user, full_user) -> dict | None:
    """Кнопка-приложение бота: меню бота с адресом или «главное» мини-приложение."""
    menu = getattr(getattr(full_user, "bot_info", None), "menu_button", None)
    if isinstance(menu, types.BotMenuButton):
        return {"mode": "menu", "text": menu.text, "url": menu.url}
    if getattr(user, "bot_has_main_app", False):
        return {"mode": "main", "text": "Приложение", "url": ""}
    return None


async def _peer_card(aid: int, entity) -> dict:
    """Карточка для предпросмотра по ссылке: можно посмотреть, не вступая."""
    client = manager.client(aid)
    card = {"kind": "chat", "id": manager.peer_id(entity), "title": display_name(entity), "type": peer_type(entity),
            "username": username(entity), "verified": bool(getattr(entity, "verified", False)),
            "about": "", "members": None, "joined": True, "webapp": None}
    if isinstance(entity, types.Channel):
        card["joined"] = not entity.left
        try:
            full = await client(functions.channels.GetFullChannelRequest(entity))
            card["about"], card["members"] = full.full_chat.about or "", full.full_chat.participants_count
        except RPCError:
            card["members"] = getattr(entity, "participants_count", None)
    elif isinstance(entity, types.Chat):
        card["joined"], card["members"] = not entity.left, entity.participants_count
    elif isinstance(entity, types.User):
        full = await client(functions.users.GetFullUserRequest(entity))
        card["about"] = full.full_user.about or ""
        if entity.bot:
            card["about"] = card["about"] or getattr(full.full_user.bot_info, "description", None) or ""
            card["webapp"] = bot_webapp(entity, full.full_user)
    return card


@app.get("/api/accounts/{aid}/resolve", dependencies=A)
async def resolve_link(aid: int, link: str):
    """Ссылка на канал, группу, бота или приглашение → карточка для предпросмотра в панели."""
    client = manager.client(aid)
    p = parse_tg_link(link.strip())
    if "invite" in p:
        res = await client(functions.messages.CheckChatInviteRequest(p["invite"]))
        if isinstance(res, types.ChatInviteAlready):
            return await _peer_card(aid, res.chat)
        if isinstance(res, types.ChatInvitePeek):
            return {**await _peer_card(aid, res.chat), "joined": False, "invite": link}
        return {"kind": "invite", "id": None, "title": res.title, "type": "channel" if res.broadcast else "group",
                "username": None, "verified": bool(res.verified), "about": res.about or "",
                "members": res.participants_count, "joined": False, "request_needed": bool(res.request_needed),
                "invite": link, "webapp": None}
    if "channel_id" in p:
        try:
            entity = await client.get_entity(await manager.entity(aid, int(f"-100{p['channel_id']}")))
        except ValueError:
            raise HTTPException(404, "Аккаунт не состоит в этом закрытом канале")
        return {**await _peer_card(aid, entity), "post": p["post"]}
    if "username" in p:
        try:
            entity = await client.get_entity(p["username"])
        except ValueError:
            raise HTTPException(404, f"@{p['username']} не найден")
        card = await _peer_card(aid, entity)
        return {**card, "post": p["post"], "app": p["app"], "start": p["start"], "startapp": p["startapp"]}
    return {"kind": "external"}


class WebAppIn(BaseModel):
    bot: str                       # id или @username бота
    mode: str = "main"             # button — кнопка под сообщением, menu — меню бота, main — главное, app — t.me/bot/app
    chat_id: int | None = None     # чат, из которого открыто (по умолчанию — чат с ботом)
    url: str = ""
    app: str = ""
    start_param: str = ""
    theme: dict[str, str] | None = None


@app.post("/api/accounts/{aid}/webapp", dependencies=A)
async def open_webapp(aid: int, body: WebAppIn):
    """Адрес мини-приложения с подписанными данными пользователя (initData) — его открывает фрейм панели."""
    client = manager.client(aid)
    bot = await _resolve_user(aid, body.bot)
    peer = await manager.entity(aid, body.chat_id) if body.chat_id else bot
    theme = types.DataJSON(json.dumps(body.theme)) if body.theme else None
    start = body.start_param or None
    if body.mode == "app":
        res = await client(functions.messages.RequestAppWebViewRequest(
            peer=peer, app=types.InputBotAppShortName(bot, body.app), platform=WEBAPP_PLATFORM,
            start_param=start, theme_params=theme))
    elif body.mode == "main":
        res = await client(functions.messages.RequestMainWebViewRequest(
            peer=peer, bot=bot, platform=WEBAPP_PLATFORM, start_param=start, theme_params=theme))
    elif body.mode in ("button", "menu"):
        res = await client(functions.messages.RequestWebViewRequest(
            peer=peer, bot=bot, platform=WEBAPP_PLATFORM, url=body.url or None, start_param=start,
            from_bot_menu=body.mode == "menu", theme_params=theme))
    else:
        raise HTTPException(400, "Неизвестный способ открытия")
    entity = await client.get_entity(bot)
    return {"url": res.url, "query_id": str(res.query_id) if getattr(res, "query_id", None) else None,
            "bot_id": manager.peer_id(entity), "title": display_name(entity)}


class ProlongIn(BaseModel):
    bot: str
    query_id: str
    chat_id: int | None = None


@app.post("/api/accounts/{aid}/webapp/prolong", dependencies=A)
async def prolong_webapp(aid: int, body: ProlongIn):
    """Пока приложение открыто, Telegram ждёт отметку раз в минуту, иначе ответ бота не дойдёт."""
    bot = await _resolve_user(aid, body.bot)
    peer = await manager.entity(aid, body.chat_id) if body.chat_id else bot
    await manager.client(aid)(functions.messages.ProlongWebViewRequest(peer=peer, bot=bot, query_id=int(body.query_id)))
    return {"ok": True}


# ---------- встроенные боты (app/bots.py) ----------

@app.get("/api/bots", dependencies=A)
async def bots_list():
    return [bot.public() for bot in bots.bots.values()]


class BotSetupIn(BaseModel):
    token: str | None = None  # None — оставить прежний
    admin_ids: list[int] = []
    timezone: str = "Europe/Moscow"


@app.put("/api/bots/{name}", dependencies=A)
async def bot_setup(name: str, body: BotSetupIn, request: Request):
    """Настройка для запуска: токен (проверяется у Telegram), администраторы, часовой пояс. Сохраняет и
    (пере)запускает бота. Остальное — в собственной панели бота."""
    bot = bots.get(name)
    changes: dict = {"admin_ids": sorted(set(i for i in body.admin_ids if i > 0)), "enabled": True}
    # адрес панели бота, как его видит браузер, — бот показывает его в Telegram («Веб-панель: …»)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
        changes["public_url"] = f"{scheme}://{host}{WEB_PREFIX}/bots/{name}/"
    if body.timezone.strip():
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(body.timezone.strip())
        except (ValueError, KeyError):
            raise ValueError(f"Неизвестный часовой пояс «{body.timezone}» (пример: Europe/Moscow)")
        changes["timezone"] = body.timezone.strip()
    if body.token is not None and body.token.strip():
        token = body.token.strip()
        other = next((b for b in bots.bots.values() if b is not bot and b.cfg.get("token") == token), None)
        if other:
            raise ValueError(f"Этот токен уже у бота «{other.kind.title}» — одному боту нельзя работать в двух местах")
        me = await bots.check_token(token)
        changes.update(token=token, username=me.get("username", ""), bot_name=me.get("first_name", ""))
    elif not bot.configured:
        raise ValueError("Укажите токен бота от @BotFather")
    bots.in_background(bot.reconfigure(changes))
    return {**bot.public(), **{k: v for k, v in changes.items() if k in ("admin_ids", "timezone", "username", "bot_name")},
            "configured": True, "enabled": True, "status": "starting", "error": ""}


@app.post("/api/bots/{name}/start", dependencies=A)
async def bot_start(name: str):
    bot = bots.get(name)
    if not bot.configured:
        raise ValueError("Сначала укажите токен бота")
    bot.save(enabled=True)
    await bot.start()
    return bot.public()


@app.post("/api/bots/{name}/stop", dependencies=A)
async def bot_stop(name: str):
    bot = bots.get(name)
    bot.save(enabled=False)
    bots.in_background(bot.stop())
    return {**bot.public(), "enabled": False, "status": "stopping"}


@app.get("/api/bots/{name}/log", dependencies=A)
async def bot_log(name: str):
    return {"lines": list(bots.get(name).tail)[-100:]}


_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
        "transfer-encoding", "upgrade", "host", "content-length"}
_proxy_session = None


async def close_bot_proxy() -> None:
    global _proxy_session
    if _proxy_session:
        await _proxy_session.close()
        _proxy_session = None


def _bot_page(title: str, text: str, status: int = 503) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta charset=utf-8><body style='font:15px system-ui;display:grid;place-items:center;"
        f"height:90vh;color:#888;text-align:center'><div><h3>{title}</h3><p>{text}</p></div>", status_code=status)


@app.api_route("/bots/{name}", methods=["GET", "HEAD"])
async def bot_root(name: str):
    return RedirectResponse(f"{WEB_PREFIX}/bots/{name}/")


@app.api_route("/bots/{name}/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
async def bot_proxy(name: str, path: str, request: Request):
    """Веб-панель бота через панель: тот же вход, тот же адрес — её можно открыть во фрейме."""
    global _proxy_session
    bot = bots.get(name)
    # вебхук оплаты xRocket приходит без входа в панель — подпись запроса проверяет сам бот
    hook = name == "ads" and path.startswith("hook/") and request.method == "POST"
    if not hook and not is_authed(request.cookies.get(COOKIE)):
        return _bot_page("Нужен вход", "Войдите в TG Panel и откройте бота снова.", 401)
    if bot.status != "running" or not bot.port:
        what = {"starting": "Бот запускается — подождите несколько секунд.",
                "error": "Бот не запустился. Откройте его настройки в TG Panel."}.get(bot.status, "Бот выключен.")
        return _bot_page(bot.kind.title, what)
    if _proxy_session is None:
        # auto_decompress=False: сжатый ответ уходит браузеру как есть, вместе с Content-Encoding
        _proxy_session = aiohttp.ClientSession(auto_decompress=False, timeout=aiohttp.ClientTimeout(
            total=None, sock_connect=5, sock_read=600))
    # путь как его прислал браузер, не раскодированный: %2F, %3F, %23 в имени файла остаются собой
    raw_path = request.scope.get("raw_path", b"").decode("latin-1") or request.url.path
    tail = raw_path.split("/bots/" + name + "/", 1)[-1]
    url = f"http://127.0.0.1:{bot.port}{bot.prefix}/{tail}"
    if request.url.query:
        url += "?" + request.url.query
    headers = [(k, v) for k, v in request.headers.items()
               if (k.lower() not in _HOP or k.lower() == "content-length") and k.lower() != "x-tg-panel-key"]
    headers.append(("X-TG-Panel-Key", bot.key))
    body = request.stream() if request.method in ("POST", "PUT", "PATCH", "DELETE") else None
    try:
        upstream = await _proxy_session.request(request.method, yarl.URL(url, encoded=True), headers=headers,
                                                data=body, allow_redirects=False)
    except aiohttp.ClientError:
        return _bot_page(bot.kind.title, "Бот не отвечает — возможно, он перезапускается. Обновите страницу.", 502)

    async def stream():
        try:
            async for chunk in upstream.content.iter_chunked(64 * 1024):
                yield chunk
        finally:
            upstream.release()

    origin = f"http://127.0.0.1:{bot.port}"
    try:
        raw = []
        for k, v in upstream.headers.items():
            if k.lower() in _HOP and k.lower() != "content-length":
                continue
            if k.lower() == "location" and v.startswith(origin):
                v = v[len(origin):]
            raw.append((k.lower().encode("latin-1"), v.encode("latin-1")))
        # release и после ответа: если браузер ушёл раньше, чем начался поток, соединение не повиснет
        response = StreamingResponse(stream(), status_code=upstream.status, background=BackgroundTask(upstream.release))
        response.raw_headers = raw
        return response
    except Exception:
        upstream.release()
        raise


# ---------- realtime ----------

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    if not is_authed(websocket.cookies.get(COOKIE)):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    manager.hub.sockets.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        manager.hub.sockets.discard(websocket)


class PanelStatic(StaticFiles):
    """Без Cache-Control браузер сам решает, сколько держать app.js, и после обновления показывает старый
    интерфейс (в программе — пустое окно). no-cache: каждый раз сверка по ETag, без изменений — короткий 304."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", PanelStatic(directory=BASE_DIR / "static", html=True), name="static")
