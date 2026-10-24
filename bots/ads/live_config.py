"""Настройки бота из веб-панели: ключи платёжных систем, параметры бота, токен.

Значение из панели хранится в таблице settings (ключ cfg:<ИМЯ>) и важнее .env. Применяется сразу, в объекте
config — без перезапуска; только смена токена бота перезапускает процесс (Docker поднимает его снова).
Ключи платёжных систем перед сохранением проверяются запросом к их API — неработающий ключ не сохранится.
Секреты наружу не отдаются: панель видит только последние 4 символа.
"""
import asyncio
import logging
import os
import re
import signal
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from aiogram import Bot

from bots.ads import db
from bots.ads.config import config, load_config

log = logging.getLogger(__name__)
PREFIX = "cfg:"


class SettingsError(Exception):
    pass


@dataclass(frozen=True)
class Field:
    key: str          # имя как в .env
    group: str        # bot | cryptobot | xrocket | xrocket_hook | freekassa
    kind: str         # secret | text | bool | int | ids | chat | tz | hours | domain
    label: str
    hint: str = ""
    lo: int = 0       # для int — допустимый диапазон
    hi: int = 0


FIELDS = [
    Field("BOT_TOKEN", "bot", "secret", "Токен бота",
          "От @BotFather. После сохранения бот перезапустится (≈10 с). Новый бот должен быть админом каналов, "
          "иначе публиковать не сможет."),
    Field("ADMIN_IDS", "bot", "ids", "Администраторы",
          "Telegram ID через запятую (узнать свой — @Get_myidrobot). Из чата первого админа берётся пост для рассылки."),
    Field("TEST_CHANNEL_ID", "bot", "chat", "Тестовый канал",
          "ID канала <code>-100…</code>, куда публикуются тестовые заказы. Бот должен быть в нём админом."),
    Field("TIMEZONE", "bot", "tz", "Часовой пояс", "Например, <code>Europe/Moscow</code>, <code>Asia/Almaty</code>."),
    Field("WORK_HOURS", "bot", "hours", "Часы публикаций",
          "Первый и последний час слотов, например <code>9-22</code> — с 09:00 до 22:00."),
    Field("BOOKING_DAYS", "bot", "int", "Дней вперёд для брони", "На сколько дней вперёд можно заказать.", 1, 90),
    Field("MIN_LEAD_MINUTES", "bot", "int", "Минимум минут до публикации",
          "Запас времени на модерацию при выборе часа.", 0, 1440),
    Field("CRYPTOPAY_TOKEN", "cryptobot", "secret", "Токен Crypto Pay",
          "@CryptoBot → Crypto Pay → приложение → API-токен. Пусто — оплата CryptoBot выключена."),
    Field("CRYPTOPAY_TESTNET", "cryptobot", "bool", "Тестовая сеть",
          "Весь CryptoBot — в тестовой сети (testnet-pay.crypt.bot), деньги ненастоящие."),
    Field("CRYPTOPAY_TESTNET_TOKEN", "cryptobot", "secret", "Токен тестовой сети",
          "Из @CryptoTestnetBot — для оплаты тестовых заказов ненастоящей криптой."),
    Field("XROCKET_TOKEN", "xrocket", "secret", "API Token",
          "@xRocket → Rocket Pay → приложение → API Token. Пусто — оплата xRocket выключена."),
    Field("XROCKET_WEBHOOK_TOKEN", "xrocket_hook", "secret", "Секрет вебхука",
          "@xRocket → Pay API → приложение → Settings → Webhook secret."),
    Field("XROCKET_WEBHOOK_DOMAIN", "xrocket_hook", "domain", "Домен",
          "Публичный HTTPS-домен, который ведёт на бота, например <code>ads.example.com</code>."),
    Field("FREEKASSA_SHOP_ID", "freekassa", "text", "ID магазина", "Кабинет FreeKassa → настройки магазина."),
    Field("FREEKASSA_API_KEY", "freekassa", "secret", "API-ключ", "Для проверки оплат."),
    Field("FREEKASSA_SECRET", "freekassa", "secret", "Секретное слово", "Первое секретное слово — подпись ссылки на оплату."),
]
BY_KEY = {f.key: f for f in FIELDS}

