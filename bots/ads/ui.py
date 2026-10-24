"""Форматирование и клавиатуры. Пользовательские тексты — через i18n.t(lang, ...)."""
from html import escape

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bots.ads import db
from bots.ads.config import config
from bots.ads.channel_info import channel_link
from bots.ads.i18n import LANG_NAMES, LANGS, t
from bots.ads.prices import ch_price, fmt_price, fmt_usd, has_price, order_price, short_price  # noqa: F401
from bots.ads.slots import fmt_ts

PAGE_SIZE = 10          # каналов на странице у пользователя
ADMIN_PAGE_SIZE = 10    # каналов на странице в админке

# username бота — заполняется при старте, нужен для ссылок на каналы
BOT_USERNAME = ""


def channel_deeplink(ch) -> str:
    return f"https://t.me/{BOT_USERNAME}?start={ch['token']}"


# ---------- callback data ----------
class MenuCb(CallbackData, prefix="m"):
    action: str                              # home | channels | buy | orders | help | admin | test | lang | support


class LangCb(CallbackData, prefix="lang"):
    code: str


class ChCb(CallbackData, prefix="ch"):       # каталог каналов для пользователя
    action: str                              # list | view | order | busy
    id: int = 0                              # id канала или номер страницы (для list)


class SelCb(CallbackData, prefix="sel"):     # выбор каналов для заказа
    action: str                              # start | toggle | all | none | page | next | back | cancel
    id: int = 0
    p: int = 0                               # текущая страница


class SlotCb(CallbackData, prefix="slot"):  # выбор даты и времени публикации
    action: str                              # days | day | t | drop | now
    v: int = 0                               # код дня (ГГГГММДД) или время слота (unix)


class PostCb(CallbackData, prefix="post"):   # подтверждение поста
    action: str                              # submit | time | replace


class OrdCb(CallbackData, prefix="ord"):     # заказы пользователя
    action: str                              # list | view | cancel | resched
    id: int = 0


class PayCb(CallbackData, prefix="pay"):
    method: str                              # stars | crypto | xrocket | check | xcheck | fake
    id: int


class AdmCb(CallbackData, prefix="adm"):
    action: str
    id: int = 0
    p: int = 0                               # страница списков


# ---------- форматирование ----------
def fmt_num(n: int | None) -> str:
    n = n or 0
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 10_000:
        return f"{n / 1000:.1f}K".replace(".0K", "K")
    return f"{n:,}".replace(",", " ")


def channel_title_link(ch) -> str:
    link = channel_link(ch)
    title = escape(ch["title"])
    return f'<a href="{link}">{title}</a>' if link else f"<b>{title}</b>"


def status_title(lang: str | None, status: str) -> str:
    key = f"st_{status}"
    try:
        return t(lang, key)
    except KeyError:
        return status


def admin_icon(ch) -> str:
    """Значок канала в админке: ⚠️ — бот не админ, 🔴 — скрыт, 🟢 — показывается."""
    if not ch["bot_admin"]:
        return "⚠️"
    return "🟢" if ch["active"] else "🔴"


def channel_card(ch, lang: str | None = "ru", admin: bool = False) -> str:
    lines = [f"📢 {channel_title_link(ch)}"]
    if ch["username"]:
        lines.append(f"@{ch['username']}")
    if ch["description"]:
        desc = ch["description"]
        lines.append(f"\n<i>{escape(desc[:300])}{'…' if len(desc) > 300 else ''}</i>")
    lines.append("")
    lines.append(t(lang, "subscribers", n=fmt_num(ch["subscribers"])))
    views = ch["avg_views"]
    lines.append(t(lang, "views", n=fmt_num(views)) if views else t(lang, "views_na"))
    if views and ch["subscribers"]:
        lines.append(f"📈 ERR: <b>{views / ch['subscribers'] * 100:.1f}%</b>")
    # в карточке канала — все заданные цены (списки и выбор каналов показывают одну)
    stars, usd, rub = ch_price(ch)
    lines.append(t(lang, "price", p=fmt_price(stars, usd, rub)))
    if views and (usd or rub):
        cpm = fmt_usd(usd / views * 1000) if usd else fmt_price(0, 0, round(rub / views * 1000, 2))
        lines.append(f"📊 CPM: <b>{cpm}</b>")
    if admin:
        lines.append("")
        lines.append(f"ID: <code>{ch['chat_id']}</code>")
        lines.append(f"🔗 Ссылка для рекламы: <code>{channel_deeplink(ch)}</code>")
        lines.append(f"Просмотры: {'вручную' if ch['views_manual'] else 'авто'}")
        if not ch["bot_admin"]:
            lines.append("⚠️ <b>Бот не администратор канала</b> — канал скрыт от пользователей. "
                         "Добавьте бота админом с правом публикации, статус обновится сам.")
        lines.append(f"Статус: {'🟢 показывается' if ch['active'] else '🔴 скрыт (виден только в тестовом режиме)'}")
        if not has_price(ch):
            lines.append("⚠️ Цена не задана — пользователи канал не видят")
        elif not payable(stars, usd, rub):
            lines.append("⚠️ Ни один способ оплаты в валютах этого канала не подключён — купить его нельзя")
        if rub and not freekassa_on():
            lines.append("ℹ️ Цена в ₽ не используется: FreeKassa не подключена")
    return "\n".join(lines)


