"""Импорт аккаунта из файлов сессии: .session (Telethon или Pyrogram, SQLite), строковые сессии
и .json с параметрами приложения (api_id, устройство, 2FA, прокси) — распространённый формат «session + json»."""
import base64
import io
import json
import re
import sqlite3
import struct
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from opentele.api import API, APIData
from opentele.tl import TelegramClient
from telethon.crypto import AuthKey
from telethon.sessions import StringSession

from .config import TMP_DIR
from .tdata_import import ImportError_, _reraise_fatal, _safe_rel, me_dict

# Адреса дата-центров: в сессиях Pyrogram хранится только номер DC
_DC = {1: "149.154.175.53", 2: "149.154.167.51", 3: "149.154.175.100", 4: "149.154.167.91", 5: "91.108.56.130"}
_SQLITE_MAGIC = b"SQLite format 3\x00"
_MAX_FILE = 5 * 1024 * 1024
# В одной «пачке» часто лежат обе сессии одного аккаунта: 123_telethon.session и 123_pyrogram.session
_SUFFIX = re.compile(r"[_\-. ]?(telethon|pyrogram|tele|pyro|tl)$", re.I)
_TDESKTOP_API_ID = 2040


@dataclass
class SessionFile:
    name: str
    dc_id: int
    auth_key: bytes
    address: str
    port: int = 443
    user_id: int | None = None


@dataclass
class Meta:
    """Что удалось вытащить из .json. Любое поле может быть пустым."""
    api: dict | None = None
    password_2fa: str = ""
    proxy: str = ""
    label: str = ""


@dataclass
class Bundle:
    session: SessionFile
    meta: Meta = field(default_factory=Meta)
    key: str = ""


# ---------- .session ----------

def _b64(s: str) -> bytes:
    s = s.strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _read_sqlite(name: str, data: bytes) -> SessionFile:
    path = TMP_DIR / f"{uuid.uuid4().hex}.session"
    path.write_bytes(data)
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(sessions)")]
            if not cols:
                raise ImportError_(f"{name}: в файле нет таблицы sessions — это не файл сессии Telethon/Pyrogram.")
            row = conn.execute("SELECT * FROM sessions LIMIT 1").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        raise ImportError_(f"{name}: файл сессии повреждён ({e}).") from e
    finally:
        path.unlink(missing_ok=True)
    if row is None:
        raise ImportError_(f"{name}: файл сессии пуст (в нём нет авторизации).")
    rec = dict(zip(cols, row))
    if "server_address" in rec:                      # Telethon
        return _make(name, rec["dc_id"], rec["auth_key"], rec.get("server_address"), rec.get("port"))
    if "auth_key" in rec and "dc_id" in rec:         # Pyrogram
        if rec.get("test_mode"):
            raise ImportError_(f"{name}: сессия для тестовых серверов Telegram, панель с ними не работает.")
        if rec.get("is_bot"):
            raise ImportError_(f"{name}: это сессия бота, а не пользователя.")
        return _make(name, rec["dc_id"], rec["auth_key"], user_id=rec.get("user_id"))
    raise ImportError_(f"{name}: незнакомая структура файла сессии.")


def _read_string(name: str, text: str) -> SessionFile:
    text = text.strip()
    if text.startswith("1") and len(text) > 300:    # Telethon StringSession
        try:
            s = StringSession(text)
        except Exception as e:
            raise ImportError_(f"{name}: строковая сессия Telethon не читается ({e}).") from e
        if not s.auth_key:
            raise ImportError_(f"{name}: в строковой сессии нет ключа авторизации.")
        return _make(name, s.dc_id, s.auth_key.key, s.server_address, s.port)
    try:
        raw = _b64(text)
    except Exception as e:
        raise ImportError_(f"{name}: это не файл сессии и не строковая сессия.") from e
    # Pyrogram: >B?256sI? (263) · >B?256sQ? (267) · >BI?256sQ? (271)
    layouts = {263: ">B?256sI?", 267: ">B?256sQ?", 271: ">BI?256sQ?"}
    fmt = layouts.get(len(raw))
    if not fmt:
        raise ImportError_(f"{name}: это не файл сессии и не строковая сессия.")
    parts = struct.unpack(fmt, raw)
    dc_id, test_mode, auth_key, user_id, is_bot = (parts if len(parts) == 5 else (parts[0], *parts[2:]))
    if test_mode:
        raise ImportError_(f"{name}: сессия для тестовых серверов Telegram, панель с ними не работает.")
    if is_bot:
        raise ImportError_(f"{name}: это сессия бота, а не пользователя.")
    return _make(name, dc_id, auth_key, user_id=user_id)


