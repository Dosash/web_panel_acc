import os
from dataclasses import dataclass

# Переменные окружения задаёт TG Panel при запуске бота (app/bots.py), .env панели не читаем


@dataclass
class Config:
    """Значения из .env. Часть из них можно переопределить в веб-панели (bot/live_config.py) —
    тогда они меняются прямо в этом объекте, без перезапуска."""
    bot_token: str
    cryptopay_token: str
    cryptopay_testnet: bool
    admin_ids: list[int]     # список меняется на месте: на него ссылаются фильтры роутеров
    db_path: str
    test_channel_id: int | None
    cryptopay_test_token: str
    timezone: str
    work_start: int          # первый слот дня (час)
    work_end: int            # последний слот дня (час)
    booking_days: int        # на сколько дней вперёд можно бронировать
    min_lead_minutes: int    # минимум до времени публикации при бронировании
    xrocket_token: str
    xrocket_webhook_secret: str  # вебхук xRocket: секрет из настроек приложения в @xRocket
    xrocket_webhook_domain: str  # и публичный HTTPS-домен бота; без любого из них — только опрос
    freekassa_shop_id: str   # FreeKassa: ID магазина
    freekassa_api_key: str   # API-ключ (проверка оплат)
    freekassa_secret: str    # секретное слово 1 (подпись ссылки на оплату)
    panel_host: str
    panel_port: int          # 0 — панель выключена
    panel_prefix: str        # путь панели за nginx хаба, например /ads
    panel_password: str      # пусто — без логина (как у соседних панелей в LAN)


def load_config() -> Config:
    admins = list(int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x)
    return Config(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        cryptopay_token=os.getenv("CRYPTOPAY_TOKEN", ""),
        cryptopay_testnet=os.getenv("CRYPTOPAY_TESTNET", "false").lower() == "true",
        admin_ids=admins,
        db_path=os.getenv("DB_PATH", "data/bot.db"),
        test_channel_id=int(os.getenv("TEST_CHANNEL_ID")) if os.getenv("TEST_CHANNEL_ID") else None,
        cryptopay_test_token=os.getenv("CRYPTOPAY_TESTNET_TOKEN", ""),
        timezone=os.getenv("TIMEZONE", "Europe/Moscow"),
        work_start=int(os.getenv("WORK_HOURS", "9-22").split("-")[0]),
        work_end=int(os.getenv("WORK_HOURS", "9-22").split("-")[1]),
        booking_days=int(os.getenv("BOOKING_DAYS", "14")),
        min_lead_minutes=int(os.getenv("MIN_LEAD_MINUTES", "60")),
        xrocket_token=os.getenv("XROCKET_TOKEN", ""),
        xrocket_webhook_secret=os.getenv("XROCKET_WEBHOOK_TOKEN", "").strip(),
        xrocket_webhook_domain=os.getenv("XROCKET_WEBHOOK_DOMAIN", "").strip(),
        freekassa_shop_id=os.getenv("FREEKASSA_SHOP_ID", "").strip(),
        freekassa_api_key=os.getenv("FREEKASSA_API_KEY", "").strip(),
        freekassa_secret=os.getenv("FREEKASSA_SECRET", "").strip(),
        panel_host=os.getenv("PANEL_HOST", "0.0.0.0"),
        panel_port=int(os.getenv("PANEL_PORT", "8093")),
        panel_prefix="/" + os.getenv("PANEL_PREFIX", "/ads").strip("/"),
        panel_password=os.getenv("PANEL_PASSWORD", ""),
    )


config = load_config()
