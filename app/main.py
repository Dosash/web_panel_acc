import asyncio
import logging
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel
from telethon import functions, types
from telethon.errors import RPCError

from . import storage
from .config import BASE_DIR, CACHE_DIR, COOKIE_SECRET, PANEL_PASSWORD, TMP_DIR
from .manager import Manager, dialog_dict, display_name, message_dict, parse_proxy, peer_type
from .tdata_import import ImportError_, convert, save_upload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("panel")

manager = Manager()
signer = URLSafeTimedSerializer(COOKIE_SECRET, salt="panel-login")
COOKIE = "panel_auth"
COOKIE_AGE = 30 * 24 * 3600


AUTH_ENABLED = bool(PANEL_PASSWORD)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not AUTH_ENABLED:
        log.warning("PANEL_PASSWORD пуст — панель открыта без пароля. Не выставляйте её в интернет.")
    storage.init_db()
    task = asyncio.create_task(manager.start_all())
    yield
    task.cancel()
    await manager.stop_all()


app = FastAPI(title="TG Panel", lifespan=lifespan)


# ---------- ошибки ----------

@app.exception_handler(RPCError)
async def rpc_error(_: Request, e: RPCError):
    return JSONResponse({"detail": f"Telegram: {e.message or type(e).__name__}"}, status_code=400)


@app.exception_handler(RuntimeError)
async def runtime_error(_: Request, e: RuntimeError):
    return JSONResponse({"detail": str(e)}, status_code=409)


@app.exception_handler(KeyError)
async def key_error(_: Request, e: KeyError):
    return JSONResponse({"detail": f"Аккаунт {e} не найден"}, status_code=404)


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
    if body.password != PANEL_PASSWORD:
        await asyncio.sleep(1.5)  # замедляем подбор пароля
        raise HTTPException(401, "Неверный пароль")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE, signer.dumps("admin"), max_age=COOKIE_AGE,
                    httponly=True, samesite="strict")
    return resp


@app.post("/api/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE)
    return resp


@app.get("/api/session", dependencies=[Depends(auth)])
async def session():
    return {"ok": True, "auth": AUTH_ENABLED}


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
    storage.delete_account(aid)
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
async def dialogs(account_id: int | None = None, archived: bool = False, limit: int = 100):
    ids = [account_id] if account_id else [i for i, l in manager.live.items() if l.status == "online"]

    async def load(aid: int):
        try:
            ds = await manager.client(aid).get_dialogs(limit=limit, archived=archived)
            return [dialog_dict(aid, d) for d in ds]
        except Exception as e:
            log.warning("Диалоги аккаунта %s: %s", aid, e)
            return []

    merged = [d for chunk in await asyncio.gather(*(load(i) for i in ids)) for d in chunk]
    merged.sort(key=lambda d: (not d["pinned"] if account_id else False, -d["date"]))
    return merged


@app.get("/api/accounts/{aid}/chats/{cid}", dependencies=A)
async def chat_info(aid: int, cid: int):
    client = manager.client(aid)
    entity = await client.get_entity(await manager.entity(aid, cid))
    info = {"account_id": aid, "id": cid, "title": display_name(entity), "type": peer_type(entity),
            "username": getattr(entity, "username", None), "about": "", "members": None,
            "is_creator": bool(getattr(entity, "creator", False)),
            "is_admin": bool(getattr(entity, "admin_rights", None)) or bool(getattr(entity, "creator", False)),
            "can_send": True, "phone": getattr(entity, "phone", None)}
    if isinstance(entity, types.User):
        full = await client(functions.users.GetFullUserRequest(entity))
        info["about"] = full.full_user.about or ""
    elif isinstance(entity, types.Channel):
        full = await client(functions.channels.GetFullChannelRequest(entity))
        info["about"] = full.full_chat.about or ""
        info["members"] = full.full_chat.participants_count
        if entity.broadcast and not info["is_admin"]:
            info["can_send"] = False
    elif isinstance(entity, types.Chat):
        full = await client(functions.messages.GetFullChatRequest(entity.id))
        info["about"] = full.full_chat.about or ""
        info["members"] = entity.participants_count
    return info


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


@app.post("/api/accounts/{aid}/chats/{cid}/read", dependencies=A)
async def mark_read(aid: int, cid: int):
    await manager.client(aid).send_read_acknowledge(await manager.entity(aid, cid))
    return {"ok": True}


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
                      "username": getattr(entity, "username", None)}

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
    link: str


@app.post("/api/accounts/{aid}/join", dependencies=A)
async def join(aid: int, body: JoinIn):
    client = manager.client(aid)
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


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