# поле → атрибут config
ATTR = {"BOT_TOKEN": "bot_token", "ADMIN_IDS": "admin_ids", "TEST_CHANNEL_ID": "test_channel_id",
        "TIMEZONE": "timezone", "BOOKING_DAYS": "booking_days", "MIN_LEAD_MINUTES": "min_lead_minutes",
        "CRYPTOPAY_TOKEN": "cryptopay_token", "CRYPTOPAY_TESTNET": "cryptopay_testnet",
        "CRYPTOPAY_TESTNET_TOKEN": "cryptopay_test_token", "XROCKET_TOKEN": "xrocket_token",
        "XROCKET_WEBHOOK_TOKEN": "xrocket_webhook_secret", "XROCKET_WEBHOOK_DOMAIN": "xrocket_webhook_domain",
        "FREEKASSA_SHOP_ID": "freekassa_shop_id", "FREEKASSA_API_KEY": "freekassa_api_key",
        "FREEKASSA_SECRET": "freekassa_secret"}

_overridden: set[str] = set()       # какие поля заданы из панели


# ---------- разбор и показ значений ----------
def parse(field: Field, raw) -> object:
    """Строка из панели (или .env) → значение для config. Бросает SettingsError."""
    s = "" if raw is None else str(raw).strip()
    if "\n" in s or len(s) > 300:
        raise SettingsError(f"{field.label}: недопустимое значение")
    k = field.kind
    if k in ("secret", "text"):
        if k == "text" and s and not re.fullmatch(r"\d+", s):
            raise SettingsError(f"{field.label}: только цифры")
        return s
    if k == "bool":
        return s.lower() in ("1", "true", "yes", "on", "да")
    if k == "int":
        try:
            n = int(s)
        except ValueError:
            raise SettingsError(f"{field.label}: нужно целое число") from None
        if not field.lo <= n <= field.hi:
            raise SettingsError(f"{field.label}: от {field.lo} до {field.hi}")
        return n
    if k == "ids":
        parts = [p for p in re.split(r"[\s,;]+", s) if p]
        if not parts or not all(re.fullmatch(r"\d{4,15}", p) for p in parts):
            raise SettingsError(f"{field.label}: Telegram ID — числа через запятую, хотя бы один")
        return list(dict.fromkeys(int(p) for p in parts))
    if k == "chat":
        if not s:
            return None
        if not re.fullmatch(r"-\d{6,20}", s):
            raise SettingsError(f"{field.label}: ID канала вида -1001234567890")
        return int(s)
    if k == "domain":
        s = re.sub(r"^https?://", "", s.lower()).split("/")[0]
        if s and not re.fullmatch(r"([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}(:\d{1,5})?", s):
            raise SettingsError(f"{field.label}: только имя хоста, например ads.example.com")
        return s
    if k == "tz":
        try:
            ZoneInfo(s)
        except Exception:
            raise SettingsError(f"{field.label}: неизвестный пояс «{s}»") from None
        return s
    if k == "hours":
        m = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})", s)
        if not m or not (0 <= int(m[1]) <= int(m[2]) <= 23):
            raise SettingsError(f"{field.label}: два часа от 0 до 23 через дефис, например 9-22")
        return int(m[1]), int(m[2])
    raise SettingsError(f"{field.label}: неизвестный тип")


def current(field: Field):
    if field.key == "WORK_HOURS":
        return config.work_start, config.work_end
    return getattr(config, ATTR[field.key])


def to_text(field: Field, value) -> str:
    """Значение config → строка в формате .env."""
    if field.kind == "bool":
        return "true" if value else "false"
    if field.kind == "ids":
        return ", ".join(map(str, value))
    if field.kind == "hours":
        return f"{value[0]}-{value[1]}"
    return "" if value is None else str(value)


