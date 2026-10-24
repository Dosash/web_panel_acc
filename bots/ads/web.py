"""Веб-панель администратора: JSON API + статика SPA (без сборки).

Работает в том же процессе, что и бот: общая БД и объект Bot (уведомления, публикация, данные каналов).
Панель отдаётся под префиксом PANEL_PREFIX (по умолчанию /ads), как соседние панели в хабе.
"""
import asyncio
import hmac
import json
import logging
import os
import secrets
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile
from aiohttp import web

from bots.ads import VERSION, broadcast, channel_info, db, live_config, services, slots, ui
from bots.ads.channel_info import ChannelError, refresh_all
from bots.ads.config import config
from bots.ads.freekassa import freekassa
from bots.ads.handlers.admin import parse_add_lines
from bots.ads.prices import has_price, price_from_fields, price_setting
from bots.ads.orders import check_xrocket, copy_post
from bots.ads.screen import notify
from bots.ads.xrocket import HOOK_MARK, HOOK_PATH, hook_stats, webhook_on, webhook_url, webhook_valid, xrocket

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "web_static"
SESSION_COOKIE = "ads_panel"
PRICE_ERROR = "Укажите цену хотя бы в одной валюте (звёзды, $, ₽); пустое поле — валюта не принимается"
_sessions: set[str] = set()


# ---------- утилиты ----------
def ok(data=None, **kw):
    return web.json_response({"ok": True, **({"data": data} if data is not None else {}), **kw},
                             dumps=lambda o: json.dumps(o, ensure_ascii=False, default=str))


def fail(message: str, status: int = 400):
    return web.json_response({"ok": False, "error": message}, status=status,
                             dumps=lambda o: json.dumps(o, ensure_ascii=False))


