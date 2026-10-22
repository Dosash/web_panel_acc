"""SQLite-хранилище аккаунтов. Строка сессии хранится только в зашифрованном виде."""
import json
import sqlite3
import time
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


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
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
