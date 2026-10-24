import asyncio
import json
import os
import secrets
import sqlite3
import string
import time
from typing import Any

import aiosqlite

from bots.ads.config import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id       INTEGER UNIQUE NOT NULL,
    title         TEXT NOT NULL,
    username      TEXT,
    invite_link   TEXT,
    description   TEXT,
    subscribers   INTEGER DEFAULT 0,
    avg_views     INTEGER DEFAULT 0,
    views_manual  INTEGER DEFAULT 0,
    price_stars   INTEGER DEFAULT 0,
    price_usd     REAL DEFAULT 0,
    price_rub     REAL DEFAULT 0,
    active        INTEGER DEFAULT 1,
    updated_at    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    user_name      TEXT,
    from_chat_id   INTEGER NOT NULL,
    message_id     INTEGER NOT NULL,
    reply_markup   TEXT,
    channel_ids    TEXT NOT NULL,
    total_stars    INTEGER NOT NULL,
    total_usd      REAL NOT NULL,
    status         TEXT NOT NULL,
    reject_reason  TEXT,
    pay_method     TEXT,
    cp_invoice_id  INTEGER,
    cp_invoice_url TEXT,
    charge_id      TEXT,
    created_at     INTEGER NOT NULL,
    paid_at        INTEGER
);

-- Бронь слота: один заказ на канал в один час. UNIQUE не даёт забронировать слот дважды.
CREATE TABLE IF NOT EXISTS bookings (
    order_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    slot_ts     INTEGER NOT NULL,
    is_test     INTEGER NOT NULL DEFAULT 0,
    UNIQUE (channel_id, slot_ts, is_test)
);
CREATE INDEX IF NOT EXISTS bookings_order ON bookings (order_id);

CREATE TABLE IF NOT EXISTS screens (
    user_id  INTEGER PRIMARY KEY,
    msg_id   INTEGER,
    extra    TEXT DEFAULT '[]'
);

-- Обращения в поддержку: переписка пользователя с администратором
CREATE TABLE IF NOT EXISTS support_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    from_admin    INTEGER NOT NULL DEFAULT 0,
    text          TEXT,
    media         TEXT,               -- тип вложения (photo, video, document…), если есть
    src_chat_id   INTEGER,            -- откуда скопировать вложение
    src_msg_id    INTEGER,
    is_read       INTEGER NOT NULL DEFAULT 0,
    created_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS support_user ON support_messages (user_id, id);

