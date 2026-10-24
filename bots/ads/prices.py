"""Цены в трёх валютах: звёзды (Telegram Stars), доллары (CryptoBot, xRocket), рубли (FreeKassa).

0 — цена в этой валюте не задана: способ оплаты в ней покупателю не показывается.
"""
import re

Price = tuple[int, float, float]          # (звёзды, доллары, рубли)

PRICE_HINT = ("Отправьте цену тремя числами: <b>звёзды</b>, <b>доллары</b> (CryptoBot, xRocket) "
              "и <b>рубли</b> (FreeKassa: СБП, карты).\n"
              "Например: <code>500 7.5 650</code>\n"
              "Валюту, в которой не принимаете оплату, укажите как <code>0</code> или <code>-</code>: "
              "<code>- 7.5 650</code> — без звёзд, <code>500 7.5</code> — без рублей.")


def fmt_usd(x: float) -> str:
    return f"${x:,.2f}".replace(",", " ").replace(".00", "")


def fmt_rub(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".00", "") + " ₽"


def fmt_price(stars: int, usd: float, rub: float) -> str:
    """Все заданные цены: «$5 / 450 ₽ / 300 ⭐»."""
    parts = []
    if usd:
        parts.append(fmt_usd(usd))
    if rub:
        parts.append(fmt_rub(rub))
    if stars:
        parts.append(f"{stars} ⭐")
    return " / ".join(parts) or "—"


def short_price(stars: int, usd: float, rub: float) -> str:
    """Одна цена для списков и кнопок: доллары, если заданы, иначе рубли, иначе звёзды."""
    if usd:
        return fmt_usd(usd)
    if rub:
        return fmt_rub(rub)
    return f"{stars} ⭐" if stars else "—"


def ch_price(ch) -> Price:
    return ch["price_stars"] or 0, ch["price_usd"] or 0, ch["price_rub"] or 0


def order_price(order) -> Price:
    return order["total_stars"] or 0, order["total_usd"] or 0, order["total_rub"] or 0


def has_price(ch) -> bool:
    return any(ch_price(ch))


def order_totals(channels) -> Price:
    """Сумма заказа по каждой валюте. Если хоть у одного канала цена в валюте не задана —
    в этой валюте заказ не оплатить (0)."""
    prices = [ch_price(c) for c in channels]
    if not prices:
        return 0, 0, 0
    stars = sum(p[0] for p in prices) if all(p[0] for p in prices) else 0
    usd = round(sum(p[1] for p in prices), 2) if all(p[1] for p in prices) else 0
    rub = round(sum(p[2] for p in prices), 2) if all(p[2] for p in prices) else 0
    return stars, usd, rub


def paid_amount(order, method: str) -> str:
    """Сколько получено — в валюте способа оплаты."""
    if method == "stars":
        return f"{order['total_stars']} ⭐"
    if method == "freekassa":
        return fmt_rub(order["total_rub"])
    return fmt_usd(order["total_usd"])


def _num(token) -> float | None:
    if token is None:
        return 0
    s = str(token).strip().replace(",", ".")
    if s in ("", "-", "—"):
        return 0
    try:
        x = float(s)
    except ValueError:
        return None
    return x if x >= 0 else None


def _price(stars, usd, rub) -> Price | None:
    nums = [_num(stars), _num(usd), _num(rub)]
    if any(x is None for x in nums):
        return None
    price = int(nums[0]), round(nums[1], 2), round(nums[2], 2)
    return price if any(price) else None


def parse_price(text: str | None) -> Price | None:
    """«звёзды доллары [рубли]»; 0 или «-» — валюта не задана. Хотя бы одна цена должна быть больше нуля."""
    tokens = re.findall(r"\d+(?:[.,]\d+)?|[-—]", text or "")
    if len(tokens) not in (2, 3):
        return None
    return _price(*tokens, *([None] * (3 - len(tokens))))


def price_from_fields(data: dict) -> Price | None:
    """Цена из полей формы панели price_stars / price_usd / price_rub (пусто — не задана)."""
    return _price(data.get("price_stars"), data.get("price_usd"), data.get("price_rub"))


def price_setting(price: Price) -> str:
    return " ".join(str(x) for x in price)