def mask(secret: str) -> str:
    return ("•" * 8 + secret[-4:]) if len(secret) > 8 else ("•" * len(secret))


def _set(field: Field, value) -> None:
    if field.key == "WORK_HOURS":
        config.work_start, config.work_end = value
    elif field.key == "ADMIN_IDS":
        config.admin_ids[:] = value          # на этот список ссылаются фильтры роутеров
    else:
        setattr(config, ATTR[field.key], value)


def env_value(field: Field):
    """Значение из .env (или значение по умолчанию)."""
    base = load_config()
    if field.key == "WORK_HOURS":
        return base.work_start, base.work_end
    return getattr(base, ATTR[field.key])


def source(field: Field) -> str:
    if field.key in _overridden:
        return "panel"
    return "env" if os.getenv(field.key, "").strip() else "default"


def describe() -> list[dict]:
    out = []
    for f in FIELDS:
        value = current(f)
        d = {"key": f.key, "group": f.group, "kind": f.kind, "label": f.label, "hint": f.hint,
             "source": source(f), "set": bool(value) if f.kind == "secret" else value is not None}
        d["value"] = mask(value) if f.kind == "secret" else (value if f.kind == "bool" else to_text(f, value))
        out.append(d)
    return out


# ---------- платёжные клиенты ----------
def reconfigure_clients() -> None:
    from bots.ads import cryptopay
    from bots.ads.freekassa import freekassa
    from bots.ads.xrocket import xrocket
    cryptopay.reconfigure()
    xrocket.setup(config.xrocket_token)
    freekassa.setup(config.freekassa_shop_id, config.freekassa_api_key, config.freekassa_secret)


async def verify_clients() -> dict[str, str | None]:
    """Проверить xRocket и FreeKassa (они включаются только после проверки ключа)."""
    from bots.ads.freekassa import freekassa
    from bots.ads.xrocket import xrocket
    res = {}
    if xrocket.token:
        res["xrocket"] = await xrocket.verify()
    if freekassa.configured:
        res["freekassa"] = await freekassa.verify()
    return res


async def _check_keys(new: dict[str, object], changed: set[str]) -> None:
    """Проверяет новые ключи запросом к API. Бросает SettingsError с понятной причиной."""
    from bots.ads.cryptopay import CryptoPay
    from bots.ads.freekassa import FreeKassa
    from bots.ads.xrocket import XRocket

    def val(key):
        return new[key] if key in new else current(BY_KEY[key])

    if changed & {"CRYPTOPAY_TOKEN", "CRYPTOPAY_TESTNET"} and val("CRYPTOPAY_TOKEN"):
        err = await CryptoPay(val("CRYPTOPAY_TOKEN"), val("CRYPTOPAY_TESTNET")).verify()
        if err:
            raise SettingsError(f"CryptoBot не принял токен: {err}")
    if "CRYPTOPAY_TESTNET_TOKEN" in changed and val("CRYPTOPAY_TESTNET_TOKEN"):
        err = await CryptoPay(val("CRYPTOPAY_TESTNET_TOKEN"), True).verify()
        if err:
            raise SettingsError(f"CryptoBot (тестовая сеть) не принял токен: {err}")
    if "XROCKET_TOKEN" in changed and val("XROCKET_TOKEN"):
        err = await XRocket(val("XROCKET_TOKEN")).verify()
        if err:
            raise SettingsError(f"xRocket не принял токен: {err}")
    hook = ("XROCKET_WEBHOOK_TOKEN", "XROCKET_WEBHOOK_DOMAIN")
    if changed & set(hook):
        filled = [bool(val(k)) for k in hook]
        if any(filled) and not all(filled):
            raise SettingsError("Вебхук xRocket: укажите и секрет, и домен (или очистите оба, чтобы работать опросом)")
    fk = ("FREEKASSA_SHOP_ID", "FREEKASSA_API_KEY", "FREEKASSA_SECRET")
    if changed & set(fk):
        filled = [bool(val(k)) for k in fk]
        if any(filled) and not all(filled):
            raise SettingsError("FreeKassa: заполните все три поля — ID магазина, API-ключ и секретное слово "
                                "(или очистите все, чтобы выключить)")
        if all(filled):
            err = await FreeKassa(*(val(k) for k in fk)).verify()
            if err:
                raise SettingsError(f"FreeKassa не приняла ключи: {err}")
    if "BOT_TOKEN" in changed:
        if not val("BOT_TOKEN"):
            raise SettingsError("Токен бота не может быть пустым")
        try:
            probe = Bot(val("BOT_TOKEN"))
        except Exception:
            raise SettingsError("Токен бота: неверный формат") from None
        try:
            await probe.get_me()
        except Exception as e:
            raise SettingsError(f"Telegram не принял токен: {e}") from None
        finally:
            await probe.session.close()


