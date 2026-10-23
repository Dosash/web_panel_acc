import os
import re
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

VERSION = "0.11.2"


def _env(name: str, old: str, default: str = "") -> str:
    # старые имена (PANEL_PASSWORD, HOST, PORT) из .env версий до 0.6.0 тоже понимаем
    return (os.getenv(name) or os.getenv(old) or default).strip()


def normalize_prefix(value: str) -> str:
    """WEB_PREFIX: 'accounts', '/accounts/' → '/accounts'; '' и '/' → ''."""
    parts = [p for p in value.strip().split("/") if p]
    for p in parts:
        if p in (".", "..") or not re.fullmatch(r"[A-Za-z0-9._~-]+", p):
            raise ValueError(f"WEB_PREFIX «{value}»: допустимы латинские буквы, цифры и символы - _ . ~ "
                             "(например, /accounts)")
    return "/" + "/".join(parts) if parts else ""


WEB_PASSWORD = _env("WEB_PASSWORD", "PANEL_PASSWORD")
WEB_HOST = _env("WEB_HOST", "HOST", "127.0.0.1")
WEB_PORT = int(_env("WEB_PORT", "PORT", "8080"))
# Путь панели, если она открыта не в корне сайта (за общим nginx): /accounts → http://сервер/accounts/
WEB_PREFIX = normalize_prefix(os.getenv("WEB_PREFIX", ""))
# Ссылка «Все панели» в рейке, когда за одним nginx несколько панелей. Пусто — без ссылки.
HUB_URL = os.getenv("HUB_URL", "").strip()
if HUB_URL and not re.match(r"(/|https?://)", HUB_URL):
    raise ValueError(f"HUB_URL «{HUB_URL}»: укажите путь (например, /) или адрес http(s)://…")
# Проверка новой версии на GitHub (значок «Вышло обновление»). UPDATE_CHECK=0 — не проверять.
# Адрес можно подменить — для проверки на своём сервере (TG_PANEL_UPDATE_URL — то же для программы)
UPDATE_CHECK = os.getenv("UPDATE_CHECK", "1").strip().lower() not in ("0", "false", "no", "off")
UPDATE_URL = _env("UPDATE_URL", "TG_PANEL_UPDATE_URL",
                  "https://api.github.com/repos/Dosash/web_panel_acc/releases/latest")

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
