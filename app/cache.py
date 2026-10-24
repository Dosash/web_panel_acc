"""Уборка data/cache и data/tmp.

Медиа из чатов (`m_*`) и аватары (`a_*`) складываются в data/cache и раньше не удалялись никогда —
на сервере с активной перепиской папка росла на гигабайты. Теперь при старте и раз в несколько часов:
медиа старше MEDIA_TTL и аватары старше AVATAR_TTL удаляются, а если кэш всё ещё больше CACHE_MAX_MB —
удаляются самые старые файлы, пока не уложимся. data/tmp — папки загрузок, оставшиеся после аварийного
завершения (в норме они удаляются сразу после запроса).
"""
import asyncio
import logging
import shutil
import time
from pathlib import Path

from .config import CACHE_DIR, CACHE_MAX_MB, TMP_DIR

log = logging.getLogger("panel.cache")

MEDIA_TTL = 7 * 86400
AVATAR_TTL = 30 * 86400
TMP_TTL = 3600
EVERY = 6 * 3600


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _remove(path: Path) -> int:
    """Удаляет файл или папку, возвращает освобождённые байты (0, если не вышло)."""
    try:
        if path.is_dir():
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            shutil.rmtree(path, ignore_errors=True)
            return size
        size = path.stat().st_size
        path.unlink()
        return size
    except OSError:
        return 0


def clean_tmp(now: float | None = None) -> int:
    """Загрузки старше TMP_TTL: после аварийного завершения панели их никто не удалит."""
    now = now or time.time()
    removed = 0
    for entry in TMP_DIR.iterdir() if TMP_DIR.exists() else ():
        if now - _mtime(entry) > TMP_TTL:
            _remove(entry)
            removed += 1
    return removed


def clean_cache(now: float | None = None, max_bytes: int | None = None) -> tuple[int, int]:
    """Возвращает (удалено файлов, освобождено байт)."""
    now = now or time.time()
    limit = CACHE_MAX_MB * 1024 * 1024 if max_bytes is None else max_bytes
    files: list[tuple[float, int, Path]] = []
    for f in CACHE_DIR.iterdir() if CACHE_DIR.exists() else ():
        if not f.is_file():
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        files.append((st.st_mtime, st.st_size, f))
    removed = freed = 0
    kept: list[tuple[float, int, Path]] = []
    for mtime, size, f in files:
        ttl = AVATAR_TTL if f.name.startswith("a_") else MEDIA_TTL
        if now - mtime > ttl:
            freed += _remove(f)
            removed += 1
        else:
            kept.append((mtime, size, f))
    total = sum(size for _, size, _ in kept)
    if limit and total > limit:
        for _mtime, size, f in sorted(kept):   # самые старые — первыми
            if total <= limit:
                break
            freed += _remove(f)
            removed += 1
            total -= size
    return removed, freed


def clean_all() -> None:
    try:
        tmp = clean_tmp()
        removed, freed = clean_cache()
        if tmp or removed:
            log.info("Уборка: временных папок %s, файлов кэша %s (%.1f МБ)", tmp, removed, freed / 1e6)
    except Exception:   # уборка не должна ронять панель
        log.exception("Уборка кэша не удалась")


async def run_forever() -> None:
    while True:
        await asyncio.to_thread(clean_all)
        await asyncio.sleep(EVERY)