async def body(request: web.Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def row(r) -> dict:
    return dict(r) if r is not None else None


def channel_dict(c) -> dict:
    d = dict(c)
    d["link"] = ui.channel_deeplink(c)
    d["public_link"] = channel_info.channel_link(c)
    d["visible"] = bool(c["active"] and c["bot_admin"] and has_price(c))
    return d


async def order_dict(o, channels_by_id: dict | None = None) -> dict:
    d = dict(o)
    ids = db.order_channel_ids(o)
    if channels_by_id is None:
        channels_by_id = {c["id"]: c for c in await db.get_channels(ids)}
    d["channels"] = [{"id": i, "title": channels_by_id[i]["title"] if i in channels_by_id else f"#{i} (удалён)"}
                     for i in ids]
    d["publish_text"] = slots.fmt_ts(o["publish_at"])
    d["status_title"] = db.STATUS_TITLES.get(o["status"], o["status"])
    d["time_ok"] = slots.slot_ok(o)
    d["post"] = json.loads(o["post_json"]) if d.get("post_json") else None
    d.pop("post_json", None)
    d.pop("reply_markup", None)
    return d


# ---------- защита ----------
# TG Panel (app/bots.py) запускает бота с TG_PANEL_KEY и ходит в его панель только через свой прокси,
# добавляя этот ключ в заголовок: панель на 127.0.0.1 не открыть в обход входа в TG Panel
PANEL_KEY = os.getenv("TG_PANEL_KEY", "")


@web.middleware
async def guard(request: web.Request, handler):
    if PANEL_KEY and not hmac.compare_digest(request.headers.get("X-TG-Panel-Key", ""), PANEL_KEY):
        return web.Response(status=403, text="Откройте панель бота через TG Panel")
    path = request.path
    api = path.startswith(config.panel_prefix + "/api/")
    if api and request.method not in ("GET", "HEAD", "OPTIONS"):
        # кастомный заголовок нельзя отправить с чужого сайта без CORS — защита от CSRF
        if request.headers.get("X-Panel") != "1":
            return fail("forbidden", 403)
    if config.panel_password and api and not path.endswith(("/api/health", "/api/login", "/api/auth")):
        if request.cookies.get(SESSION_COOKIE) not in _sessions:
            return fail("auth required", 401)
    resp = await handler(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")  # панель бота открывается во фрейме TG Panel
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    if api:
        resp.headers["Cache-Control"] = "no-store"
    return resp


def build_app(bot: Bot) -> web.Application:
    app = web.Application(middlewares=[guard], client_max_size=21 * 1024 * 1024)
    p = config.panel_prefix
    r = web.RouteTableDef()

    # ---------- вебхук xRocket (единственное, что можно открыть в интернет) ----------
    hook_tasks: set[asyncio.Task] = set()

    async def xrocket_paid(invoice_id: str) -> None:
        order = await db.order_by_xrocket_invoice(invoice_id)
        if not order:
            return
        try:
            # статус перепроверяем по API: одному вебхуку не верим, даже с подписью
            if await check_xrocket(bot, order):
                log.info("xrocket webhook: заказ #%s оплачен", order["id"])
        except Exception:
            log.exception("xrocket webhook: проверка счёта %s не удалась (подхватит опрос)", invoice_id)

    @r.get(p + HOOK_PATH)
    async def xrocket_hook_probe(request):
        if not webhook_on():
            raise web.HTTPNotFound()
        return web.Response(text=HOOK_MARK)

    @r.post(p + HOOK_PATH)
    async def xrocket_hook(request):
        if not webhook_on():
            raise web.HTTPNotFound()
        raw = await request.read()
        if not webhook_valid(request.headers, raw, config.xrocket_webhook_secret):
            log.warning("xrocket webhook: неверная подпись")
            return web.Response(status=401, text="bad signature")
        try:
            event = json.loads(raw)
            inv = (event.get("data") or {}).get("invoice") or {}
        except (ValueError, AttributeError):
            return web.Response(status=400, text="bad json")
        hook_stats["last"] = db.now()
        if event.get("type") == "invoice" and inv.get("status") == "paid" and inv.get("id"):
            # отвечаем 200 сразу (у xRocket таймаут 10 с), оплату обрабатываем в фоне
            task = asyncio.create_task(xrocket_paid(str(inv["id"])))
            hook_tasks.add(task)
            task.add_done_callback(hook_tasks.discard)
        return web.Response(text="ok")

    # ---------- служебное ----------
    @r.get(p + "/api/health")
    async def health(request):
        n_mod = await db.count_status(db.MODERATION)
        return web.json_response({"status": "ok", "version": VERSION, "bot": ui.BOT_USERNAME,
                                  "moderation": n_mod, "support_unread": await db.support_unread_total()})

    @r.get(p + "/api/auth")
    async def auth_state(request):
        enabled = bool(config.panel_password)
        return ok({"enabled": enabled, "logged_in": (not enabled) or request.cookies.get(SESSION_COOKIE) in _sessions})

    @r.post(p + "/api/login")
    async def login(request):
        if not config.panel_password:
            return ok()
        data = await body(request)
        if not hmac.compare_digest(str(data.get("password", "")), config.panel_password):
            return fail("Неверный пароль", 401)
        sid = secrets.token_urlsafe(32)
        _sessions.add(sid)
        resp = ok()
        resp.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="Strict", path=p, max_age=30 * 86400)
        return resp

    @r.post(p + "/api/logout")
    async def logout(request):
        _sessions.discard(request.cookies.get(SESSION_COOKIE))
        resp = ok()
        resp.del_cookie(SESSION_COOKIE, path=p)
        return resp

    # ---------- обзор ----------
    @r.get(p + "/api/summary")
    async def summary(request):
        channels = await db.list_channels()
        stats = await db.stats()
        stars, usd, rub = await db.default_price()
        upcoming = await db.upcoming_bookings(db.now(), False, limit=5)
        return ok({
            "version": VERSION,
            "bot": ui.BOT_USERNAME,
            "channels": len(channels),
            "channels_visible": sum(1 for c in channels if c["active"] and c["bot_admin"] and has_price(c)),
            "channels_no_admin": sum(1 for c in channels if not c["bot_admin"]),
            "reach": sum(c["subscribers"] or 0 for c in channels),
            "moderation": await db.count_status(db.MODERATION),
            "awaiting_payment": await db.count_status(db.APPROVED),
            "scheduled": await db.count_status(db.SCHEDULED),
            "need_time": await db.count_status(db.NEED_TIME),
            "support_unread": await db.support_unread_total(),
            "stats": stats,
            "audience": await db.audience_stats(),
            "default_price": {"stars": stars, "usd": usd, "rub": rub},
            "premium_emoji": await db.premium_emoji(),
            "upcoming": [await order_dict(o) for o in upcoming],
            "test_admins": [a for a in config.admin_ids if await db.is_test_user(a)],
            "admin_ids": list(config.admin_ids),
            "payments": payments_status(),
        })

    # ---------- каналы ----------
    @r.get(p + "/api/channels")
    async def channels_list(request):
        return ok([channel_dict(c) for c in await db.list_channels()])

    @r.post(p + "/api/channels/bulk")
    async def channels_bulk(request):
        lines = parse_add_lines((await body(request)).get("text", ""))
        if not lines:
            return fail("Пустой список")
        if len(lines) > 300:
            return fail("Не больше 300 строк за раз")
        added, errors = [], []
        for line, ref, price in lines:
            if ref is None:
                errors.append({"line": line, "error": "не похоже на канал"})
                continue
            try:
                cid = await services.add_channel(bot, ref, price)
                added.append(channel_dict(await db.get_channel(cid)))
            except ChannelError as e:
                errors.append({"line": line, "error": str(e)})
        return ok({"added": added, "errors": errors})

    @r.patch(p + "/api/channels/{id:\\d+}")
    async def channel_update(request):
        cid = int(request.match_info["id"])
        ch = await db.get_channel(cid)
        if not ch:
            return fail("Канал не найден", 404)
        data = await body(request)
        fields = {}
        if any(k in data for k in ("price_stars", "price_usd", "price_rub")):
            price = price_from_fields(data)
            if not price:
                return fail(PRICE_ERROR)
            fields.update(price_stars=price[0], price_usd=price[1], price_rub=price[2])
        if "active" in data:
            fields["active"] = 1 if data["active"] else 0
        if "avg_views" in data:
            if data["avg_views"] in (None, "", 0, "0"):
                fields["views_manual"] = 0
            else:
                try:
                    fields.update(avg_views=max(0, int(data["avg_views"])), views_manual=1)
                except (TypeError, ValueError):
                    return fail("Просмотры — целое число")
        if fields:
            await db.update_channel(cid, **fields)
        if fields.get("views_manual") == 0:
            try:
                await channel_info.fetch_and_save(bot, ch["chat_id"])
            except ChannelError:
                pass
        return ok(channel_dict(await db.get_channel(cid)))

    @r.post(p + "/api/channels/{id:\\d+}/refresh")
    async def channel_refresh(request):
        ch = await db.get_channel(int(request.match_info["id"]))
        if not ch:
            return fail("Канал не найден", 404)
        try:
            await channel_info.fetch_and_save(bot, ch["chat_id"])
        except ChannelError as e:
            return fail(str(e))
        return ok(channel_dict(await db.get_channel(ch["id"])))

    @r.post(p + "/api/channels/{id:\\d+}/token")
    async def channel_token(request):
        cid = int(request.match_info["id"])
        if not await db.get_channel(cid):
            return fail("Канал не найден", 404)
        await db.regenerate_token(cid)
        return ok(channel_dict(await db.get_channel(cid)))

    @r.delete(p + "/api/channels/{id:\\d+}")
    async def channel_delete(request):
        await services.delete_channel(int(request.match_info["id"]))
        return ok()

    @r.post(p + "/api/channels/price-all")
    async def price_all(request):
        data = await body(request)
        price = price_from_fields(data)
        if not price:
            return fail(PRICE_ERROR)
        await db.set_price_all(*price)
        return ok()

    @r.post(p + "/api/channels/refresh-all")
    async def channels_refresh_all(request):
        n, errors = await refresh_all(bot)
        return ok({"updated": n, "errors": errors})

    @r.get(p + "/api/settings")
    async def settings_get(request):
        stars, usd, rub = await db.default_price()
        return ok({"default_price": {"stars": stars, "usd": usd, "rub": rub}})

    @r.put(p + "/api/settings/default-price")
    async def settings_default_price(request):
        data = await body(request)
        price = price_from_fields(data)
        if not price:
            return fail(PRICE_ERROR)
        await db.set_setting("default_price", price_setting(price))
        return ok()

    @r.put(p + "/api/settings/premium-emoji")
    async def settings_premium_emoji(request):
        data = await body(request)
        await db.set_setting("premium_emoji", "1" if data.get("on") is True else "0")
        return ok({"premium_emoji": await db.premium_emoji()})

    # ---------- настройки бота и ключи платёжных систем ----------
    def payments_status() -> dict:
        return {"stars": True, "cryptobot": bool(config.cryptopay_token), "xrocket": xrocket.enabled,
                "xrocket_hook": xrocket.enabled and webhook_on(), "freekassa": freekassa.enabled,
                "xrocket_hook_url": webhook_url(), "xrocket_hook_last": hook_stats["last"]}

    @r.get(p + "/api/settings/bot")
    async def bot_settings_get(request):
        return ok({"fields": live_config.describe(), "payments": payments_status(), "bot": ui.BOT_USERNAME})

    @r.put(p + "/api/settings/bot")
    async def bot_settings_put(request):
        values = (await body(request)).get("values")
        if not isinstance(values, dict) or not values:
            return fail("Нет изменений")
        try:
            res = await live_config.save(values)
        except live_config.SettingsError as e:
            return fail(str(e))
        return ok({**res, "fields": live_config.describe(), "payments": payments_status()})

    @r.delete(p + "/api/settings/bot/{key:[A-Z_]+}")
    async def bot_settings_reset(request):
        try:
            res = await live_config.reset(request.match_info["key"])
        except live_config.SettingsError as e:
            return fail(str(e))
        return ok({**res, "fields": live_config.describe(), "payments": payments_status()})

    # ---------- ссылки на каналы ----------
    @r.get(p + "/api/links.txt")
    async def links_txt(request):
        lines = [f"{c['title']}\t{ui.channel_deeplink(c)}" for c in await db.list_channels()]
        return web.Response(text="\n".join(lines) + "\n", content_type="text/plain", charset="utf-8",
                            headers={"Content-Disposition": 'attachment; filename="channel-links.txt"'})

    # ---------- заказы и модерация ----------
    @r.get(p + "/api/orders")
    async def orders_list(request):
        status = request.query.get("status") or None
        orders = await db.list_orders(status)
        by_id = {c["id"]: c for c in await db.list_channels()}
        return ok([await order_dict(o, by_id) for o in orders])

    @r.get(p + "/api/orders/{id:\\d+}")
    async def order_get(request):
        o = await db.get_order(int(request.match_info["id"]))
        if not o:
            return fail("Заказ не найден", 404)
        return ok(await order_dict(o))

    @r.post(p + "/api/orders/{id:\\d+}/approve")
    async def order_approve(request):
        try:
            await services.approve_order(bot, int(request.match_info["id"]))
        except services.ServiceError as e:
            return fail(str(e), 409)
        return ok()

    @r.post(p + "/api/orders/{id:\\d+}/reject")
    async def order_reject(request):
        reason = (str((await body(request)).get("reason") or "")).strip()[:1000] or None
        try:
            await services.reject_order(bot, int(request.match_info["id"]), reason)
        except services.ServiceError as e:
            return fail(str(e), 409)
        return ok()

    @r.post(p + "/api/orders/{id:\\d+}/preview")
    async def order_preview(request):
        """Прислать пост администраторам в Telegram — посмотреть «как в канале»."""
        o = await db.get_order(int(request.match_info["id"]))
        if not o:
            return fail("Заказ не найден", 404)
        sent = 0
        for admin_id in config.admin_ids:
            try:
                await copy_post(bot, o, admin_id)
                sent += 1
            except Exception as e:
                log.warning("preview to %s failed: %s", admin_id, e)
        if not sent:
            return fail("Не удалось отправить пост — возможно, пользователь удалил его из чата с ботом")
        return ok()

    async def stream_file(file_id: str) -> web.Response:
        try:
            f = await bot.get_file(file_id)
            data = await bot.download_file(f.file_path)
        except Exception as e:
            return fail(f"Файл недоступен: {e}", 404)
        ext = (f.file_path or "").rsplit(".", 1)[-1].lower()
        ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
                 "gif": "image/gif", "mp4": "video/mp4", "mov": "video/quicktime", "oga": "audio/ogg",
                 "ogg": "audio/ogg", "mp3": "audio/mpeg", "webm": "video/webm", "pdf": "application/pdf"}.get(
            ext, "application/octet-stream")
        return web.Response(body=data.read(), content_type=ctype,
                            headers={"Cache-Control": "private, max-age=3600"})

    @r.get(p + "/api/orders/{id:\\d+}/media")
    async def order_media(request):
        o = await db.get_order(int(request.match_info["id"]))
        post = json.loads(o["post_json"]) if o and o["post_json"] else None
        if not post or not post.get("file_id"):
            return fail("Нет вложения", 404)
        return await stream_file(post["file_id"])

    # ---------- расписание ----------
    @r.get(p + "/api/schedule")
    async def schedule(request):
        test = request.query.get("test") == "1"
        rows = await db.upcoming_bookings(db.now() - 3600, test, limit=200)
        by_id = {c["id"]: c for c in await db.list_channels()}
        return ok([await order_dict(o, by_id) for o in rows])

    # ---------- поддержка ----------
    @r.get(p + "/api/support")
    async def support_list(request):
        status = request.query.get("status") or "open"
        return ok([dict(t) for t in await db.support_threads(status)])

    @r.get(p + "/api/support/{uid:\\d+}")
    async def support_thread(request):
        uid = int(request.match_info["uid"])
        th = await db.support_thread(uid)
        if not th:
            return fail("Диалог не найден", 404)
        await db.support_mark_read(uid)
        msgs = [dict(m) for m in await db.support_messages(uid, limit=200)]
        for m in msgs:
            m["has_file"] = bool(m.pop("file_id", None))
            m.pop("src_chat_id", None)
            m.pop("src_msg_id", None)
        return ok({"thread": dict(th), "messages": msgs})

    @r.post(p + "/api/support/{uid:\\d+}/reply")
    async def support_reply(request):
        uid = int(request.match_info["uid"])
        text = str((await body(request)).get("text") or "").strip()
        if not text:
            return fail("Пустое сообщение")
        if not await db.support_thread(uid):
            return fail("Диалог не найден", 404)
        try:
            await services.support_reply_text(bot, uid, text[:4000])
        except Exception as e:
            return fail(f"Не удалось доставить (пользователь заблокировал бота?): {e}")
        return ok()

    @r.post(p + "/api/support/{uid:\\d+}/status")
    async def support_status(request):
        status = (await body(request)).get("status")
        if status not in ("open", "closed"):
            return fail("Неизвестный статус")
        await db.support_set_status(int(request.match_info["uid"]), status)
        return ok()

    @r.get(p + "/api/support/media/{mid:\\d+}")
    async def support_media(request):
        m = await db.support_message(int(request.match_info["mid"]))
        if not m or not m["file_id"]:
            return fail("Нет вложения", 404)
        return await stream_file(m["file_id"])

    # ---------- рассылка ----------
    def broadcast_dict(b) -> dict:
        d = dict(b)
        d["post"] = json.loads(d.pop("post_json") or "null")
        d.pop("reply_markup", None)
        return d

    @r.get(p + "/api/broadcast")
    async def broadcast_state(request):
        draft = await broadcast.get_draft()
        if draft:
            draft["buttons_text"] = broadcast.buttons_text(draft["post"].get("buttons") or [])
        return ok({
            "draft": draft,
            "capture_until": broadcast.capture_until(),
            "audience": await db.audience_stats(),
            "history": [broadcast_dict(b) for b in await db.list_broadcasts()],
            "check": broadcast.check_state(),
            "bot": ui.BOT_USERNAME,
        })

    @r.post(p + "/api/broadcast/draft")
    async def broadcast_draft(request):
        """Пост из панели: бот присылает его первому админу — это сообщение и становится источником рассылки."""
        if not config.admin_ids:
            return fail("Не задан ADMIN_IDS")
        form = await request.post()
        text = str(form.get("text") or "").strip()
        try:
            rows = broadcast.parse_buttons(str(form.get("buttons") or ""))
        except broadcast.BroadcastError as e:
            return fail(str(e))
        upload = form.get("file")
        has_file = upload is not None and hasattr(upload, "file") and upload.filename
        if not text and not has_file:
            return fail("Добавьте текст или файл")
        if has_file and len(text) > 1024:
            return fail(f"С фото или видео текст — не длиннее 1024 символов (сейчас {len(text)})")
        if len(text) > 4096:
            return fail(f"Текст — не длиннее 4096 символов (сейчас {len(text)})")
        markup = broadcast.buttons_markup(rows)
        chat = config.admin_ids[0]
        try:
            if has_file:
                data = upload.file.read()
                name = upload.filename
                ctype = (upload.content_type or "").lower()
                f = BufferedInputFile(data, filename=name)
                caption = text or None
                if ctype == "image/gif" or name.lower().endswith(".gif"):
                    msg = await bot.send_animation(chat, f, caption=caption, reply_markup=markup)
                elif ctype.startswith("image/"):
                    msg = await bot.send_photo(chat, f, caption=caption, reply_markup=markup)
                elif ctype.startswith("video/"):
                    msg = await bot.send_video(chat, f, caption=caption, reply_markup=markup, supports_streaming=True)
                else:
                    msg = await bot.send_document(chat, f, caption=caption, reply_markup=markup)
            else:
                msg = await bot.send_message(chat, text, reply_markup=markup)
        except TelegramBadRequest as e:
            if "parse entities" in str(e).lower():
                return fail("Ошибка в разметке текста: проверьте закрытые теги (<b>…</b>) и символы < > &")
            return fail(f"Telegram не принял пост: {e}")
        except Exception as e:
            return fail(f"Не удалось отправить пост: {e}")
        broadcast.stop_capture()
        draft = await broadcast.save_draft(msg, "panel", rows)
        # остальным админам — копия для просмотра
        for admin_id in config.admin_ids[1:]:
            try:
                await bot.copy_message(admin_id, chat, msg.message_id, reply_markup=markup)
            except Exception:
                pass
        await notify(bot, chat, "☝️ Черновик рассылки из веб-панели. "
                                         "<i>Не удаляйте его, пока рассылка не закончится.</i>")
        return ok(draft)

    @r.put(p + "/api/broadcast/draft/buttons")
    async def broadcast_buttons(request):
        try:
            rows = broadcast.parse_buttons(str((await body(request)).get("buttons") or ""))
            return ok(await broadcast.set_draft_buttons(rows))
        except broadcast.BroadcastError as e:
            return fail(str(e))

    @r.delete(p + "/api/broadcast/draft")
    async def broadcast_draft_delete(request):
        await broadcast.clear_draft()
        return ok()

    @r.post(p + "/api/broadcast/draft/preview")
    async def broadcast_preview(request):
        draft = await broadcast.get_draft()
        if not draft:
            return fail("Черновика нет", 404)
        if not await broadcast.send_preview(bot, draft):
            return fail("Не удалось отправить — возможно, исходный пост удалён из чата с ботом")
        return ok()

    @r.get(p + "/api/broadcast/draft/media")
    async def broadcast_media(request):
        draft = await broadcast.get_draft()
        if not draft or not draft["post"].get("file_id"):
            return fail("Нет вложения", 404)
        return await stream_file(draft["post"]["file_id"])

    @r.post(p + "/api/broadcast/capture")
    async def broadcast_capture(request):
        if (await body(request)).get("stop"):
            broadcast.stop_capture()
            return ok()
        return ok({"capture_until": broadcast.start_capture()})

    @r.post(p + "/api/broadcast/start")
    async def broadcast_start(request):
        try:
            return ok({"id": await broadcast.start(bot)})
        except broadcast.BroadcastError as e:
            return fail(str(e), 409)

    @r.post(p + "/api/broadcast/{id:\\d+}/stop")
    async def broadcast_stop(request):
        try:
            await broadcast.stop(int(request.match_info["id"]))
        except broadcast.BroadcastError as e:
            return fail(str(e), 409)
        return ok()

    @r.post(p + "/api/broadcast/check")
    async def broadcast_check(request):
        try:
            await broadcast.start_check(bot)
        except broadcast.BroadcastError as e:
            return fail(str(e), 409)
        return ok(broadcast.check_state())

    # ---------- тестовый режим ----------
    @r.post(p + "/api/test/clear")
    async def test_clear(request):
        return ok({"deleted": await db.delete_test_orders()})

    # ---------- статика ----------
    async def index(request):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        # версия ассетов меняется при любой правке файлов — браузер не держит старый app.js
        assets = str(int(max(f.stat().st_mtime for f in STATIC.iterdir())))
        html = (html.replace("__PREFIX__", p).replace("__VERSION__", VERSION).replace("__TZ__", config.timezone)
                .replace("__ASSETS__", assets))
        return web.Response(text=html,
                            content_type="text/html", headers={"Cache-Control": "no-cache"})

    @r.get(p)
    async def to_slash(request):
        raise web.HTTPMovedPermanently(p + "/")

    r.get(p + "/")(index)
    app.add_routes(r)
    app.router.add_static(p + "/static/", STATIC, append_version=False)
    return app


async def start_panel(bot: Bot) -> web.AppRunner | None:
    if not config.panel_port:
        return None
    runner = web.AppRunner(build_app(bot), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, config.panel_host, config.panel_port)
    await site.start()
    log.info("веб-панель: http://%s:%s%s/", config.panel_host, config.panel_port, config.panel_prefix)
    if webhook_on():
        log.info("xRocket вебхук: %s (опрос xRocket — раз в 10 минут, подстраховка)", webhook_url())
    return runner

