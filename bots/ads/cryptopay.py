"""Минимальный клиент Crypto Pay API (@CryptoBot)."""
from typing import Any

import aiohttp

from bots.ads.config import config


class CryptoPayError(Exception):
    pass


class CryptoPay:
    def __init__(self, token: str, testnet: bool = False):
        self.setup(token, testnet)

    def setup(self, token: str, testnet: bool = False) -> None:
        self.token = token
        host = "testnet-pay.crypt.bot" if testnet else "pay.crypt.bot"
        self.base = f"https://{host}/api/"

    async def verify(self) -> str | None:
        """Проверяет токен. Возвращает текст ошибки или None, если всё в порядке."""
        try:
            await self._call("getMe")
        except (CryptoPayError, aiohttp.ClientError, TimeoutError, ValueError) as e:
            return str(e) or type(e).__name__
        return None

    async def _call(self, method: str, **params: Any) -> Any:
        params = {k: v for k, v in params.items() if v is not None}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(self.base + method, json=params,
                              headers={"Crypto-Pay-API-Token": self.token}) as r:
                data = await r.json(content_type=None)
        if not data.get("ok"):
            raise CryptoPayError(str(data.get("error")))
        return data["result"]

    async def create_invoice(self, amount_usd: float, description: str, payload: str,
                             expires_in: int = 24 * 3600) -> dict:
        # Счёт в долларах — пользователь сам выбирает, какой криптой платить
        return await self._call(
            "createInvoice",
            currency_type="fiat",
            fiat="USD",
            amount=f"{amount_usd:.2f}",
            description=description[:1024],
            payload=payload,
            allow_comments=False,
            allow_anonymous=True,
            expires_in=int(expires_in),
        )

    async def get_invoices(self, invoice_ids: list[int]) -> list[dict]:
        if not invoice_ids:
            return []
        res = await self._call("getInvoices", invoice_ids=",".join(map(str, invoice_ids)))
        return res.get("items", [])


cryptopay = CryptoPay(config.cryptopay_token, config.cryptopay_testnet)
# Для тестовых заказов: тестовая сеть @CryptoTestnetBot (ненастоящие монеты), если задан токен
cryptopay_test = CryptoPay(config.cryptopay_test_token, testnet=True)


def reconfigure() -> None:
    """Применить токены из config (их меняют в веб-панели)."""
    cryptopay.setup(config.cryptopay_token, config.cryptopay_testnet)
    cryptopay_test.setup(config.cryptopay_test_token, testnet=True)


def client_for(order) -> CryptoPay | None:
    """Клиент CryptoPay для заказа. None — если токен для него не задан."""
    client = cryptopay_test if order["is_test"] else cryptopay
    return client if client.token else None
