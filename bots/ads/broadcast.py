"""Рассылка рекламного поста всем пользователям бота (из веб-панели).

Черновик — это сообщение в чате первого админа с ботом: либо пост, который админ прислал боту (через @justpost,
пересылкой или просто написал), либо пост, собранный в панели и отправленный ему ботом. Рассылка копирует это
сообщение каждому пользователю (copy_message), ~20 сообщений в секунду — ниже лимита Telegram (30/с).
Прогресс пишется в таблицу broadcasts после каждого получателя, поэтому после рестарта рассылка продолжается.
"""
import asyncio
import json
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import Message

from bots.ads import db
from bots.ads.config import config
from bots.ads.orders import buttons_markup, copy_post, copy_with_markup, notify_admins, post_snapshot

log = logging.getLogger(__name__)

DRAFT_KEY = "broadcast_draft"
CAPTURE_SECONDS = 600
SEND_DELAY = 0.05          # 20 сообщений в секунду
CHECK_DELAY = 0.04

_capture_until = 0.0        # до какого времени ждём пост от админа в Telegram
_tasks: dict[int, asyncio.Task] = {}
_check = {"running": False, "done": 0, "total": 0, "blocked": 0, "finished_at": None}


class BroadcastError(Exception):
    pass


# ---------- кнопки ----------
def parse_buttons(text: str) -> list[list[dict]]:
    """Строка — ряд кнопок: «Текст | https://ссылка», несколько кнопок в ряду — через «;;»."""
    rows = []
    for n, line in enumerate((text or "").splitlines(), 1):
        if not line.strip():
            continue
        row = []
        for part in line.split(";;"):
            if "|" not in part:
                raise BroadcastError(f"Кнопки, строка {n}: нужно «Текст | ссылка»")
            label, url = (x.strip() for x in part.rsplit("|", 1))
            if not label or not url.startswith(("https://", "http://", "tg://")):
                raise BroadcastError(f"Кнопки, строка {n}: нужен текст и ссылка, начинающаяся с https://")
            row.append({"text": label[:64], "url": url})
        rows.append(row)
    return rows


def buttons_text(rows: list[list[dict]]) -> str:
    return "\n".join(" ;; ".join(f"{b['text']} | {b['url']}" for b in r) for r in rows)


# ---------- черновик ----------
async def get_draft() -> dict | None:
    raw = await db.get_setting(DRAFT_KEY)
    return json.loads(raw) if raw else None


async def save_draft(message: Message, source: str, buttons: list[list[dict]] | None = None) -> dict:
    post = json.loads(post_snapshot(message))
    if buttons is not None:
        post["buttons"] = buttons
    draft = {"from_chat_id": message.chat.id, "message_id": message.message_id, "post": post,
             "source": source, "created_at": db.now()}
    await db.set_setting(DRAFT_KEY, json.dumps(draft, ensure_ascii=False))
    return draft


async def set_draft_buttons(rows: list[list[dict]]) -> dict:
    draft = await get_draft()
    if not draft:
        raise BroadcastError("Черновика нет")
    # цвет и эмодзи кнопок из поста в текстовом формате не видны — у неизменённых кнопок сохраняем их
    old = {(b["text"], b["url"]): b for r in draft["post"].get("buttons") or [] for b in r}
    draft["post"]["buttons"] = [[{**old.get((b["text"], b["url"]), {}), **b} for b in r] for r in rows]
    await db.set_setting(DRAFT_KEY, json.dumps(draft, ensure_ascii=False))
    return draft


async def clear_draft() -> None:
    await db.set_setting(DRAFT_KEY, "")


async def send_preview(bot: Bot, draft: dict) -> int:
    """Копия черновика всем админам — посмотреть, как пост увидят пользователи."""
    sent = 0
    for admin_id in config.admin_ids:
        try:
            await copy_with_markup(bot, admin_id, draft["from_chat_id"], draft["message_id"],
                                   buttons_markup(draft["post"].get("buttons") or []))
            sent += 1
        except Exception as e:
            log.warning("broadcast preview to %s failed: %s", admin_id, e)
    return sent


# ---------- пост из Telegram ----------
def start_capture() -> int:
    global _capture_until
    _capture_until = time.time() + CAPTURE_SECONDS
    return int(_capture_until)


def stop_capture() -> None:
    global _capture_until
    _capture_until = 0.0


def capture_active() -> bool:
    return time.time() < _capture_until


def capture_until() -> int | None:
    return int(_capture_until) if capture_active() else None


# ---------- рассылка ----------
def is_running() -> bool:
    return any(not t.done() for t in _tasks.values())