def restart_soon(delay: float = 1.5) -> None:
    """Корректно останавливаем процесс (как docker stop); Docker сам поднимет его снова — уже с новым токеном."""
    log.warning("перезапуск бота по запросу из панели")
    asyncio.get_running_loop().call_later(delay, os.kill, os.getpid(), signal.SIGTERM)


# ---------- загрузка, сохранение, сброс ----------
async def load() -> None:
    """При старте: значения из панели поверх .env."""
    for f in FIELDS:
        raw = await db.get_setting(PREFIX + f.key)
        if raw is None:
            continue
        try:
            _set(f, parse(f, raw))
            _overridden.add(f.key)
        except SettingsError as e:
            log.warning("настройка %s из панели не применена: %s", f.key, e)
    reconfigure_clients()


def overridden(key: str) -> bool:
    return key in _overridden


async def save(values: dict) -> dict:
    """values: {ИМЯ: строка}. Пустая строка у секрета — очистить. Возвращает {"restart": bool, "verify": {...}}."""
    unknown = [k for k in values if k not in BY_KEY]
    if unknown:
        raise SettingsError(f"Неизвестная настройка: {', '.join(unknown)}")
    new = {k: parse(BY_KEY[k], v) for k, v in values.items()}
    changed = {k for k, v in new.items() if v != current(BY_KEY[k])}
    await _check_keys(new, changed)
    for k in changed:
        f = BY_KEY[k]
        await db.set_setting(PREFIX + k, to_text(f, new[k]))
        _set(f, new[k])
        _overridden.add(k)
    restart = "BOT_TOKEN" in changed
    res = {"restart": restart, "verify": {}}
    if changed & {f.key for f in FIELDS if f.group != "bot"}:
        reconfigure_clients()
        res["verify"] = await verify_clients()
    if changed & {"XROCKET_WEBHOOK_TOKEN", "XROCKET_WEBHOOK_DOMAIN"} and config.xrocket_webhook_domain:
        from bots.ads.xrocket import probe_webhook
        res["verify"]["вебхук xRocket"] = await probe_webhook()
    if restart:
        restart_soon()
    log.info("настройки из панели сохранены: %s", ", ".join(sorted(changed)) or "без изменений")
    return res


async def reset(key: str) -> dict:
    """Убрать значение из панели — снова действует .env."""
    f = BY_KEY.get(key)
    if not f:
        raise SettingsError("Неизвестная настройка")
    before = current(f)
    if key == "BOT_TOKEN" and not env_value(f):
        raise SettingsError("В .env нет BOT_TOKEN — сбросить токен из панели нельзя, бот не запустится")
    await db.db().execute("DELETE FROM settings WHERE key = ?", (PREFIX + key,))
    await db.db().commit()
    _overridden.discard(key)
    _set(f, env_value(f))
    res = {"restart": False, "verify": {}}
    if f.group != "bot":
        reconfigure_clients()
        res["verify"] = await verify_clients()
    if key == "BOT_TOKEN" and current(f) != before:
        res["restart"] = True
        restart_soon()
    return res
