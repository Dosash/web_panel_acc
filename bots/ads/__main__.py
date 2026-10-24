import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import BotCommand

from bots.ads import db, live_config
from bots.ads.channel_info import refresh_loop
from bots.ads.config import config, load_config
from bots.ads import broadcast
from bots.ads.handlers import admin, audience, payments, support, user
from bots.ads import ui
from bots.ads.orders import crypto_poll_loop, scheduler_loop
from bots.ads.web import start_panel


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    await db.init_db()
    await live_config.load()      # настройки из веб-панели — поверх .env
    if not config.bot_token:
        raise SystemExit("BOT_TOKEN не задан (ни в .env, ни в панели)")

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        me = await bot.me()
    except TelegramUnauthorizedError:
        env_token = load_config().bot_token
        if not (live_config.overridden("BOT_TOKEN") and env_token and env_token != config.bot_token):
            raise
        # токен из панели отозван — запускаемся со старым из .env, чтобы панель осталась доступной
        logging.error("токен бота из панели не принят Telegram — используется BOT_TOKEN из .env")
        await bot.session.close()
        config.bot_token = env_token
        bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        me = await bot.me()
    dp = Dispatcher()
    # порядок важен: аудитория (блокировки, пост для рассылки) → админка → оплата → пользовательские сценарии (там же «ловушка» прочих сообщений)
    dp.message.outer_middleware(audience.TouchUser())
    dp.callback_query.outer_middleware(audience.TouchUser())
    dp.include_routers(audience.router, admin.router, support.admin_router, admin.events, payments.router,
                       support.user_router, user.router)

    ui.BOT_USERNAME = me.username
    checks = await live_config.verify_clients()
    for key, name, on, off in (("xrocket", "xRocket Pay", "подключён", "отключён"),
                               ("freekassa", "FreeKassa", "подключена", "отключена")):
        if key not in checks:
            logging.warning("%s %s: ключи не заданы", name, off)
        elif checks[key]:
            logging.warning("%s %s: %s", name, off, checks[key])
        else:
            logging.info("%s %s", name, on)
    await bot.set_my_commands([BotCommand(command="start", description="Главное меню / Main menu"),
                               BotCommand(command="lang", description="Язык / Language")])

    panel = await start_panel(bot)
    tasks = [
        asyncio.create_task(crypto_poll_loop(bot)),
        asyncio.create_task(refresh_loop(bot)),
        asyncio.create_task(scheduler_loop(bot)),
        asyncio.create_task(admin.discovery_report_loop(bot)),
        broadcast.resume_all(bot),
    ]
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for t in tasks:
            t.cancel()
        if panel:
            await panel.cleanup()
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
