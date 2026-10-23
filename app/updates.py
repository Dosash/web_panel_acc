"""Новая версия панели: последний релиз на GitHub. Проверка раз в 6 часов, результат — в памяти."""
import asyncio
import json
import logging
import re
import ssl
import time
import urllib.request
from pathlib import Path

from .config import UPDATE_CHECK, UPDATE_URL, VERSION

log = logging.getLogger("panel.update")

CHECK_EVERY = 6 * 3600
RETRY_AFTER = 15 * 60   # GitHub не ответил — спросим раньше
FORCE_EVERY = 60        # «Проверить снова» не чаще раза в минуту: у GitHub лимит 60 запросов в час
# в контейнере панель обновляется пересборкой образа, без него — git pull в папке панели
DOCKER = Path("/.dockerenv").exists()

_state: dict = {"at": 0.0, "release": None, "error": ""}
_lock = asyncio.Lock()


def parse_version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def _ssl_context() -> ssl.SSLContext:
    # в программе под macOS у Python нет системных корневых сертификатов — берём из certifi
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch() -> dict:
    req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": f"TG-Panel/{VERSION}",
                                                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=15, context=_ssl_context()) as r:
        data = json.load(r)
    return {"latest": (data.get("tag_name") or "").lstrip("v"), "notes": (data.get("body") or "").strip()[:20000],
            "page": data.get("html_url") or "", "published_at": data.get("published_at") or ""}


async def status(force: bool = False) -> dict:
    base = {"current": VERSION, "enabled": UPDATE_CHECK, "docker": DOCKER}
    if not UPDATE_CHECK:
        return base | {"available": False}
    async with _lock:
        age = time.time() - _state["at"]
        if age > (CHECK_EVERY if _state["release"] else RETRY_AFTER) or (force and age > FORCE_EVERY):
            try:
                _state["release"], _state["error"] = await asyncio.to_thread(_fetch), ""
            except Exception as e:  # сеть, GitHub, лимит запросов — панель работает и без проверки
                log.warning("Не удалось проверить обновления: %s", e)
                _state["error"] = str(e)
            _state["at"] = time.time()
    rel = _state["release"] or {}
    latest = rel.get("latest", "")
    return base | rel | {"available": bool(latest) and parse_version(latest) > parse_version(VERSION),
                         "checked_at": int(_state["at"]), "error": _state["error"]}
