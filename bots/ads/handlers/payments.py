import logging
import secrets

from aiogram import Bot, F, Router
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice,
                           Message, PreCheckoutQuery)

from bots.ads import db, slots
from bots.ads.config import config
from bots.ads.cryptopay import CryptoPayError, client_for
from bots.ads.freekassa import FreeKassaError, freekassa
from bots.ads.handlers.user import order_screen, user_lang
from bots.ads.i18n import t
from bots.ads.orders import check_crypto, check_freekassa, check_xrocket, handle_paid
from bots.ads.xrocket import XRocketError, xrocket
from bots.ads.screen import add_extra, nav, remove_input
from bots.ads.prices import fmt_rub
from bots.ads.ui import MenuCb, OrdCb, PayCb, fmt_usd, status_title

log = logging.getLogger(__name__)
router = Router(name="payments")
# подключается в диспетчер ПЕРВЫМ: сообщение об оплате звёздами не должен перехватить ни приём поста для
# рассылки, ни FSM-обработчики админки и поддержки (иначе оплата потеряется)
early_router = Router(name="payments_early")


async def get_payable(call: CallbackQuery, order_id: int, currency: str | None = None):
    """Заказ, который можно оплатить сейчас. currency — колонка суммы (total_stars/total_usd/total_rub):
    в валюте без цены у какого-либо из каналов заказ не оплачивается."""
    lang = await user_lang(call.from_user)
    order = await db.get_order(order_id)
    if not order or order["user_id"] != call.from_user.id:
        await call.answer(t(lang, "order_nf"), show_alert=True)
        return None
    if currency and not order[currency]:
        await call.answer(t(lang, "unavailable"), show_alert=True)
        return None
    if order["status"] != db.APPROVED:
        await call.answer(t(lang, "pay_status", s=status_title(lang, order["status"])), show_alert=True)
        return None
    if not slots.slot_ok(order):
        await call.answer(t(lang, "pay_time_passed"), show_alert=True)
        return None
    if await slot_taken(order):
        await call.answer(t(lang, "pay_slot_taken"), show_alert=True)
        return None
    return order


async def slot_taken(order) -> bool:
    """Желаемое время заказа уже забронировано кем-то (оплачено)."""
    if not order["publish_at"]:
        return False
    busy = await slots.load_busy(bool(order["is_test"]), exclude_order=order["id"])
    return bool(slots.busy_in(busy, order["publish_at"], db.order_channel_ids(order)))


# ---------- Telegram Stars ----------
@router.callback_query(PayCb.filter(F.method == "stars"))
async def pay_stars(call: CallbackQuery, callback_data: PayCb, bot: Bot):
    order = await get_payable(call, callback_data.id, "total_stars")
    if not order:
        return
    lang = await user_lang(call.from_user)
    invoice = await bot.send_invoice(
        chat_id=call.from_user.id,
        title=t(lang, "inv_title", id=order["id"]),
        description=t(lang, "inv_desc", n=len(db.order_channel_ids(order))),
        payload=f"order:{order['id']}",
        currency="XTR",
        prices=[LabeledPrice(label=t(lang, "inv_label"), amount=order["total_stars"])],
    )
    # счёт — временное сообщение, удалится при следующем переходе по меню
    await add_extra(call.from_user.id, invoice.message_id)
    await call.answer()


@early_router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    lang = await user_lang(query.from_user)
    try:
        order_id = int(query.invoice_payload.split(":")[1])
    except (IndexError, ValueError):
        return await query.answer(ok=False, error_message=t(lang, "pc_bad"))
    order = await db.get_order(order_id)
    # платить может только владелец заказа — чужой payload не принимаем
    if not order or order["status"] != db.APPROVED or order["user_id"] != query.from_user.id:
        return await query.answer(ok=False, error_message=t(lang, "pc_unavailable"))
    if not slots.slot_ok(order):
        return await query.answer(ok=False, error_message=t(lang, "pc_passed"))
    if await slot_taken(order):
        return await query.answer(ok=False, error_message=t(lang, "pc_taken"))
    if query.currency != "XTR" or not order["total_stars"] or query.total_amount != order["total_stars"]:
        return await query.answer(ok=False, error_message=t(lang, "pc_amount"))
    await query.answer(ok=True)


@early_router.message(F.successful_payment)
async def successful_payment(message: Message, bot: Bot):
    sp = message.successful_payment
    order_id = int(sp.invoice_payload.split(":")[1])
    await remove_input(message)
    await handle_paid(bot, order_id, "stars", charge_id=sp.telegram_payment_charge_id)