def _make(name: str, dc_id, auth_key, address=None, port=None, user_id=None) -> SessionFile:
    if not isinstance(auth_key, (bytes, bytearray)) or len(auth_key) != 256:
        raise ImportError_(f"{name}: ключ авторизации в сессии отсутствует или повреждён.")
    try:
        dc_id = int(dc_id)
    except (TypeError, ValueError):
        raise ImportError_(f"{name}: в сессии не указан дата-центр.")
    if not address:
        address = _DC.get(dc_id)
    if not address:
        raise ImportError_(f"{name}: неизвестный дата-центр {dc_id}.")
    return SessionFile(name, dc_id, bytes(auth_key), address, int(port or 443), user_id)


def looks_like_session(name: str, data: bytes) -> bool:
    if data.startswith(_SQLITE_MAGIC):
        return True
    if name.lower().endswith(".session"):
        return True
    if len(data) < 500 and not name.lower().endswith((".json", ".txt")):
        return re.fullmatch(rb"\s*[A-Za-z0-9_\-=]{300,}\s*", data) is not None
    return False


def parse_session(name: str, data: bytes) -> SessionFile:
    if data.startswith(_SQLITE_MAGIC):
        return _read_sqlite(name, data)
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        raise ImportError_(f"{name}: это не файл сессии Telethon/Pyrogram.")
    return _read_string(name, text)


# ---------- .json ----------

