"""Превращение папки tdata (Telegram Desktop) в строковую сессию Telethon через opentele."""
import asyncio
import shutil
import uuid
import zipfile
from pathlib import Path

from opentele.api import API, APIData, UseCurrentSession
from opentele.td import TDesktop
from telethon.sessions import StringSession

from .config import TMP_DIR

# Кэш, эмодзи и дампы для входа не нужны, а весят сотни мегабайт
_SKIP_DIRS = {"user_data", "emoji", "dumps", "temp", "tdummy", "webview"}
_MAX_FILE = 5 * 1024 * 1024


class ImportError_(Exception):
    """Понятная пользователю ошибка импорта."""


def _reraise_fatal(e: BaseException) -> None:
    """opentele наследует свои ошибки от BaseException, поэтому ловим его, но системные пропускаем."""
    if isinstance(e, (KeyboardInterrupt, SystemExit, asyncio.CancelledError, GeneratorExit, ImportError_)):
        raise e


def _wanted(rel: Path, size: int | None = None) -> bool:
    if any(p.lower().startswith(tuple(_SKIP_DIRS)) for p in rel.parts[:-1]):
        return False
    return size is None or size <= _MAX_FILE


def _safe_rel(name: str) -> Path | None:
    rel = Path(name.replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        return None
    return rel


def save_upload(files: list[tuple[str, bytes]]) -> Path:
    """Сохраняет загруженные файлы (папку или zip) во временную папку и возвращает её."""
    work = TMP_DIR / uuid.uuid4().hex
    work.mkdir(parents=True)
    for name, data in files:
        rel = _safe_rel(name)
        if rel is None:
            continue
        if rel.suffix.lower() == ".zip":
            zip_path = work / "_upload.zip"
            zip_path.write_bytes(data)
            with zipfile.ZipFile(zip_path) as zf:
                for info in zf.infolist():
                    inner = _safe_rel(info.filename)
                    if info.is_dir() or inner is None or not _wanted(inner, info.file_size):
                        continue
                    target = work / inner
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(zf.read(info))
            zip_path.unlink()
        elif _wanted(rel, len(data)):
            target = work / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return work


def find_tdata_root(work: Path) -> Path:
    """Ищет папку, в которой лежит key_datas (это и есть корень tdata)."""
    for key in sorted(work.rglob("key_data*"), key=lambda p: len(p.parts)):
        if key.is_file():
            return key.parent
    raise ImportError_("В загруженных файлах нет key_datas — это не папка tdata.")


def _api_dict(api: APIData) -> dict:
    return {
        "api_id": api.api_id, "api_hash": api.api_hash,
        "device_model": api.device_model, "system_version": api.system_version,
        "app_version": api.app_version, "lang_code": api.lang_code,
        "system_lang_code": api.system_lang_code, "lang_pack": api.lang_pack,
    }


def me_dict(me) -> dict:
    return {
        "id": me.id, "phone": me.phone or "", "username": me.username or "",
        "full_name": " ".join(filter(None, [me.first_name, me.last_name])),
    }


async def convert(work: Path, unique_id: str, passcode: str = "", new_session: bool = False,
                  password_2fa: str = "", proxy: dict | None = None) -> tuple[str, dict, dict]:
    """Возвращает (StringSession, параметры API, данные аккаунта). Временная папка удаляется всегда."""
    try:
        root = find_tdata_root(work)
        api = API.TelegramDesktop.Generate(system="windows", unique_id=unique_id)
        try:
            tdesk = TDesktop(str(root), api=api, passcode=passcode or None)
        except BaseException as e:
            _reraise_fatal(e)
            raise ImportError_(f"Не удалось прочитать tdata ({e}). Если в Telegram Desktop стоит "
                               "локальный код-пароль, укажите его.") from e
        if not tdesk.isLoaded() or tdesk.accountsCount == 0:
            raise ImportError_("В tdata нет авторизованного аккаунта (или нужен локальный код-пароль).")

        kwargs = {"proxy": proxy} if proxy else {}
        # Клиент на ключе из tdata (пока не подключён)
        client = await tdesk.ToTelethon(None, UseCurrentSession, api, **kwargs)
        new_client = None
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise ImportError_("Сессия из tdata больше не действует (аккаунт вышел или сеанс завершён).")
            if new_session:
                # Новое устройство входит через tdata, как по QR-коду; сеанс tdata остаётся рабочим
                try:
                    new_client = await client.QRLoginToNewClient(
                        StringSession(), api=api, password=password_2fa or None, **kwargs)
                except BaseException as e:
                    _reraise_fatal(e)
                    raise ImportError_(f"Не удалось создать новый сеанс ({e}). "
                                       "Если включена 2FA, укажите облачный пароль.") from e
                target = new_client
            else:
                target = client
            me = await target.get_me()
            return StringSession.save(target.session), _api_dict(api), me_dict(me)
        finally:
            for c in (client, new_client):
                if c is not None and c.is_connected():
                    await c.disconnect()
    finally:
        shutil.rmtree(work, ignore_errors=True)