# ---------- CryptoBot ----------
def crypto_kb(lang, order_id: int, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_go_pay"), url=url)],
        [InlineKeyboardButton(text=t(lang, "btn_check"), callback_data=PayCb(method="check", id=order_id).pack())],
        [InlineKeyboardButton(text=t(lang, "btn_to_order"), callback_data=OrdCb(action="view", id=order_id).pack()),
         InlineKeyboardButton(text=t(lang, "menu"), callback_data=MenuCb(action="home").pack())],
    ])


@router.callback_query(PayCb.filter(F.method == "crypto"))
async def pay_crypto(call: CallbackQuery, callback_data: PayCb):
    order = await get_payable(call, callback_data.id, "total_usd")
    if not order:
        return
    lang = await user_lang(call.from_user)
    client = client_for(order)
    if not client:
        return await call.answer(t(lang, "crypto_no_test" if order["is_test"] else "unavailable"), show_alert=True)
    url = order["cp_invoice_url"]
    if url:
        # старый счёт мог истечь (например, время заказа перенесли) — тогда выпишем новый
        try:
            items = await client.get_invoices([order["cp_invoice_id"]])
            if not items or items[0].get("status") != "active":
                url = None
        except CryptoPayError:
            pass
    if not url:
        try:
            # счёт живёт до времени публикации, но не дольше суток
            deadline = min(db.now() + 24 * 3600, order["publish_at"] or (db.now() + 24 * 3600))
            inv = await client.create_invoice(
                amount_usd=order["total_usd"],
                description=t(lang, "inv_title", id=order["id"]),
                payload=f"order:{order['id']}",
                expires_in=max(300, deadline - db.now()),
            )
        except CryptoPayError as e:
            log.error("createInvoice failed: %s", e)
            return await call.answer(t(lang, "crypto_fail"), show_alert=True)
        url = inv.get("bot_invoice_url") or inv.get("pay_url")
        await db.update_order(order["id"], cp_invoice_id=inv["invoice_id"], cp_invoice_url=url)
    await nav(call, t(lang, "crypto_text", usd=fmt_usd(order["total_usd"]), id=order["id"],
                      test=t(lang, "crypto_testnet") if order["is_test"] else ""),
              crypto_kb(lang, order["id"], url))
    await call.answer()


# ---------- xRocket Pay ----------
def xrocket_kb(lang, order_id: int, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_go_pay"), url=url)],
        [InlineKeyboardButton(text=t(lang, "btn_check"), callback_data=PayCb(method="xcheck", id=order_id).pack())],
        [InlineKeyboardButton(text=t(lang, "btn_to_order"), callback_data=OrdCb(action="view", id=order_id).pack()),
         InlineKeyboardButton(text=t(lang, "menu"), callback_data=MenuCb(action="home").pack())],
    ])


@router.callback_query(PayCb.filter(F.method == "xrocket"))
async def pay_xrocket(call: CallbackQuery, callback_data: PayCb):
    order = await get_payable(call, callback_data.id, "total_usd")
    if not order:
        return
    lang = await user_lang(call.from_user)
    if not xrocket.enabled or order["is_test"]:
        return await call.answer(t(lang, "unavailable"), show_alert=True)
    url = order["xr_invoice_url"]
    if url:
        # старый счёт мог истечь — тогда выпишем новый
        try:
            inv = await xrocket.get_invoice(order["xr_invoice_id"])
            if not inv or inv.get("status") != "active":
                url = None
        except XRocketError:
            url = None
    if not url:
        try:
            deadline = min(db.now() + 24 * 3600, order["publish_at"] or (db.now() + 24 * 3600))
            inv = await xrocket.create_invoice(
                amount_usd=order["total_usd"],
                description=t(lang, "inv_title", id=order["id"]),
                # уникален на каждый счёт заказа (старый мог истечь)
                client_id=f"order-{order['id']}-{db.now()}",
                expires_in=max(300, deadline - db.now()),
            )
        except XRocketError as e:
            log.error("xrocket createInvoice failed: %s", e)
            return await call.answer(t(lang, "xrocket_fail"), show_alert=True)
        url = inv["links"]["telegramBotLink"]
        await db.update_order(order["id"], xr_invoice_id=inv["id"], xr_invoice_url=url)
    await nav(call, t(lang, "xrocket_text", usd=fmt_usd(order["total_usd"]), id=order["id"]),
              xrocket_kb(lang, order["id"], url))
    await call.answer()


