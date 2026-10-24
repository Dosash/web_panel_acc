"""FreeKassa (https://docs.freekassa.net): оплата в рублях — СБП, карты, кошельки, FKWallet.

Ссылка на оплату — форма SCI (подпись — секретное слово 1): способ оплаты покупатель выбирает на странице
FreeKassa. Факт оплаты проверяем опросом API (подпись — API-ключ), без вебхуков: серверу не нужен
публичный адрес.
"""
import asyncio
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import aiohttp

from bots.ads.config import config

API = "https://api.fk.life/v1/"
PAY_FORM = "https://pay.fk.money/"
STATUS_PAID = 1


class FreeKassaError(Exception):
    pass


def amount_str(x: float) -> str:
    """Сумма одинаково и в ссылке, и в подписи: 1500 или 1500.50."""
    return str(int(x)) if float(x).is_integer() else f"{x:.2f}"


class FreeKassa:
    def __init__(self, shop_id: str, api_key: str, secret: str):
        self._nonce = 0
        self._lock = asyncio.Lock()  # nonce должен расти — запросы идут строго по очереди
        self.setup(shop_id, api_key, secret)

    def setup(self, shop_id: str, api_key: str, secret: str) -> None:
        """Ключи из .env или веб-панели; включится после verify()."""
        self.shop_id = shop_id
        self.api_key = api_key
        self.secret = secret
        self.verified = False

    @property
    def configured(self) -> bool:
        return bool(self.shop_id and self.api_key and self.secret)

    @property
    def enabled(self) -> bool:
        return self.configured and self.verified

    def _sign(self, data: dict) -> str:
        msg = "|".join(str(data[k]) for k in sorted(data))
        return hmac.new(self.api_key.encode(), msg.encode(), hashlib.sha256).hexdigest()

    async def _call(self, path: str, **params: Any) -> dict:
        async with self._lock:
            self._nonce = max(self._nonce + 1, time.time_ns() // 1_000_000)
            data = {"shopId": int(self.shop_id), "nonce": self._nonce,
                    **{k: v for k, v in params.items() if v is not None}}
            data["signature"] = self._sign(data)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
                async with s.post(API + path, json=data) as r:
                    res = await r.json(content_type=None)
        if r.status >= 400 or not isinstance(res, dict) or res.get("type") != "success":
            detail = res.get("message") or res.get("error") if isinstance(res, dict) else None
            raise FreeKassaError(f"{r.status}: {detail or res}")
        return res

    async def verify(self) -> str | None:
        """Проверяет ключи. Возвращает текст ошибки или None, если всё в порядке."""
        if not self.configured:
            return "FREEKASSA_SHOP_ID / FREEKASSA_API_KEY / FREEKASSA_SECRET не заданы"
        try:
            await self._call("balance")
        except (FreeKassaError, aiohttp.ClientError, TimeoutError, ValueError) as e:
            self.verified = False
            return str(e)
        self.verified = True
        return None

    def pay_url(self, payment_id: str, amount_rub: float, lang: str | None = "ru") -> str:
        """Ссылка на форму оплаты. Сумму, валюту и номер заказа закрывает подпись — подменить их нельзя."""
        oa = amount_str(amount_rub)
        sign = hashlib.md5(f"{self.shop_id}:{oa}:{self.secret}:RUB:{payment_id}".encode()).hexdigest()
        return PAY_FORM + "?" + urlencode({"m": self.shop_id, "oa": oa, "currency": "RUB", "o": payment_id,
                                           "s": sign, "lang": "en" if lang == "en" else "ru"})

    async def is_paid(self, payment_id: str) -> bool:
        res = await self._call("orders", paymentId=payment_id, orderStatus=STATUS_PAID)
        return any(str(o.get("merchant_order_id")) == payment_id and int(o.get("status", -1)) == STATUS_PAID
                   for o in res.get("orders") or [])


freekassa = FreeKassa(config.freekassa_shop_id, config.freekassa_api_key, config.freekassa_secret)