async def start(bot: Bot) -> int:
    draft = await get_draft()
    if not draft:
        raise BroadcastError("Сначала подготовьте пост")
    if is_running() or await db.running_broadcasts():
        raise BroadcastError("Рассылка уже идёт — дождитесь окончания или остановите её")
    total = (await db.audience_stats())["active"]
    if not total:
        raise BroadcastError("Некому отправлять: активных пользователей нет")
    markup = buttons_markup(draft["post"].get("buttons") or [])
    bid = await db.create_broadcast(draft["from_chat_id"], draft["message_id"],
                                    markup.model_dump_json(exclude_none=True) if markup else None,
                                    json.dumps(draft["post"], ensure_ascii=False), total)
    _tasks[bid] = asyncio.create_task(_run(bot, bid))
    return bid


async def stop(bid: int) -> None:
    b = await db.get_broadcast(bid)
    if not b or b["status"] != "running":
        raise BroadcastError("Эта рассылка не идёт")
    await db.update_broadcast(bid, status="stopped", finished_at=db.now())
    task = _tasks.get(bid)
    if task and not task.done():
        task.cancel()


def resume_all(bot: Bot) -> None:
    """После рестарта — продолжить незаконченные рассылки."""
    async def go():
        for b in await db.running_broadcasts():
            log.info("продолжаю рассылку #%s с user_id > %s", b["id"], b["cursor"])
            _tasks[b["id"]] = asyncio.create_task(_run(bot, b["id"]))
    return asyncio.create_task(go())


async def _send(bot: Bot, b, uid: int) -> str:
    """sent | blocked | failed | fatal:<текст>"""
    for _ in range(3):
        try:
            await copy_post(bot, b, uid)
            return "sent"
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramForbiddenError:
            return "blocked"
        except TelegramBadRequest as e:
            msg = str(e).lower()
            if "message to copy not found" in msg or "message_id_invalid" in msg:
                return "fatal:исходный пост удалён из чата с ботом — подготовьте пост заново"
            if "chat not found" in msg or "user is deactivated" in msg or "peer_id_invalid" in msg:
                return "blocked"
            log.warning("broadcast #%s → %s: %s", b["id"], uid, e)
            return "failed"
        except Exception as e:
            log.warning("broadcast #%s → %s: %s", b["id"], uid, e)
            return "failed"
    return "failed"


async def _run(bot: Bot, bid: int) -> None:
    try:
        b = await db.get_broadcast(bid)
        counts = {"sent": b["sent"], "blocked": b["blocked"], "failed": b["failed"]}
        cursor = b["cursor"]
        while True:
            ids = await db.user_ids_after(cursor, 200)
            if not ids:
                break
            for uid in ids:
                res = await _send(bot, b, uid)
                if res.startswith("fatal:"):
                    await db.update_broadcast(bid, status="error", error=res[6:], finished_at=db.now(), **counts)
                    await notify_admins(bot, f"⚠️ Рассылка #{bid} остановлена: {res[6:]}.")
                    return
                counts[res] += 1
                if res == "blocked":
                    await db.set_blocked(uid, True)
                cursor = uid
                await db.update_broadcast(bid, cursor=cursor, **counts)
                await asyncio.sleep(SEND_DELAY)
        await db.update_broadcast(bid, status="done", finished_at=db.now(), **counts)
        await notify_admins(bot, f"📣 Рассылка #{bid} завершена.\nДоставлено: <b>{counts['sent']}</b>, "
                                 f"заблокировали бота: {counts['blocked']}, ошибок: {counts['failed']}.")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.exception("broadcast #%s failed", bid)
        await db.update_broadcast(bid, status="error", error=str(e)[:500], finished_at=db.now())


# ---------- проверка, кто заблокировал бота ----------
def check_state() -> dict:
    return dict(_check)


async def start_check(bot: Bot) -> None:
    if _check["running"]:
        raise BroadcastError("Проверка уже идёт")
    total = (await db.audience_stats())["users"]
    _check.update(running=True, done=0, total=total, blocked=0, finished_at=None)
    _check["task"] = asyncio.create_task(_run_check(bot))   # ссылка — иначе задачу может собрать GC


async def _run_check(bot: Bot) -> None:
    """sendChatAction ничего не присылает в чат, но для заблокировавших бота возвращает ошибку 403."""
    cursor = 0
    try:
        while True:
            ids = await db.user_ids_after(cursor, 200, only_active=False)
            if not ids:
                break
            for uid in ids:
                cursor = uid
                blocked = None
                for _ in range(3):
                    try:
                        await bot.send_chat_action(uid, "typing")
                        blocked = False
                        break
                    except TelegramRetryAfter as e:
                        await asyncio.sleep(e.retry_after + 1)
                    except TelegramForbiddenError:
                        blocked = True
                        break
                    except TelegramBadRequest as e:
                        msg = str(e).lower()
                        blocked = True if ("chat not found" in msg or "deactivated" in msg) else None
                        break
                    except Exception:
                        break
                if blocked is not None:
                    await db.set_blocked(uid, blocked)
                    _check["blocked"] += blocked
                _check["done"] += 1
                await asyncio.sleep(CHECK_DELAY)
    except Exception:
        log.exception("audience check failed")
    finally:
        _check.update(running=False, finished_at=db.now())