def _pick(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", 0):
            return v
    return None


def _proxy_str(p) -> str:
    """Прокси из .json: строка, список [тип, хост, порт, rdns, логин, пароль] или словарь."""
    if isinstance(p, str):
        return p.strip()
    if isinstance(p, (list, tuple)) and len(p) >= 3:
        scheme, host, port = str(p[0]).lower(), p[1], p[2]
        if isinstance(scheme, str) and not scheme.startswith(("socks", "http")):
            return ""
        user = p[4] if len(p) > 4 else None
        pwd = p[5] if len(p) > 5 else None
        auth = f"{user}:{pwd}@" if user else ""
        return f"{scheme}://{auth}{host}:{port}"
    if isinstance(p, dict):
        scheme = str(_pick(p, "scheme", "proxy_type", "type") or "socks5").lower()
        host, port = _pick(p, "hostname", "addr", "host", "ip"), _pick(p, "port")
        if not host or not port:
            return ""
        user, pwd = _pick(p, "username", "user", "login"), _pick(p, "password", "pass")
        auth = f"{user}:{pwd}@" if user else ""
        return f"{scheme}://{auth}{host}:{port}"
    return ""


def default_api() -> dict:
    return api_dict(API.TelegramDesktop.Generate(system="windows", unique_id=uuid.uuid4().hex))


def api_dict(api: APIData) -> dict:
    return {
        "api_id": api.api_id, "api_hash": api.api_hash,
        "device_model": api.device_model, "system_version": api.system_version,
        "app_version": api.app_version, "lang_code": api.lang_code,
        "system_lang_code": api.system_lang_code, "lang_pack": api.lang_pack,
    }


def parse_json(name: str, data: bytes) -> Meta:
    try:
        j = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as e:
        raise ImportError_(f"{name}: не удалось прочитать json ({e}).") from e
    if not isinstance(j, dict):
        raise ImportError_(f"{name}: в json ожидался объект с параметрами аккаунта.")
    meta = Meta()
    api_id, api_hash = _pick(j, "app_id", "api_id"), _pick(j, "app_hash", "api_hash")
    if api_id and api_hash:
        base = default_api()
        try:
            api_id = int(api_id)
        except (TypeError, ValueError):
            raise ImportError_(f"{name}: app_id должен быть числом.")
        meta.api = {
            "api_id": api_id, "api_hash": str(api_hash),
            "device_model": str(_pick(j, "device_model", "device") or base["device_model"]),
            "system_version": str(_pick(j, "system_version", "sdk") or base["system_version"]),
            "app_version": str(_pick(j, "app_version") or base["app_version"]),
            "lang_code": str(_pick(j, "lang_code", "lang_pack") or "en"),
            "system_lang_code": str(_pick(j, "system_lang_code", "system_lang_pack") or "en-US"),
            # «tdesktop» — настоящее имя пакета локализации Telegram Desktop; у остальных клиентов его нет
            "lang_pack": "tdesktop" if api_id == _TDESKTOP_API_ID else "",
        }
    pwd = _pick(j, "twoFA", "two_fa", "2fa", "password_2fa", "password")
    meta.password_2fa = str(pwd) if pwd else ""
    meta.proxy = _proxy_str(j.get("proxy"))
    name_ = " ".join(filter(None, [j.get("first_name"), j.get("last_name")])).strip()
    phone = str(_pick(j, "phone", "phone_number") or "").strip()
    meta.label = name_ or (f"+{phone.lstrip('+')}" if phone else "") or str(_pick(j, "username") or "")
    return meta


# ---------- подбор пар ----------

def expand_zips(files: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """zip с файлами сессий раскрывается; остальные файлы остаются как есть (путь — только имя)."""
    out = []
    for name, data in files:
        rel = _safe_rel(name)
        if rel is None:
            continue
        if rel.suffix.lower() == ".zip" or data.startswith(b"PK\x03\x04"):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        inner = _safe_rel(info.filename)
                        if info.is_dir() or inner is None or info.file_size > _MAX_FILE:
                            continue
                        if inner.suffix.lower() in (".session", ".json", ".txt"):
                            out.append((inner.name, zf.read(info)))
            except zipfile.BadZipFile as e:
                raise ImportError_(f"{rel.name}: архив повреждён ({e}).") from e
        elif len(data) <= _MAX_FILE:
            out.append((rel.name, data))
    return out


def _key(name: str) -> str:
    stem = PurePosixPath(name).stem
    return _SUFFIX.sub("", stem).lower() or stem.lower()


def pair_files(files: list[tuple[str, bytes]]) -> list[Bundle]:
    """Каждый файл сессии — отдельный аккаунт; .json подбирается по имени (123.json ↔ 123_telethon.session).
    Две сессии одного аккаунта (Telethon и Pyrogram) считаются одной — берётся Telethon."""
    sessions: dict[str, SessionFile] = {}
    jsons: dict[str, Meta] = {}
    errors: list[str] = []
    for name, data in files:
        low = name.lower()
        try:
            if low.endswith(".json"):
                jsons[_key(name)] = parse_json(name, data)
            elif looks_like_session(name, data):
                sess = parse_session(name, data)
                key = _key(name)
                prev = sessions.get(key)
                if prev is None or ("telethon" in low and "telethon" not in prev.name.lower()):
                    sessions[key] = sess
        except ImportError_ as e:
            errors.append(str(e))
    if not sessions:
        if errors:
            raise ImportError_(errors[0])
        raise ImportError_("Среди файлов нет сессии: нужен .session (Telethon или Pyrogram) или строковая сессия.")
    bundles = []
    for key, sess in sessions.items():
        meta = jsons.get(key)
        if meta is None and len(jsons) == 1 and len(sessions) == 1:
            meta = next(iter(jsons.values()))
        bundles.append(Bundle(sess, meta or Meta(), key))
    return bundles


# ---------- вход ----------

def to_string_session(sess: SessionFile) -> str:
    s = StringSession()
    s.set_dc(sess.dc_id, sess.address, sess.port)
    s.auth_key = AuthKey(sess.auth_key)
    return StringSession.save(s)


async def convert_session(sess: SessionFile, api: dict | None, new_session: bool = False,
                          password_2fa: str = "", proxy: dict | None = None) -> tuple[str, dict, dict]:
    """Проверяет сессию в Telegram и возвращает (StringSession, параметры API, данные аккаунта)."""
    api = api or default_api()
    api_obj = APIData(**api)
    kwargs = {"proxy": proxy} if proxy else {}
    client = TelegramClient(StringSession(to_string_session(sess)), api=api_obj, **kwargs)
    new_client = None
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise ImportError_(f"{sess.name}: сессия больше не действует (аккаунт вышел или сеанс завершён).")
        if new_session:
            try:
                new_client = await client.QRLoginToNewClient(StringSession(), api=api_obj,
                                                             password=password_2fa or None, **kwargs)
            except BaseException as e:
                _reraise_fatal(e)
                raise ImportError_(f"{sess.name}: не удалось создать новый сеанс ({e}). "
                                   "Если включена 2FA, укажите облачный пароль.") from e
            target = new_client
        else:
            target = client
        me = await target.get_me()
        if me is None:
            raise ImportError_(f"{sess.name}: Telegram не вернул данные аккаунта.")
        return StringSession.save(target.session), api, me_dict(me)
    finally:
        for c in (client, new_client):
            if c is not None and c.is_connected():
                await c.disconnect()
