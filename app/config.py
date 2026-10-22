import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "").strip()
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8080"))

# Веб-панель из локальной сети — кнопка первой в рейке. Пустой адрес — кнопки нет.
LAN_PANEL_URL = os.getenv("LAN_PANEL_URL", "").strip()
LAN_PANEL_NAME = os.getenv("LAN_PANEL_NAME", "").strip() or "Панель локальной сети"
# Порт прокси, через который она встраивается в TG Panel. 0 — открывать в новой вкладке.
LAN_PANEL_PROXY_PORT = int(os.getenv("LAN_PANEL_PROXY_PORT", "8081") or 0)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
if not DATA_DIR.is_absolute():
    DATA_DIR = BASE_DIR / DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "panel.db"
CACHE_DIR = DATA_DIR / "cache"
TMP_DIR = DATA_DIR / "tmp"
CACHE_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)


def _load_or_create(path: Path, factory) -> bytes:
    if path.exists():
        return path.read_bytes().strip()
    value = factory()
    path.write_bytes(value)
    path.chmod(0o600)
    return value


# Ключ шифрования сессий в базе. Без этого файла сохранённые сессии не расшифровать.
FERNET_KEY = _load_or_create(DATA_DIR / "secret.key", Fernet.generate_key)
# Ключ подписи cookie входа в панель
COOKIE_SECRET = _load_or_create(DATA_DIR / "cookie.key", lambda: secrets.token_hex(32).encode()).decode()