@router.callback_query(PayCb.filter(F.method == "xcheck"))
async def xrocket_check(call: CallbackQuery, callback_data: PayCb, bot: Bot):
    lang = await user_lang(call.from_user)
    order = await db.get_order(callback_data.id)
    if not order or order["user_id"] != call.from_user.id:
        return await call.answer(t(lang, "order_nf"), show_alert=True)
    if order["status"] in (db.PAID, db.SCHEDULED, db.NEED_TIME, db.PUBLISHED):
        return await call.answer(t(lang, "already_paid"), show_alert=True)
    try:
        paid = await check_xrocket(bot, order)
    except XRocketError:
        return await call.answer(t(lang, "check_fail"), show_alert=True)
    if paid:
        return await order_screen(call, order["id"], t(lang, "paid_ok"))
    await call.answer(t(lang, "not_paid"), show_alert=True)


# ---------- FreeKassa (рубли: СБП, карты, FKWallet) ----------
def fk_kb(lang, order_id: int, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_go_pay"), url=url)],
        [InlineKeyboardButton(text=t(lang, "btn_check"), callback_data=PayCb(method="fkcheck", id=order_id).pack())],
        [InlineKeyboardButton(text=t(lang, "btn_to_order"), callback_data=OrdCb(action="view", id=order_id).pack()),
         InlineKeyboardButton(text=t(lang, "menu"), callback_data=MenuCb(action="home").pack())],
    ])


@router.callback_query(PayCb.filter(F.method == "fk"))
async def pay_fk(call: CallbackQuery, callback_data: PayCb):
    order = await get_payable(call, callback_data.id, "total_rub")
    if not order:
        return
    lang = await user_lang(call.from_user)
    if not freekassa.enabled or order["is_test"]:
        return await call.answer(t(lang, "fk_fail"), show_alert=True)
    # номер платежа постоянный для заказа: любая оплата по ссылке найдётся при проверке;
    # случайная часть — чтобы не совпасть с платежами другой базы того же магазина
    payment_id = order["fk_payment_id"] or f"ad{order['id']}x{secrets.token_hex(3)}"
    url = freekassa.pay_url(payment_id, order["total_rub"], lang)
    await db.update_order(order["id"], fk_payment_id=payment_id, fk_invoice_url=url, fk_invoice_at=db.now())
    await nav(call, t(lang, "fk_text", rub=fmt_rub(order["total_rub"]), id=order["id"]),
              fk_kb(lang, order["id"], url))
    await call.answer()


@router.callback_query(PayCb.filter(F.method == "fkcheck"))
async def fk_check(call: CallbackQuery, callback_data: PayCb, bot: Bot):
    lang = await user_lang(call.from_user)
    order = await db.get_order(callback_data.id)
    if not order or order["user_id"] != call.from_user.id:
        return await call.answer(t(lang, "order_nf"), show_alert=True)
    if order["status"] in (db.PAID, db.SCHEDULED, db.NEED_TIME, db.PUBLISHED):
        return await call.answer(t(lang, "already_paid"), show_alert=True)
    try:
        paid = await check_freekassa(bot, order)
    except FreeKassaError:
        return await call.answer(t(lang, "check_fail"), show_alert=True)
    if paid:
        return await order_screen(call, order["id"], t(lang, "paid_ok"))
    await call.answer(t(lang, "not_paid"), show_alert=True)


# ---------- тестовая оплата (только админ в тестовом режиме) ----------
@router.callback_query(PayCb.filter(F.method == "fake"), F.from_user.id.in_(config.admin_ids))
async def pay_fake(call: CallbackQuery, callback_data: PayCb, bot: Bot):
    order = await get_payable(call, callback_data.id)
    if not order:
        return
    lang = await user_lang(call.from_user)
    if not order["is_test"]:
        return await call.answer(t(lang, "unavailable"), show_alert=True)
    await handle_paid(bot, order["id"], "test")
    await order_screen(call, order["id"], t(lang, "test_paid"))


@router.callback_query(PayCb.filter(F.method == "fake"))
async def pay_fake_denied(call: CallbackQuery):
    await call.answer(t(await user_lang(call.from_user), "unavailable"), show_alert=True)


@router.callback_query(PayCb.filter(F.method == "check"))
async def crypto_check(call: CallbackQuery, callback_data: PayCb, bot: Bot):
    lang = await user_lang(call.from_user)
    order = await db.get_order(callback_data.id)
    if not order or order["user_id"] != call.from_user.id:
        return await call.answer(t(lang, "order_nf"), show_alert=True)
    if order["status"] in (db.PAID, db.SCHEDULED, db.NEED_TIME, db.PUBLISHED):
        return await call.answer(t(lang, "already_paid"), show_alert=True)
    try:
        paid = await check_crypto(bot, order)
    except CryptoPayError:
        return await call.answer(t(lang, "check_fail"), show_alert=True)
    if paid:
        return await order_screen(call, order["id"], t(lang, "paid_ok"))
    await call.answer(t(lang, "not_paid"), show_alert=True)