def order_summary(order, channels, lang: str | None = "ru", admin: bool = False) -> str:
    names = "\n".join(f"• {channel_title_link(c)}" for c in channels) or t(lang, "channels_deleted")
    text = t(lang, "order_card",
             test=t(lang, "test_label") if order["is_test"] else "",
             id=order["id"], status=status_title(lang, order["status"]),
             t=fmt_ts(order["publish_at"], lang), n=len(channels), names=names,
             total=fmt_price(*order_price(order)))
    if order["status"] == db.REJECTED and order["reject_reason"]:
        text += t(lang, "reject_reason", r=escape(order["reject_reason"]))
    return text


TEST_MODE_TEXT = (
    "🧪 <b>Тестовый режим включён</b>\n\n"
    "Теперь вы видите бота как обычный пользователь. Все заказы будут <b>тестовыми</b>:\n"
    "• попадают к вам на модерацию с пометкой 🧪;\n"
    "• оплата: кнопка «🧪 Тестовая оплата» (без денег) или настоящие звёзды — "
    "они автоматически вернутся после оплаты;\n"
    "• публикуются <b>только в тестовый канал</b>, реальные каналы не затрагиваются;\n"
    "• не учитываются в статистике продаж.\n\n"
    "Админ-панель остаётся доступной в меню — модерируйте свои же заказы оттуда."
)


# ---------- клавиатуры ----------
def kb(rows: list[list[tuple[str, str | CallbackData]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=tx, callback_data=c.pack() if isinstance(c, CallbackData) else c)
         for tx, c in row]
        for row in rows
    ])


def home_btn(lang) -> tuple:
    return (t(lang, "menu"), MenuCb(action="home"))


def home_kb(lang, is_admin: bool, test: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [(t(lang, "btn_channels"), MenuCb(action="channels")), (t(lang, "btn_buy"), MenuCb(action="buy"))],
        [(t(lang, "btn_orders"), MenuCb(action="orders")), (t(lang, "btn_help"), MenuCb(action="help"))],
        [(t(lang, "btn_support"), MenuCb(action="support")), (t(lang, "btn_lang"), MenuCb(action="lang"))],
    ]
    if is_admin:
        rows.append([(t(lang, "btn_admin"), MenuCb(action="admin")),
                     (t(lang, "btn_test_off" if test else "btn_test_on"), MenuCb(action="test"))])
    return kb(rows)


def lang_kb() -> InlineKeyboardMarkup:
    return kb([[(LANG_NAMES[code], LangCb(code=code)) for code in LANGS]])


