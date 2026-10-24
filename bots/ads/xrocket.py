"""Клиент xRocket Pay API (https://docs.xrocket.exchange/api/pay/pay-api-overview).

Авторизация — Bearer-токен приложения из @xRocket → Rocket Pay → приложение → API Token.
"""
import hashlib
import hmac
import time
from typing import Any

import aiohttp

from bots.ads.config import config


class XRocketError(Exception):
    pass


class XRocket:
    def __init__(self, token: str, testnet: bool = False):
        self.token = token
        host = "pay.api.testnet.xrocket.exchange" if testnet else "pay.api.xrocket.exchange"
        self.base = f"https://{host}/api/v1/"
        self.verified = False   # ключ проверен при старте (verify)

    @property
    def enabled(self) -> bool:
        return bool(self.token) and self.verified

    async def _call(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> Any:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.request(method, self.base + path, params=params, json=json,
                                 headers={"Authorization": f"Bearer {self.token}",
                                          "Accept": "application/json"}) as r:
                data = await r.json(content_type=None) if r.content_length != 0 else {}
                if r.status >= 400:
                    detail = (data or {}).get("detail") or (data or {}).get("title") or r.reason
                    raise XRocketError(f"{r.status}: {detail}")
        return data

    async def verify(self) -> str | None:
        """Проверяет ключ. Возвращает текст ошибки или None, если всё в порядке."""
        if not self.token:
            return "XROCKET_TOKEN не задан"
        try:
            await self._call("GET", "app-info")
        except (XRocketError, aiohttp.ClientError, TimeoutError, ValueError) as e:
            self.verified = False
            return str(e)
        self.verified = True
        return None

    def setup(self, token: str) -> None:
        """Новый токен из веб-панели; включится после verify()."""
        self.token = token
        self.verified = False

    async def create_invoice(self, amount_usd: float, description: str, client_id: str,
                             expires_in: int = 24 * 3600) -> dict:
        """Счёт в USDT (1 USDT ≈ 1 $). Оплатить можно любой криптой из кошелька xRocket.

        client_id делает повторную отправку безопасной: тот же client_id второй счёт не создаст.
        """
        return await self._call("POST", "invoices", json={
            "priceAmount": f"{amount_usd:.2f}",
            "priceCurrency": "USDT",
            "numPayments": 1,
            "description": description[:1000],
            "clientInvoiceId": client_id,
            "expiresIn": int(expires_in) * 1000,      # API ждёт миллисекунды
        })

    async def paid_ids(self, limit: int = 100) -> set[str]:
        """ID последних оплаченных счетов — одним запросом (у API лимит 20 запросов в минуту)."""
        data = await self._call("GET", "invoices", params={"status": "paid", "limit": str(limit)})
        return {str(inv["id"]) for inv in data.get("items", [])}

    async def get_invoice(self, invoice_id: str | int) -> dict:
        return await self._call("GET", "invoice", params={"invoiceId": str(invoice_id)})


HOOK_PATH = "/hook/xrocket"         # после префикса панели: /ads/hook/xrocket
HOOK_MARK = "xRocket webhook: ok"    # ответ на GET — по нему проверяем, что домен ведёт на этого бота
hook_stats = {"last": 0}             # время последнего принятого вебхука (для панели)


def webhook_url() -> str:
    return f"https://{config.xrocket_webhook_domain}{config.panel_prefix}{HOOK_PATH}" if config.xrocket_webhook_domain else ""


def webhook_on() -> bool:
    """Вебхук настроен: тогда оплаты xRocket приходят через него, опрос — только как подстраховка."""
    return bool(config.xrocket_webhook_secret and config.xrocket_webhook_domain)


async def probe_webhook() -> str | None:
    """GET на публичный адрес вебхука. Текст ошибки или None, если адрес ведёт на этого бота."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(webhook_url()) as r:
                text = await r.text()
    except (aiohttp.ClientError, TimeoutError, ValueError) as e:
        return f"{webhook_url()} недоступен из интернета ({e.__class__.__name__}: {e})"
    if r.status != 200 or HOOK_MARK not in text:
        return f"{webhook_url()} отвечает, но не ботом (HTTP {r.status}) — проверьте, куда ведёт домен"
    return None


def webhook_valid(headers, raw: bytes, secret: str, tolerance_ms: int = 300_000) -> bool:
    """Подпись вебхука Pay API (https://docs.xrocket.exchange/api/pay/webhooks/signature):
    Signature = hex(HMAC-SHA256(secret, "{Signature-Timestamp}.{сырое тело}")), версия v1, запас по времени 5 минут."""
    sig, ts = headers.get("Signature", ""), headers.get("Signature-Timestamp", "")
    if not secret or not sig or not ts or headers.get("Signature-Version") != "v1":
        return False
    try:
        if abs(time.time() * 1000 - int(ts)) > tolerance_ms:
            return False
    except ValueError:
        return False
    expected = hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig.strip().lower())


xrocket = XRocket(config.xrocket_token)
