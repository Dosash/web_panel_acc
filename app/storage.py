"""SQLite-хранилище аккаунтов. Строка сессии хранится только в зашифрованном виде."""
import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from cryptography.fernet import Fernet

from .config import DB_PATH, FERNET_KEY

_fernet = Fernet(FERNET_KEY)

COLORS = ["#4f9cf9", "#2fbf71", "#f5a524", "#e5484d", "#a36cf7",
          "#12a4b8", "#f76b15", "#d6409f", "#8d9b2a", "#6e56cf"]


@dataclass
class Account:
    id: int
    name: str
    color: str
    session: str          # расшифрованная StringSession
    api: dict             # параметры клиента (api_id, device_model, ...)
    proxy: str = ""
    user_id: int | None = None
    phone: str = ""
    username: str = ""
    full_name: str = ""
    created_at: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {
            "id": self.id, "name": self.name, "color": self.color, "proxy": self.proxy,
            "user_id": self.user_id, "phone": self.phone, "username": self.username,
            "full_name": self.full_name, "created_at": self.created_at,
        }


@contextmanager
def _conn():
    """Соединение на одну операцию: коммит при выходе, откат при ошибке и всегда close() —
    голый `with sqlite3.connect()` соединение не закрывает. timeout — ждать, если база занята."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as c:
        # WAL: чтение не ждёт записи, файл базы не портится при обрыве питания посреди записи
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                color TEXT NOT NULL,
                session_enc BLOB NOT NULL,
                api_json TEXT NOT NULL,
                proxy TEXT NOT NULL DEFAULT '',
                user_id INTEGER,
                phone TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                full_name TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL
            )""")
        # Папки панели: в одной папке могут лежать чаты разных аккаунтов
        c.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS folder_items (
                folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
                account_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                added_at REAL NOT NULL,
                PRIMARY KEY (folder_id, account_id, chat_id)
            )""")
        # Бот, который публикует посты с кнопками в канал (у обычного аккаунта кнопки не работают)
        c.execute("""
            CREATE TABLE IF NOT EXISTS post_bots (
                account_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                bot_id INTEGER NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                token_enc BLOB NOT NULL,
                session_enc BLOB,
                PRIMARY KEY (account_id, chat_id)
            )""")


def _row(r: sqlite3.Row) -> Account:
    return Account(
        id=r["id"], name=r["name"], color=r["color"],
        session=_fernet.decrypt(r["session_enc"]).decode(),
        api=json.loads(r["api_json"]), proxy=r["proxy"], user_id=r["user_id"],
        phone=r["phone"], username=r["username"], full_name=r["full_name"],
        created_at=r["created_at"],
    )


def list_accounts() -> list[Account]:
    with _conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM accounts ORDER BY id")]


def count_accounts() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]


def get_account(account_id: int) -> Account | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return _row(r) if r else None


def find_by_user_id(user_id: int) -> Account | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
    return _row(r) if r else None


def add_account(name: str, session: str, api: dict, proxy: str, me: dict) -> Account:
    with _conn() as c:
        count = c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        cur = c.execute(
            """INSERT INTO accounts (name, color, session_enc, api_json, proxy,
                   user_id, phone, username, full_name, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, COLORS[count % len(COLORS)], _fernet.encrypt(session.encode()),
             json.dumps(api), proxy, me.get("id"), me.get("phone", ""),
             me.get("username", ""), me.get("full_name", ""), time.time()),
        )
        account_id = cur.lastrowid
    return get_account(account_id)


def update_account(account_id: int, **fields) -> Account | None:
    allowed = {"name", "color", "proxy", "phone", "username", "full_name"}
    sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "session" in fields:
        sets["session_enc"] = _fernet.encrypt(fields["session"].encode())
    if "api" in fields:
        sets["api_json"] = json.dumps(fields["api"])
    if sets:
        cols = ", ".join(f"{k} = ?" for k in sets)
        with _conn() as c:
            c.execute(f"UPDATE accounts SET {cols} WHERE id = ?", (*sets.values(), account_id))
    return get_account(account_id)


def delete_account(account_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        c.execute("DELETE FROM folder_items WHERE account_id = ?", (account_id,))
        c.execute("DELETE FROM post_bots WHERE account_id = ?", (account_id,))


# ---------- папки ----------

def folder_items(folder_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute("SELECT account_id, chat_id FROM folder_items WHERE folder_id = ? ORDER BY added_at",
                         (folder_id,)).fetchall()
    return [dict(r) for r in rows]


def get_folder(folder_id: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT id, name, position FROM folders WHERE id = ?", (folder_id,)).fetchone()
    return {**dict(r), "items": folder_items(folder_id)} if r else None


def list_folders() -> list[dict]:
    with _conn() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM folders ORDER BY position, id")]
    return [get_folder(i) for i in ids]


def create_folder(name: str) -> dict:
    with _conn() as c:
        pos = c.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM folders").fetchone()[0]
        cur = c.execute("INSERT INTO folders (name, position, created_at) VALUES (?, ?, ?)",
                        (name, pos, time.time()))
        folder_id = cur.lastrowid
    return get_folder(folder_id)


def rename_folder(folder_id: int, name: str) -> dict | None:
    with _conn() as c:
        c.execute("UPDATE folders SET name = ? WHERE id = ?", (name, folder_id))
    return get_folder(folder_id)


def delete_folder(folder_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM folder_items WHERE folder_id = ?", (folder_id,))
        c.execute("DELETE FROM folders WHERE id = ?", (folder_id,))


def add_folder_item(folder_id: int, account_id: int, chat_id: int) -> None:
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO folder_items (folder_id, account_id, chat_id, added_at) VALUES (?, ?, ?, ?)",
                  (folder_id, account_id, chat_id, time.time()))


def remove_folder_item(folder_id: int, account_id: int, chat_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM folder_items WHERE folder_id = ? AND account_id = ? AND chat_id = ?",
                  (folder_id, account_id, chat_id))


# ---------- боты для постов ----------

def get_post_bot(account_id: int, chat_id: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM post_bots WHERE account_id = ? AND chat_id = ?", (account_id, chat_id)).fetchone()
    if not r:
        return None
    return {"bot_id": r["bot_id"], "username": r["username"], "token": _fernet.decrypt(r["token_enc"]).decode(),
            "session": _fernet.decrypt(r["session_enc"]).decode() if r["session_enc"] else ""}


def set_post_bot(account_id: int, chat_id: int, bot_id: int, username: str, token: str, session: str) -> None:
    with _conn() as c:
        c.execute("""INSERT OR REPLACE INTO post_bots (account_id, chat_id, bot_id, username, token_enc, session_enc)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (account_id, chat_id, bot_id, username, _fernet.encrypt(token.encode()),
                   _fernet.encrypt(session.encode()) if session else None))


def delete_post_bot(account_id: int, chat_id: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM post_bots WHERE account_id = ? AND chat_id = ?", (account_id, chat_id))