def paginate(items: list, page: int, size: int) -> tuple[list, int, int]:
    """Возвращает (элементы страницы, номер страницы, всего страниц)."""
    pages = max(1, (len(items) + size - 1) // size)
    page = max(0, min(page, pages - 1))
    return items[page * size:(page + 1) * size], page, pages


def page_row(lang, page: int, pages: int, make) -> list[tuple]:
    """Строка навигации ◀️ Стр. 2/5 ▶️; make(page) -> CallbackData."""
    if pages <= 1:
        return []
    return [
        (t(lang, "prev") if page > 0 else "·", make(page - 1) if page > 0 else "noop"),
        (t(lang, "page", p=page + 1, n=pages), "noop"),
        (t(lang, "next_page") if page < pages - 1 else "·", make(page + 1) if page < pages - 1 else "noop"),
    ]


def catalog_kb(lang, channels, page: int) -> InlineKeyboardMarkup:
    items, page, pages = paginate(channels, page, PAGE_SIZE)
    rows = [[(f"{ch['title']} · {fmt_num(ch['subscribers'])} 👥 · {short_price(*ch_price(ch))}",
              ChCb(action="view", id=ch["id"]))] for ch in items]
    nav = page_row(lang, page, pages, lambda p: ChCb(action="list", id=p))
    if nav:
        rows.append(nav)
    if channels:
        rows.append([(t(lang, "btn_buy"), SelCb(action="start"))])
    rows.append([home_btn(lang)])
    return kb(rows)


def channel_user_kb(lang, ch, deeplink: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=t(lang, "btn_order_here"), callback_data=ChCb(action="order", id=ch["id"]).pack())],
    ]
    if deeplink:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_more_channels"), callback_data=SelCb(action="start").pack())])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_busy"), callback_data=ChCb(action="busy", id=ch["id"]).pack())])
    link = channel_link(ch)
    if link:
        rows.append([InlineKeyboardButton(text=t(lang, "btn_open"), url=link)])
    rows.append([InlineKeyboardButton(text=t(lang, "btn_to_list"), callback_data=ChCb(action="list").pack()),
                 InlineKeyboardButton(text=t(lang, "menu"), callback_data=MenuCb(action="home").pack())])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def select_kb(lang, channels, selected: set[int], page: int) -> InlineKeyboardMarkup:
    items, page, pages = paginate(channels, page, PAGE_SIZE)
    rows = []
    for ch in items:
        mark = "✅" if ch["id"] in selected else "▫️"
        rows.append([(f"{mark} {ch['title']} · {short_price(*ch_price(ch))}",
                      SelCb(action="toggle", id=ch["id"], p=page))])
    nav = page_row(lang, page, pages, lambda p: SelCb(action="page", p=p))
    if nav:
        rows.append(nav)
    all_selected = channels and len(selected) == len(channels)
    rows.append([(t(lang, "btn_none" if all_selected else "btn_all"),
                  SelCb(action="none" if all_selected else "all", p=page))])
    rows.append([(t(lang, "cancel"), SelCb(action="cancel")),
                 (t(lang, "btn_next", k=len(selected)), SelCb(action="next"))])
    return kb(rows)


def freekassa_on() -> bool:
    from bots.ads.freekassa import freekassa
    return freekassa.enabled


def payable(stars: int, usd: float, rub: float) -> bool:
    """Есть ли подключённый способ оплаты хотя бы в одной из заданных валют."""
    from bots.ads.xrocket import xrocket
    return bool(stars or (usd and (config.cryptopay_token or xrocket.enabled)) or (rub and freekassa_on()))


def pay_kb(lang, order) -> InlineKeyboardMarkup:
    """Способы оплаты — только в тех валютах, в которых у всех каналов заказа задана цена."""
    from bots.ads.xrocket import xrocket
    stars, usd, rub = order_price(order)
    test = order["is_test"]
    rows = []
    if stars:
        rows.append([(t(lang, "btn_pay_stars", n=stars), PayCb(method="stars", id=order["id"]))])
    if rub and freekassa_on() and not test:      # у FreeKassa нет тестовой оплаты без денег
        rows.append([(t(lang, "btn_pay_fk", rub=fmt_price(0, 0, rub)), PayCb(method="fk", id=order["id"]))])
    if usd and (config.cryptopay_token or test):
        rows.append([(t(lang, "btn_pay_crypto", usd=fmt_usd(usd)), PayCb(method="crypto", id=order["id"]))])
    if usd and xrocket.enabled and not test:     # у xRocket нет тестовой сети
        rows.append([(t(lang, "btn_pay_xrocket", usd=fmt_usd(usd)), PayCb(method="xrocket", id=order["id"]))])
    if test:
        rows.append([(t(lang, "btn_pay_test"), PayCb(method="fake", id=order["id"]))])
    return kb(rows)
