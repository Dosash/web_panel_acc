"""Housekeeping of the uploads directory and the statistics tables (run hourly by the scheduler).

Nothing else ever deletes an upload: a replaced picture, an abandoned draft, a deleted post or a
retried request leave their files behind, and the Telegram preview cache (``tg_*``) and temp files
of a killed upload (``*.part``) stay too. `sweep_uploads` removes, in the top level of
`uploads_dir` only (the ``avatars/`` subdirectory belongs to bots.posts.services.avatars):

* uploads (``<32 hex>.<ext>``) older than UPLOAD_MAX_AGE that no post refers to any more
  (`db.referenced_media_paths`, one query) — a fresh upload of a post being composed is kept;
* ``tg_*`` preview cache files older than CACHE_MAX_AGE (downloaded again when needed);
* ``.*.part`` temp files older than PART_MAX_AGE.

`prune_history` drops statistics rows older than HISTORY_MAX_AGE (the statistics look back at most
a year — bots.posts.services.stats.MAX_DAYS). Both only log their failures.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from bots.posts.media import UPLOAD_NAME_RE

log = logging.getLogger(__name__)

UPLOAD_MAX_AGE = 24 * 3600  # an unreferenced upload is kept this long (a draft still being composed)
CACHE_MAX_AGE = 7 * 86400  # tg_* preview cache files (by mtime)
PART_MAX_AGE = 3600  # *.part temp files of uploads / downloads cut by a crash
HISTORY_MAX_AGE = 400 * 86400  # statistics rows (member_snapshots, member_events, channel_posts)

_CACHE_NAME_RE = re.compile(r"^tg_[0-9a-f]{16}\.[a-z0-9]{1,5}$")
_PART_NAME_RE = re.compile(r"^\..+\.part$")


def _entries(directory: Path) -> list[tuple[str, float]]:
    """(name, mtime) of the regular files in the top level of `directory` ([] when it is missing)."""
    result = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                try:
                    if entry.is_file(follow_symlinks=False):
                        result.append((entry.name, entry.stat(follow_symlinks=False).st_mtime))
                except OSError:
                    continue
    except OSError:
        return []
    return result


def _remove(paths: list[Path]) -> int:
    removed = 0
    for path in paths:
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
        except OSError as exc:
            log.warning("Не удалось удалить файл %s: %s", path.name, exc)
    return removed


def stale_files(entries: list[tuple[str, float]], referenced: set[str], now_ts: float) -> list[str]:
    """Names of the files `sweep_uploads` removes (pure, for tests)."""
    stale = []
    for name, mtime in entries:
        age = now_ts - mtime
        if UPLOAD_NAME_RE.fullmatch(name):
            if age > UPLOAD_MAX_AGE and name not in referenced:
                stale.append(name)
        elif _CACHE_NAME_RE.fullmatch(name):
            if age > CACHE_MAX_AGE:
                stale.append(name)
        elif _PART_NAME_RE.fullmatch(name) and age > PART_MAX_AGE:
            stale.append(name)
    return stale


async def sweep_uploads(db: Any, uploads_dir: Path | str) -> int:
    """Remove stale files from the uploads directory (see the module docstring). Returns how many."""
    directory = Path(uploads_dir)
    entries = await asyncio.to_thread(_entries, directory)
    if not entries:
        return 0
    referenced = await db.referenced_media_paths()
    stale = stale_files(entries, referenced, time.time())
    if not stale:
        return 0
    removed = await asyncio.to_thread(_remove, [directory / name for name in stale])
    if removed:
        log.info("Загрузки: удалено %s устаревших файлов", removed)
    return removed


async def prune_history(db: Any, *, max_age: float = HISTORY_MAX_AGE) -> int:
    """Drop statistics rows older than `max_age` seconds. Returns how many rows were removed."""
    removed = await db.prune_history(int(time.time() - max_age))
    if removed:
        log.info("Статистика: удалено %s записей старше %s дней", removed, int(max_age // 86400))
    return removed
