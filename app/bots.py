"""Встроенные боты: бот постинга (bots/posts) и бот рекламы (bots/ads).

Каждый бот — отдельный процесс со своей веб-панелью на 127.0.0.1 и свободном порту. Панель запускает
его, перезапускает после падения и проксирует его веб-панель по адресу <WEB_PREFIX>/bots/<имя>/
(вход — общий, паролем TG Panel). Настройки бота для запуска лежат в data/bots/<имя>/bot.json, там же
его база и журнал: token, admin_ids, timezone, enabled, public_url (адрес его панели снаружи — для ссылок
из бота) и env — дополнительные переменные окружения бота (например, ключи оплаты бота рекламы,
перенесённые из его прежнего .env). Токен — секрет: наружу отдаём только «…abcd».
"""
import asyncio
import collections
import json
import logging
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

from .config import BASE_DIR, DATA_DIR, WEB_PREFIX

log = logging.getLogger("panel.bots")

BOTS_DIR = DATA_DIR / "bots"
TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
LOG_LIMIT = 5 * 1024 * 1024  # bot.log больше этого — начинаем заново
STOP_TIMEOUT = 75  # бот постинга даёт идущим публикациям до ~72 с (bots/posts/__main__.py)
READY_TIMEOUT = 60
PROBE_TIMEOUT = 8  # /api/health бота постинга при недоступном Telegram отвечает до ~5 с
RESTART_DELAYS = (2, 5, 15, 30, 60)
# Переменные панели и ботов, которые не должны попасть к боту из окружения панели
_ENV_DROP = re.compile(r"^(WEB_|PANEL_|HUB_URL$|BOT_TOKEN$|ADMIN_IDS$|DB_PATH$|UPLOADS_DIR$|CRYPTOPAY_|XROCKET_|"
                       r"FREEKASSA_|TEST_CHANNEL_ID$|TRUST_PROXY$|PORT$|HOST$)")


@dataclass(frozen=True)
class Kind:
    name: str
    title: str
    about: str


KINDS = {
    "posts": Kind("posts", "Бот постинга",
                  "Публикация постов в ваши каналы: Markdown, медиа, цветные кнопки, отложенные посты, контент-план."),
    "ads": Kind("ads", "Бот рекламы",
                "Продажа рекламы в ваших каналах: каталог с ценами, модерация, оплата и автопубликация."),
}


def mask(token: str) -> str:
    return "…" + token[-4:] if token else ""


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def check_token(token: str) -> dict:
    """getMe: бот, которому принадлежит токен. ValueError с понятным текстом, если токен не годится."""
    token = token.strip()
    if not TOKEN_RE.fullmatch(token):
        raise ValueError("Это не токен бота: он выглядит как 123456789:AAE… — возьмите его у @BotFather")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(f"https://api.telegram.org/bot{token}/getMe") as r:
                data = await r.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError):
        raise ValueError("Не удалось связаться с Telegram — проверьте интернет на сервере") from None
    if not data.get("ok"):
        raise ValueError("Telegram не принял токен — возьмите актуальный у @BotFather")
    return data["result"]