CREATE TABLE IF NOT EXISTS support_threads (
    user_id       INTEGER PRIMARY KEY,
    user_name     TEXT,
    status        TEXT NOT NULL DEFAULT 'open',   -- open | closed
    updated_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    lang        TEXT,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS test_users (
    user_id INTEGER PRIMARY KEY
);

-- каждый /start — для счётчика запусков
CREATE TABLE IF NOT EXISTS start_log (
    user_id  INTEGER NOT NULL,
    ts       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS start_log_ts ON start_log (ts);

-- рассылки рекламного поста всем пользователям бота
CREATE TABLE IF NOT EXISTS broadcasts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    from_chat_id  INTEGER NOT NULL,       -- откуда копировать пост (чат админа с ботом)
    message_id    INTEGER NOT NULL,
    reply_markup  TEXT,
    post_json     TEXT,
    status        TEXT NOT NULL,          -- running | done | stopped | error
    total         INTEGER NOT NULL DEFAULT 0,
    sent          INTEGER NOT NULL DEFAULT 0,
    blocked       INTEGER NOT NULL DEFAULT 0,
    failed        INTEGER NOT NULL DEFAULT 0,
    cursor        INTEGER NOT NULL DEFAULT 0,   -- последний обработанный user_id (для продолжения после рестарта)
    error         TEXT,
    created_at    INTEGER NOT NULL,
    finished_at   INTEGER
);

CREATE TABLE IF NOT EXISTS publications (
    order_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    chat_id     INTEGER NOT NULL,
    message_id  INTEGER,
    error       TEXT,
    created_at  INTEGER NOT NULL
);
"""

# Статусы заказа
MODERATION = "moderation"      # ждёт проверки администратором
APPROVED = "approved"          # одобрен, ждёт оплаты
REJECTED = "rejected"          # отклонён модератором
PAID = "paid"                  # оплачен, идёт публикация
SCHEDULED = "scheduled"        # оплачен, время забронировано, ждёт публикации
NEED_TIME = "need_time"        # оплачен, но выбранное время успели занять — нужно выбрать новое
PUBLISHED = "published"        # опубликован
CANCELLED = "cancelled"        # отменён пользователем
EXPIRED = "expired"            # (устаревший статус, оставлен для старых записей)

STATUS_TITLES = {
    MODERATION: "🕓 На модерации",
    APPROVED: "💳 Ожидает оплаты",
    REJECTED: "❌ Отклонён",
    PAID: "⏳ Оплачен, публикуется",
    SCHEDULED: "⏰ Оплачен, ждёт публикации",
    NEED_TIME: "⚠️ Оплачен — выберите время",
    PUBLISHED: "✅ Опубликован",
    CANCELLED: "🚫 Отменён",
    EXPIRED: "⌛ Бронь истекла",
}

# статусы, при которых заказ держит бронь времени (бронь ставится только после оплаты)
HOLDING = (PAID, SCHEDULED, PUBLISHED)
# статусы, в которых пользователь может менять время
RESCHEDULABLE = (MODERATION, APPROVED, NEED_TIME, SCHEDULED)

_db: aiosqlite.Connection | None = None


async def init_db() -> None:
    global _db
    os.makedirs(os.path.dirname(config.db_path) or ".", exist_ok=True)
    _db = await aiosqlite.connect(config.db_path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    # миграции для уже созданных баз
    cur = await _db.execute("PRAGMA table_info(orders)")
    cols = {r["name"] for r in await cur.fetchall()}
    for col, ddl in (("is_test", "INTEGER DEFAULT 0"), ("publish_at", "INTEGER"), ("approved_at", "INTEGER"),
                     ("xr_invoice_id", "TEXT"), ("xr_invoice_url", "TEXT"), ("post_json", "TEXT"),
                     ("total_rub", "REAL DEFAULT 0"), ("fk_payment_id", "TEXT"), ("fk_invoice_url", "TEXT"),
                     ("fk_invoice_at", "INTEGER")):
        if col not in cols:
            await _db.execute(f"ALTER TABLE orders ADD COLUMN {col} {ddl}")
    cur = await _db.execute("PRAGMA table_info(support_messages)")
    if "file_id" not in {r["name"] for r in await cur.fetchall()}:
        await _db.execute("ALTER TABLE support_messages ADD COLUMN file_id TEXT")
    cur = await _db.execute("PRAGMA table_info(channels)")
    cols = {r["name"] for r in await cur.fetchall()}
    if "token" not in cols:
        await _db.execute("ALTER TABLE channels ADD COLUMN token TEXT")
    if "price_rub" not in cols:
        await _db.execute("ALTER TABLE channels ADD COLUMN price_rub REAL DEFAULT 0")
    if "bot_admin" not in cols:
        # старые каналы добавлялись только при правах админа
        await _db.execute("ALTER TABLE channels ADD COLUMN bot_admin INTEGER DEFAULT 1")
    await _db.execute("CREATE UNIQUE INDEX IF NOT EXISTS channels_token ON channels (token)")
    cur = await _db.execute("PRAGMA table_info(users)")
    cols = {r["name"] for r in await cur.fetchall()}
    if "blocked" not in cols:
        for col, ddl in (("first_name", "TEXT"), ("username", "TEXT"), ("blocked", "INTEGER DEFAULT 0"),
                         ("blocked_at", "INTEGER"), ("last_seen", "INTEGER")):
            await _db.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
        # раньше в users попадали только выбравшие язык — добираем заказчиков и писавших в поддержку
        await _db.execute("INSERT OR IGNORE INTO users (user_id, created_at)"
                          " SELECT user_id, MIN(created_at) FROM orders GROUP BY user_id")
        await _db.execute("INSERT OR IGNORE INTO users (user_id, created_at)"
                          " SELECT user_id, MIN(created_at) FROM support_messages GROUP BY user_id")
    # у старых каналов токена нет — выдаём
    cur = await _db.execute("SELECT id FROM channels WHERE token IS NULL")
    for row in await cur.fetchall():
        await _db.execute("UPDATE channels SET token = ? WHERE id = ?", (new_token(), row["id"]))
    await _db.commit()


_TOKEN_ALPHABET = string.ascii_letters + string.digits


def new_token(length: int = 10) -> str:
    """Случайный токен для ссылки t.me/bot?start=<token>."""
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(length))


async def close_db() -> None:
    if _db:
        await _db.close()


def db() -> aiosqlite.Connection:
    assert _db is not None, "init_db() не вызван"
    return _db


def now() -> int:
    return int(time.time())


# ---------- каналы ----------

async def upsert_channel(chat_id: int, title: str, username: str | None, invite_link: str | None,
                         description: str | None, subscribers: int, avg_views: int | None,
                         bot_admin: bool = True) -> int:
    cur = await db().execute("SELECT id, views_manual FROM channels WHERE chat_id = ?", (chat_id,))
    row = await cur.fetchone()
    if row:
        fields = dict(title=title, username=username, invite_link=invite_link,
                      description=description, subscribers=subscribers, updated_at=now(),
                      bot_admin=int(bot_admin))
        # ручное значение просмотров не перетираем
        if avg_views is not None and not row["views_manual"]:
            fields["avg_views"] = avg_views
        sets = ", ".join(f"{k} = ?" for k in fields)
        await db().execute(f"UPDATE channels SET {sets} WHERE id = ?", (*fields.values(), row["id"]))
        await db().commit()
        return row["id"]
    cur = await db().execute(
        "INSERT INTO channels (chat_id, title, username, invite_link, description, subscribers, avg_views,"
        " updated_at, token, bot_admin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (chat_id, title, username, invite_link, description, subscribers, avg_views or 0, now(), new_token(),
         int(bot_admin)),
    )
    await db().commit()
    return cur.lastrowid


async def upsert_placeholder(chat_id: int) -> int:
    """Заготовка канала, который Telegram пока не отдаёт боту (бот ещё не добавлен)."""
    cur = await db().execute("SELECT id FROM channels WHERE chat_id = ?", (chat_id,))
    row = await cur.fetchone()
    if row:
        await db().execute("UPDATE channels SET bot_admin = 0, updated_at = ? WHERE id = ?", (now(), row["id"]))
        await db().commit()
        return row["id"]
    cur = await db().execute(
        "INSERT INTO channels (chat_id, title, updated_at, token, bot_admin) VALUES (?, ?, ?, ?, 0)",
        (chat_id, f"Канал {chat_id}", now(), new_token()),
    )
    await db().commit()
    return cur.lastrowid


async def get_channel_by_token(token: str) -> aiosqlite.Row | None:
    cur = await db().execute("SELECT * FROM channels WHERE token = ?", (token,))
    return await cur.fetchone()


async def regenerate_token(channel_id: int) -> str:
    token = new_token()
    await db().execute("UPDATE channels SET token = ? WHERE id = ?", (token, channel_id))
    await db().commit()
    return token


async def get_channel(channel_id: int) -> aiosqlite.Row | None:
    cur = await db().execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
    return await cur.fetchone()


async def get_channel_by_chat(chat_id: int) -> aiosqlite.Row | None:
    cur = await db().execute("SELECT * FROM channels WHERE chat_id = ?", (chat_id,))
    return await cur.fetchone()


async def list_channels(only_active: bool = False, include_hidden: bool = False) -> list[aiosqlite.Row]:
    """only_active — только каналы с ценой, доступные для заказа.
    include_hidden — показывать и скрытые (для тестового режима)."""
    q = "SELECT * FROM channels"
    if only_active:
        # пользователям — только каналы с ценой (хотя бы в одной валюте), где бот может публиковать
        q += " WHERE (price_stars > 0 OR price_usd > 0 OR price_rub > 0) AND bot_admin = 1"
        if not include_hidden:
            q += " AND active = 1"
    q += " ORDER BY subscribers DESC"
    cur = await db().execute(q)
    return list(await cur.fetchall())


async def get_channels(ids: list[int]) -> list[aiosqlite.Row]:
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    cur = await db().execute(f"SELECT * FROM channels WHERE id IN ({marks}) ORDER BY subscribers DESC", ids)
    return list(await cur.fetchall())


async def update_channel(channel_id: int, **fields: Any) -> None:
    sets = ", ".join(f"{k} = ?" for k in fields)
    await db().execute(f"UPDATE channels SET {sets} WHERE id = ?", (*fields.values(), channel_id))
    await db().commit()


async def set_price_all(stars: int, usd: float, rub: float) -> None:
    await db().execute("UPDATE channels SET price_stars = ?, price_usd = ?, price_rub = ?", (stars, usd, rub))
    await db().commit()


async def delete_channel(channel_id: int) -> None:
    await db().execute("DELETE FROM channels WHERE id = ?", (channel_id,))
    await db().commit()


# ---------- заказы ----------

class SlotBusy(Exception):
    """Слот уже занят в одном из каналов."""

    def __init__(self, channel_ids: list[int]):
        super().__init__("slot busy")
        self.channel_ids = channel_ids


# одна блокировка на все операции с бронями — чтобы проверка и запись шли без вклинивания
_booking_lock = asyncio.Lock()


async def _busy_channels(channel_ids: list[int], slot_ts: int, is_test: bool,
                         exclude_order: int | None = None) -> list[int]:
    if not channel_ids:
        return []
    marks = ",".join("?" * len(channel_ids))
    cur = await db().execute(
        f"SELECT channel_id FROM bookings WHERE slot_ts = ? AND is_test = ? AND channel_id IN ({marks})"
        " AND order_id != ?",
        (slot_ts, int(is_test), *channel_ids, exclude_order or -1),
    )
    return [r[0] for r in await cur.fetchall()]


async def create_order(user_id: int, user_name: str, from_chat_id: int, message_id: int,
                       reply_markup: str | None, channel_ids: list[int],
                       total_stars: int, total_usd: float, total_rub: float, is_test: bool = False,
                       publish_at: int | None = None, post_json: str | None = None) -> int:
    """Создаёт заказ с желаемым временем. Время НЕ бронируется — только проверяется,
    что оно ещё не занято оплаченным заказом. Бронь ставится при оплате (book_order)."""
    async with _booking_lock:
        if publish_at:
            busy = await _busy_channels(channel_ids, publish_at, is_test)
            if busy:
                raise SlotBusy(busy)
        cur = await db().execute(
            "INSERT INTO orders (user_id, user_name, from_chat_id, message_id, reply_markup, channel_ids,"
            " total_stars, total_usd, total_rub, status, created_at, is_test, publish_at, post_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, user_name, from_chat_id, message_id, reply_markup, json.dumps(channel_ids),
             total_stars, total_usd, total_rub, MODERATION, now(), int(is_test), publish_at, post_json),
        )
        await db().commit()
        return cur.lastrowid


async def book_order(order_id: int, publish_at: int) -> None:
    """Бронирует время за оплаченным заказом. Бросает SlotBusy, если его уже заняли."""
    order = await get_order(order_id)
    channel_ids = order_channel_ids(order)
    async with _booking_lock:
        busy = await _busy_channels(channel_ids, publish_at, order["is_test"], exclude_order=order_id)
        if busy:
            raise SlotBusy(busy)
        try:
            await db().execute("DELETE FROM bookings WHERE order_id = ?", (order_id,))
            await db().executemany(
                "INSERT INTO bookings (order_id, channel_id, slot_ts, is_test) VALUES (?, ?, ?, ?)",
                [(order_id, ch, publish_at, order["is_test"]) for ch in channel_ids],
            )
            await db().execute("UPDATE orders SET publish_at = ? WHERE id = ?", (publish_at, order_id))
            await db().commit()
        except sqlite3.IntegrityError:
            await db().rollback()
            raise SlotBusy(await _busy_channels(channel_ids, publish_at, order["is_test"], exclude_order=order_id))


async def reschedule_order(order_id: int, publish_at: int | None, new_status: str | None = None) -> None:
    """Меняет время заказа. Для оплаченных заказов переносит бронь, для остальных — только
    желаемое время. Бросает SlotBusy, если время занято."""
    order = await get_order(order_id)
    channel_ids = order_channel_ids(order)
    paid = (new_status or order["status"]) in HOLDING
    async with _booking_lock:
        if publish_at:
            busy = await _busy_channels(channel_ids, publish_at, order["is_test"], exclude_order=order_id)
            if busy:
                raise SlotBusy(busy)
        try:
            await db().execute("DELETE FROM bookings WHERE order_id = ?", (order_id,))
            if publish_at and paid:
                await db().executemany(
                    "INSERT INTO bookings (order_id, channel_id, slot_ts, is_test) VALUES (?, ?, ?, ?)",
                    [(order_id, ch, publish_at, order["is_test"]) for ch in channel_ids],
                )
            fields = {"publish_at": publish_at}
            if new_status:
                fields["status"] = new_status
            sets = ", ".join(f"{k} = ?" for k in fields)
            await db().execute(f"UPDATE orders SET {sets} WHERE id = ?", (*fields.values(), order_id))
            await db().commit()
        except sqlite3.IntegrityError:
            await db().rollback()
            raise SlotBusy(await _busy_channels(channel_ids, publish_at, order["is_test"], exclude_order=order_id))


async def release_booking(order_id: int) -> None:
    async with _booking_lock:
        await db().execute("DELETE FROM bookings WHERE order_id = ?", (order_id,))
        await db().commit()


async def busy_map(start_ts: int, end_ts: int, is_test: bool,
                   exclude_order: int | None = None) -> dict[int, set[int]]:
    """{slot_ts: {channel_id, ...}} — занятые слоты в интервале."""
    cur = await db().execute(
        "SELECT slot_ts, channel_id FROM bookings WHERE slot_ts >= ? AND slot_ts <= ? AND is_test = ?"
        " AND order_id != ?",
        (start_ts, end_ts, int(is_test), exclude_order or -1),
    )
    result: dict[int, set[int]] = {}
    for slot_ts, channel_id in await cur.fetchall():
        result.setdefault(slot_ts, set()).add(channel_id)
    return result


async def upcoming_bookings(from_ts: int, is_test: bool, limit: int = 40) -> list[aiosqlite.Row]:
    cur = await db().execute(
        "SELECT o.* FROM orders o"
        " WHERE o.publish_at >= ? AND o.is_test = ? AND o.status IN (?, ?, ?, ?)"
        " ORDER BY o.publish_at, o.id LIMIT ?",
        (from_ts, int(is_test), MODERATION, APPROVED, PAID, SCHEDULED, limit),
    )
    return list(await cur.fetchall())


async def due_scheduled(ts: int) -> list[aiosqlite.Row]:
    cur = await db().execute(
        "SELECT * FROM orders WHERE status = ? AND (publish_at IS NULL OR publish_at <= ?)", (SCHEDULED, ts))
    return list(await cur.fetchall())


async def get_order(order_id: int) -> aiosqlite.Row | None:
    cur = await db().execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    return await cur.fetchone()


async def user_orders(user_id: int, limit: int = 10) -> list[aiosqlite.Row]:
    cur = await db().execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    return list(await cur.fetchall())


async def moderation_queue() -> list[aiosqlite.Row]:
    cur = await db().execute("SELECT * FROM orders WHERE status = ? ORDER BY id", (MODERATION,))
    return list(await cur.fetchall())


async def count_status(status: str) -> int:
    cur = await db().execute("SELECT COUNT(*) FROM orders WHERE status = ?", (status,))
    return (await cur.fetchone())[0]


async def change_status(order_id: int, from_status: str, to_status: str, **fields: Any) -> bool:
    """Атомарно меняет статус. Возвращает False, если заказ уже не в from_status."""
    fields["status"] = to_status
    if to_status == APPROVED:
        fields.setdefault("approved_at", now())
    sets = ", ".join(f"{k} = ?" for k in fields)
    cur = await db().execute(
        f"UPDATE orders SET {sets} WHERE id = ? AND status = ?", (*fields.values(), order_id, from_status)
    )
    await db().commit()
    changed = cur.rowcount > 0
    if changed and to_status not in HOLDING:
        await release_booking(order_id)   # отказ/отмена/истечение — время освобождается
    return changed


async def update_order(order_id: int, **fields: Any) -> None:
    sets = ", ".join(f"{k} = ?" for k in fields)
    await db().execute(f"UPDATE orders SET {sets} WHERE id = ?", (*fields.values(), order_id))
    await db().commit()


async def orders_with_xrocket_invoice() -> list[aiosqlite.Row]:
    cur = await db().execute(
        "SELECT * FROM orders WHERE status = ? AND xr_invoice_id IS NOT NULL AND is_test = 0", (APPROVED,)
    )
    return list(await cur.fetchall())


async def order_by_xrocket_invoice(invoice_id: str) -> aiosqlite.Row | None:
    """Неоплаченный заказ с этим счётом xRocket (для вебхука)."""
    cur = await db().execute(
        "SELECT * FROM orders WHERE status = ? AND xr_invoice_id = ? AND is_test = 0", (APPROVED, str(invoice_id))
    )
    return await cur.fetchone()


async def orders_with_fk_invoice(since: int) -> list[aiosqlite.Row]:
    """Неоплаченные заказы со ссылкой FreeKassa, выданной после since (старые проверяются кнопкой)."""
    cur = await db().execute(
        "SELECT * FROM orders WHERE status = ? AND fk_payment_id IS NOT NULL AND fk_invoice_at >= ? AND is_test = 0",
        (APPROVED, since),
    )
    return list(await cur.fetchall())


async def orders_with_crypto_invoice() -> list[aiosqlite.Row]:
    cur = await db().execute(
        "SELECT * FROM orders WHERE status = ? AND cp_invoice_id IS NOT NULL", (APPROVED,)
    )
    return list(await cur.fetchall())


def order_channel_ids(order: aiosqlite.Row) -> list[int]:
    return json.loads(order["channel_ids"])


async def add_publication(order_id: int, channel_id: int, chat_id: int,
                          message_id: int | None, error: str | None) -> None:
    await db().execute(
        "INSERT INTO publications (order_id, channel_id, chat_id, message_id, error, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (order_id, channel_id, chat_id, message_id, error, now()),
    )
    await db().commit()


async def stats() -> dict[str, Any]:
    cur = await db().execute(
        "SELECT COUNT(*), COALESCE(SUM(CASE WHEN pay_method='stars' THEN total_stars END), 0),"
        " COALESCE(SUM(CASE WHEN pay_method='crypto' THEN total_usd END), 0),"
        " COALESCE(SUM(CASE WHEN pay_method='xrocket' THEN total_usd END), 0),"
        " COALESCE(SUM(CASE WHEN pay_method='freekassa' THEN total_rub END), 0)"
        " FROM orders WHERE status IN (?, ?, ?, ?) AND is_test = 0", (SCHEDULED, NEED_TIME, PAID, PUBLISHED),
    )
    paid, stars, usd, xr, rub = await cur.fetchone()
    cur = await db().execute("SELECT COUNT(DISTINCT user_id) FROM orders WHERE is_test = 0")
    users = (await cur.fetchone())[0]
    return {"paid": paid, "stars": stars, "usd": usd, "xrocket": xr, "freekassa": rub, "users": users}


# ---------- тестовый режим ----------

async def is_test_user(user_id: int) -> bool:
    cur = await db().execute("SELECT 1 FROM test_users WHERE user_id = ?", (user_id,))
    return await cur.fetchone() is not None


async def set_test_user(user_id: int, enabled: bool) -> None:
    if enabled:
        await db().execute("INSERT OR IGNORE INTO test_users (user_id) VALUES (?)", (user_id,))
    else:
        await db().execute("DELETE FROM test_users WHERE user_id = ?", (user_id,))
    await db().commit()


async def delete_test_orders() -> int:
    await db().execute("DELETE FROM publications WHERE order_id IN (SELECT id FROM orders WHERE is_test = 1)")
    await db().execute("DELETE FROM bookings WHERE is_test = 1")
    cur = await db().execute("DELETE FROM orders WHERE is_test = 1")
    await db().commit()
    return cur.rowcount


# ---------- экран (одно обновляемое сообщение-меню) ----------

async def get_screen(user_id: int) -> tuple[int | None, list[int]]:
    cur = await db().execute("SELECT msg_id, extra FROM screens WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    if not row:
        return None, []
    return row["msg_id"], json.loads(row["extra"] or "[]")


async def save_screen(user_id: int, msg_id: int | None, extra: list[int]) -> None:
    await db().execute(
        "INSERT INTO screens (user_id, msg_id, extra) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET msg_id = excluded.msg_id, extra = excluded.extra",
        (user_id, msg_id, json.dumps(extra)),
    )
    await db().commit()


# ---------- пользователи и язык ----------

async def get_lang(user_id: int) -> str | None:
    cur = await db().execute("SELECT lang FROM users WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    return row["lang"] if row else None


async def set_lang(user_id: int, lang: str) -> None:
    await db().execute(
        "INSERT INTO users (user_id, lang, created_at) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET lang = excluded.lang",
        (user_id, lang, now()),
    )
    await db().commit()


async def touch_user(user_id: int, first_name: str | None, username: str | None) -> None:
    """Пользователь что-то сделал в боте — значит, бот не заблокирован."""
    await db().execute(
        "INSERT INTO users (user_id, first_name, username, created_at, last_seen) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET first_name = excluded.first_name, username = excluded.username,"
        " last_seen = excluded.last_seen, blocked = 0",
        (user_id, first_name, username, now(), now()),
    )
    await db().commit()


async def set_blocked(user_id: int, blocked: bool) -> None:
    await db().execute(
        "INSERT INTO users (user_id, created_at, blocked, blocked_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET blocked = excluded.blocked, blocked_at = excluded.blocked_at",
        (user_id, now(), 1 if blocked else 0, now() if blocked else None),
    )
    await db().commit()


async def log_start(user_id: int) -> None:
    await db().execute("INSERT INTO start_log (user_id, ts) VALUES (?, ?)", (user_id, now()))
    await db().commit()


async def audience_stats() -> dict[str, int]:
    cur = await db().execute("SELECT COUNT(*), COALESCE(SUM(blocked), 0) FROM users")
    total, blocked = await cur.fetchone()
    day = now() - 86400
    cur = await db().execute(
        "SELECT COUNT(*), COALESCE(SUM(ts >= ?), 0), COALESCE(SUM(ts >= ?), 0) FROM start_log",
        (day, now() - 7 * 86400))
    starts, starts_day, starts_week = await cur.fetchone()
    cur = await db().execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (day,))
    new_day = (await cur.fetchone())[0]
    return {"users": total, "active": total - blocked, "blocked": blocked, "new_day": new_day,
            "starts": starts, "starts_day": starts_day, "starts_week": starts_week}


async def user_ids_after(after: int, limit: int, only_active: bool = True) -> list[int]:
    cur = await db().execute(
        "SELECT user_id FROM users WHERE user_id > ?" + (" AND blocked = 0" if only_active else "") +
        " ORDER BY user_id LIMIT ?", (after, limit))
    return [r[0] for r in await cur.fetchall()]


# ---------- рассылки ----------

async def create_broadcast(from_chat_id: int, message_id: int, reply_markup: str | None,
                           post_json: str | None, total: int) -> int:
    cur = await db().execute(
        "INSERT INTO broadcasts (from_chat_id, message_id, reply_markup, post_json, status, total, created_at)"
        " VALUES (?, ?, ?, ?, 'running', ?, ?)",
        (from_chat_id, message_id, reply_markup, post_json, total, now()),
    )
    await db().commit()
    return cur.lastrowid


async def get_broadcast(bid: int) -> aiosqlite.Row | None:
    cur = await db().execute("SELECT * FROM broadcasts WHERE id = ?", (bid,))
    return await cur.fetchone()


async def list_broadcasts(limit: int = 30) -> list[aiosqlite.Row]:
    cur = await db().execute("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ?", (limit,))
    return await cur.fetchall()


async def running_broadcasts() -> list[aiosqlite.Row]:
    cur = await db().execute("SELECT * FROM broadcasts WHERE status = 'running' ORDER BY id")
    return await cur.fetchall()


async def update_broadcast(bid: int, **fields: Any) -> None:
    keys = ", ".join(f"{k} = ?" for k in fields)
    await db().execute(f"UPDATE broadcasts SET {keys} WHERE id = ?", (*fields.values(), bid))
    await db().commit()


# ---------- настройки ----------

async def get_setting(key: str, default: str | None = None) -> str | None:
    cur = await db().execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = await cur.fetchone()
    return row["value"] if row else default


async def set_setting(key: str, value: str) -> None:
    await db().execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await db().commit()


async def default_price() -> tuple[int, float, float]:
    """Цена (звёзды, доллары, рубли), которая ставится автоматически найденным каналам."""
    raw = (await get_setting("default_price", "300 3.0 0")).split()
    stars, usd, rub = (raw + ["0"] * 3)[:3]
    return int(stars), float(usd), float(rub)


async def premium_emoji() -> bool:
    """Админ отметил, что у бота есть юзернейм с Fragment: без него Telegram показывает премиум-эмодзи
    в каналах обычными. От галочки зависит только то, что говорим покупателю; пост копируется одинаково."""
    return await get_setting("premium_emoji", "0") == "1"


async def known_chat_ids() -> set[int]:
    cur = await db().execute("SELECT chat_id FROM channels")
    return {r[0] for r in await cur.fetchall()}


# ---------- поддержка ----------

async def support_add(user_id: int, user_name: str | None, from_admin: bool, text: str | None,
                      media: str | None = None, src_chat_id: int | None = None, src_msg_id: int | None = None,
                      file_id: str | None = None) -> None:
    await db().execute(
        "INSERT INTO support_messages (user_id, from_admin, text, media, src_chat_id, src_msg_id, is_read,"
        " created_at, file_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, int(from_admin), text, media, src_chat_id, src_msg_id, int(from_admin), now(), file_id),
    )
    if from_admin:
        await db().execute("UPDATE support_threads SET updated_at = ? WHERE user_id = ?", (now(), user_id))
    else:
        await db().execute(
            "INSERT INTO support_threads (user_id, user_name, status, updated_at) VALUES (?, ?, 'open', ?)"
            " ON CONFLICT(user_id) DO UPDATE SET user_name = excluded.user_name, status = 'open',"
            " updated_at = excluded.updated_at",
            (user_id, user_name, now()),
        )
    await db().commit()


async def support_threads(status: str | None = None) -> list[aiosqlite.Row]:
    """Диалоги: сначала с непрочитанными, затем по свежести."""
    q = ("SELECT t.*, (SELECT COUNT(*) FROM support_messages m WHERE m.user_id = t.user_id"
         " AND m.from_admin = 0 AND m.is_read = 0) AS unread,"
         " (SELECT text FROM support_messages m WHERE m.user_id = t.user_id ORDER BY id DESC LIMIT 1) AS last_text"
         " FROM support_threads t")
    args: tuple = ()
    if status:
        q += " WHERE t.status = ?"
        args = (status,)
    q += " ORDER BY unread > 0 DESC, t.updated_at DESC"
    cur = await db().execute(q, args)
    return list(await cur.fetchall())


async def support_thread(user_id: int) -> aiosqlite.Row | None:
    cur = await db().execute("SELECT * FROM support_threads WHERE user_id = ?", (user_id,))
    return await cur.fetchone()


async def support_messages(user_id: int, limit: int = 15) -> list[aiosqlite.Row]:
    cur = await db().execute(
        "SELECT * FROM (SELECT * FROM support_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?) ORDER BY id",
        (user_id, limit),
    )
    return list(await cur.fetchall())


async def support_mark_read(user_id: int) -> None:
    await db().execute("UPDATE support_messages SET is_read = 1 WHERE user_id = ? AND from_admin = 0", (user_id,))
    await db().commit()


async def support_unread_total() -> int:
    cur = await db().execute("SELECT COUNT(*) FROM support_messages WHERE from_admin = 0 AND is_read = 0")
    return (await cur.fetchone())[0]


async def support_set_status(user_id: int, status: str) -> None:
    await db().execute("UPDATE support_threads SET status = ? WHERE user_id = ?", (status, user_id))
    await db().commit()


async def support_message(msg_id: int) -> aiosqlite.Row | None:
    cur = await db().execute("SELECT * FROM support_messages WHERE id = ?", (msg_id,))
    return await cur.fetchone()


async def list_orders(status: str | None = None, limit: int = 300) -> list[aiosqlite.Row]:
    if status:
        cur = await db().execute("SELECT * FROM orders WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit))
    else:
        cur = await db().execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
    return list(await cur.fetchall())