@dataclass
class BotProcess:
    kind: Kind
    dir: Path = field(init=False)
    cfg: dict = field(default_factory=dict)
    port: int = 0
    proc: subprocess.Popen | None = None
    status: str = "off"  # off | starting | running | error
    error: str = ""
    tail: collections.deque = field(default_factory=lambda: collections.deque(maxlen=200))
    key: str = ""  # TG_PANEL_KEY: без него панель бота не отвечает (bots/*/web), новый на каждый запуск
    _task: asyncio.Task | None = None
    _stopping: bool = False
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self):
        self.dir = BOTS_DIR / self.kind.name
        self.cfg = self._load()

    # ---------- настройки ----------

    @property
    def cfg_path(self) -> Path:
        return self.dir / "bot.json"

    def _load(self) -> dict:
        try:
            return json.loads(self.cfg_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def save(self, **changes) -> None:
        self.cfg.update(changes)
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.cfg_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), "utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.cfg_path)

    @property
    def configured(self) -> bool:
        return bool(self.cfg.get("token"))

    @property
    def prefix(self) -> str:
        return f"{WEB_PREFIX}/bots/{self.kind.name}"

    def public(self) -> dict:
        return {
            "name": self.kind.name, "title": self.kind.title, "about": self.kind.about,
            "configured": self.configured, "enabled": bool(self.cfg.get("enabled")),
            "status": self.status, "error": self.error,
            "username": self.cfg.get("username", ""), "bot_name": self.cfg.get("bot_name", ""),
            "token": mask(self.cfg.get("token", "")), "admin_ids": self.cfg.get("admin_ids", []),
            "timezone": self.cfg.get("timezone", "Europe/Moscow"),
        }

    # ---------- процесс ----------

    def _command(self) -> list[str]:
        if getattr(sys, "frozen", False):  # программа для ПК: тот же exe, режим бота
            return [sys.executable, "--bot", self.kind.name]
        return [sys.executable, "-m", "bots", self.kind.name]

    def _env(self) -> dict:
        env = {k: v for k, v in os.environ.items() if not _ENV_DROP.match(k)}
        env.update({k: str(v) for k, v in (self.cfg.get("env") or {}).items()})
        admins = ",".join(str(i) for i in self.cfg.get("admin_ids", []))
        tz = self.cfg.get("timezone") or "Europe/Moscow"
        env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", TG_PANEL_CHILD="1", TG_PANEL_KEY=self.key,
                   BOT_TOKEN=self.cfg["token"], ADMIN_IDS=admins, TIMEZONE=tz,
                   DB_PATH=str(self.dir / "bot.db"), LOG_LEVEL="INFO")
        if self.kind.name == "posts":
            env.update(WEB_HOST="127.0.0.1", WEB_PORT=str(self.port), WEB_PREFIX=self.prefix,
                       WEB_PASSWORD="", HUB_URL="", TRUST_PROXY="0", UPLOADS_DIR=str(self.dir / "uploads"),
                       WEB_PUBLIC_URL=self.cfg.get("public_url", ""))
        else:
            env.update(PANEL_HOST="127.0.0.1", PANEL_PORT=str(self.port), PANEL_PREFIX=self.prefix,
                       PANEL_PASSWORD="")
        if not getattr(sys, "frozen", False):
            env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(BASE_DIR), env.get("PYTHONPATH", "")]))
        return env

    def _spawn(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.port = free_port()
        self.key = secrets.token_urlsafe(32)
        logfile = self.dir / "bot.log"
        if logfile.exists() and logfile.stat().st_size > LOG_LIMIT:
            logfile.unlink()
        extra = {}
        if sys.platform == "win32":
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            extra["start_new_session"] = True  # Ctrl+C в терминале панели не должен доходить до бота мимо панели
        self.proc = subprocess.Popen(self._command(), cwd=self.dir, env=self._env(), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **extra)
        threading.Thread(target=self._pump, args=(self.proc, logfile), name=f"bot-{self.kind.name}-log",
                         daemon=True).start()

    def _pump(self, proc: subprocess.Popen, logfile: Path) -> None:
        """Вывод бота — в data/bots/<имя>/bot.log, в журнал панели и в хвост для экрана настройки."""
        blog = logging.getLogger(f"bot.{self.kind.name}")
        with open(logfile, "a", encoding="utf-8") as f:
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").rstrip()
                if not line:
                    continue
                f.write(line + "\n")
                f.flush()
                self.tail.append(line)
                blog.info("%s", line)

    async def _wait_ready(self) -> bool:
        """Ждём, пока панель бота ответит; False — за READY_TIMEOUT не ответила или процесс завершился."""
        url = f"http://127.0.0.1:{self.port}{self.prefix}/api/health"
        deadline = time.monotonic() + READY_TIMEOUT
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=PROBE_TIMEOUT)) as s:
            while time.monotonic() < deadline and self.proc and self.proc.poll() is None:
                try:
                    async with s.get(url, headers={"X-TG-Panel-Key": self.key}) as r:
                        if r.status < 500:
                            self._remember_identity(await r.json(content_type=None))
                            return True
                except (aiohttp.ClientError, TimeoutError, ValueError):
                    pass
                await asyncio.sleep(0.5)
        return False

    def _remember_identity(self, health: dict) -> None:
        """Имя бота из его /api/health: токен могли сменить и в панели самого бота."""
        username = str(health.get("bot") or "").lstrip("@")
        if username and username != self.cfg.get("username"):
            self.save(username=username, bot_name="")

    async def _until_ready(self) -> None:
        while self.proc and self.proc.poll() is None:
            if await self._wait_ready():
                self.status, self.error = "running", ""
                log.info("%s запущен (порт %s)", self.kind.title, self.port)
                return
            if self.proc.poll() is None:
                # бот рекламы открывает панель только после ответа Telegram — при плохой сети ждём дальше
                self.status = "error"
                self.error = "Бот запущен, но его панель не отвечает — проверьте связь сервера с Telegram. " \
                             + self._last_error()

    def _last_error(self) -> str:
        for line in reversed(self.tail):
            if any(w in line for w in ("Error", "ERROR", "error", "Exit", "не задан", "не принял")):
                return line[-300:]
        return self.tail[-1][-300:] if self.tail else ""

    async def _supervise(self) -> None:
        failures = 0
        while not self._stopping:
            self.status, self.error = "starting", ""
            started = time.monotonic()
            try:
                self._spawn()
            except OSError as e:
                self.status, self.error = "error", f"Не удалось запустить бота: {e}"
                log.error("%s: %s", self.kind.title, self.error)
                return
            ready = asyncio.create_task(self._until_ready())
            try:
                code = await asyncio.to_thread(self.proc.wait)
            finally:
                ready.cancel()
            if self._stopping:
                break
            failures = 0 if time.monotonic() - started > 120 else failures + 1
            delay = RESTART_DELAYS[min(failures, len(RESTART_DELAYS) - 1)]
            # бот рекламы перезапускает себя сам после смены токена в своей панели — один выход не ошибка
            self.status = "error" if failures > 1 else "starting"
            self.error = self._last_error() if failures > 1 else ""
            log.warning("%s остановился (код %s), перезапуск через %s с", self.kind.title, code, delay)
            await asyncio.sleep(delay)

    # Запуск и остановка — под замком: иначе «Выключить» во время перезапуска могло оставить второй
    # процесс бота с тем же токеном
    def _start(self) -> None:
        if not self.configured or (self._task and not self._task.done()):
            return
        self._stopping = False
        self.status, self.error = "starting", ""
        self.tail.clear()
        self._task = asyncio.create_task(self._supervise())

    @staticmethod
    async def _end(proc: subprocess.Popen | None) -> None:
        if proc and proc.poll() is None:
            proc.terminate()  # SIGTERM: бот корректно завершает публикации (под Windows — сразу)
            try:
                await asyncio.wait_for(asyncio.to_thread(proc.wait), STOP_TIMEOUT)
            except TimeoutError:
                proc.kill()
                await asyncio.to_thread(proc.wait)
        if proc and proc.stdin and not proc.stdin.closed:
            try:
                proc.stdin.close()
            except OSError:
                pass

    async def _stop(self) -> None:
        self._stopping = True
        task, self._task = self._task, None
        await self._end(self.proc)
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        await self._end(self.proc)  # процесс, запущенный задачей, пока мы ждали первый
        self.status, self.error, self.port = "off", "", 0

    def _forget_own_settings(self, keys: list[str]) -> None:
        """Токен, администраторы и пояс, заданные в панели самого бота, важнее переменных окружения.
        Когда их меняют в TG Panel, прежние значения из базы бота убираем — иначе новые не применятся."""
        names = {"posts": {"token": "bot_token", "timezone": "timezone"},
                 "ads": {"token": "cfg:BOT_TOKEN", "admin_ids": "cfg:ADMIN_IDS", "timezone": "cfg:TIMEZONE"}}
        rows = [names[self.kind.name][k] for k in keys if k in names[self.kind.name]]
        db = self.dir / "bot.db"
        if not rows or not db.exists():
            return
        with sqlite3.connect(db) as conn:
            conn.executemany("DELETE FROM settings WHERE key = ?", [(r,) for r in rows])

    async def start(self) -> None:
        async with self._lock:
            self._start()

    async def stop(self) -> None:
        async with self._lock:
            await self._stop()

    async def restart(self) -> None:
        async with self._lock:
            await self._stop()
            self._start()

    async def reconfigure(self, changes: dict) -> None:
        """Новые настройки запуска из TG Panel: остановить, сохранить, (пере)запустить."""
        async with self._lock:
            await self._stop()
            changed = [k for k in ("token", "admin_ids", "timezone") if k in changes and changes[k] != self.cfg.get(k)]
            self.save(**changes)
            try:
                self._forget_own_settings(changed)
            except sqlite3.Error as e:
                log.warning("%s: не удалось сбросить настройки в базе бота: %s", self.kind.title, e)
            self._start()


bots = {name: BotProcess(kind) for name, kind in KINDS.items()}


class NoSuchBot(Exception):
    pass


def get(name: str) -> BotProcess:
    bot = bots.get(name)
    if not bot:
        raise NoSuchBot(name)
    return bot


_background: set[asyncio.Task] = set()


def in_background(coro) -> None:
    """Остановка бота занимает до STOP_TIMEOUT: запрос из интерфейса не ждёт её (таймаут nginx — 60 с)."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background_done)


def _background_done(task: asyncio.Task) -> None:
    _background.discard(task)
    if not task.cancelled() and task.exception() is not None:
        log.error("Фоновая операция с ботом не удалась", exc_info=task.exception())


async def start_all() -> None:
    for bot in bots.values():
        if bot.configured and bot.cfg.get("enabled"):
            await bot.start()


async def stop_all() -> None:
    await asyncio.gather(*(bot.stop() for bot in bots.values()), return_exceptions=True)
