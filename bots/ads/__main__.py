import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.types import BotCommand, User

from bots.ads import db, live_config
from bots.ads.channel_info import refresh_loop
from bots.ads.config import config, load_config
from bots.ads import broadcast
from bots.ads.handlers import admin, audience, payments, support, user
from bots.ads import ui
from bots.ads.orders import crypto_poll_loop, recover_paid, scheduler_loop
from bots.ads.web import start_panel

log = logging.getLogger("bots.ads")
TASKS_STOP_TIMEOUT = 20   # сколько ждём незавершённые обработчики (оплата, публикация) при остановке


def new_bot() -> Bot:
    return Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def wait_telegram(bot: Bot) -> User:
    """getMe с повторами: без связи с Telegram не падаем — панель уже работает, ждём сеть."""
    while True:
        try:
            return await bot.me()
        except TelegramNetworkError as e:
            log.warning("Telegram недоступен (%s) — повтор через 5 с", e)
            await asyncio.sleep(5)


async def wait_stop() -> None:
    """Токен не принят: бот не работает, но панель остаётся — ждём SIGTERM (остановка или смена токена в панели)."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):   # Windows
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
    await stop.wait()


def _task_done(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("фоновая задача %s упала", task.get_name(), exc_info=task.exception())


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    await db.init_db()
    await live_config.load()      # настройки из веб-панели — поверх .env
    if not config.bot_token:
        raise SystemExit("BOT_TOKEN не задан (ни в .env, ни в панели)")

    bot = new_bot()
    # панель — до связи с Telegram: TG Panel ждёт /api/health, а настройки должны открываться и без сети
    panel = await start_panel(bot)
    tasks: list[asyncio.Task] = []
    try:
        try:
            me = await wait_telegram(bot)
        except TelegramUnauthorizedError:
            env_token = load_config().bot_token
            if not (live_config.overridden("BOT_TOKEN") and env_token and env_token != config.bot_token):
                log.error("Telegram не принял токен бота — бот не запущен, панель работает: "
                          "задайте верный токен в настройках панели (бот перезапустится сам)")
                await wait_stop()
                return
            # токен из панели отозван — запускаемся со старым из .env, чтобы панель осталась доступной
            log.error("токен бота из панели не принят Telegram — используется BOT_TOKEN из .env")
            await bot.session.close()
            config.bot_token = env_token
            bot = new_bot()
            if panel:   # панель привязана к объекту Bot — поднимаем её заново с новым
                await panel.cleanup()
                panel = await start_panel(bot)
            try:
                me = await wait_telegram(bot)
            except TelegramUnauthorizedError:
                log.error("Telegram не принял и BOT_TOKEN из .env — бот не запущен, панель работает")
                await wait_stop()
                return
        dp = Dispatcher()
        # порядок важен: оплата звёздами (чтобы её не перехватили другие обработчики) → аудитория (блокировки,
        # пост для рассылки) → админка → оплата → пользовательские сценарии (там же «ловушка» прочих сообщений)
        dp.message.outer_middleware(audience.TouchUser())
        dp.callback_query.outer_middleware(audience.TouchUser())
        dp.include_routers(payments.early_router, audience.router, admin.router, support.admin_router, admin.events,
                           payments.router, support.user_router, user.router)

        ui.BOT_USERNAME = me.username
        checks = await live_config.verify_clients()
        for key, name, on, off in (("xrocket", "xRocket Pay", "подключён", "отключён"),
                                   ("freekassa", "FreeKassa", "подключена", "отключена")):
            if key not in checks:
                log.warning("%s %s: ключи не заданы", name, off)
            elif checks[key]:
                log.warning("%s %s: %s", name, off, checks[key])
            else:
                log.info("%s %s", name, on)
        try:
            await bot.set_my_commands([BotCommand(command="start", description="Главное меню / Main menu"),
                                       BotCommand(command="lang", description="Язык / Language")])
        except TelegramNetworkError as e:
            log.warning("не удалось задать команды бота: %s", e)

        await recover_paid(bot)   # заказы, оплата или публикация которых прервалась остановкой процесса
        tasks = [
            asyncio.create_task(crypto_poll_loop(bot), name="crypto_poll"),
            asyncio.create_task(refresh_loop(bot), name="channels_refresh"),
            asyncio.create_task(scheduler_loop(bot), name="scheduler"),
            asyncio.create_task(admin.discovery_report_loop(bot), name="discovery_report"),
            broadcast.resume_all(bot),
        ]
        for task in tasks:
            task.add_done_callback(_task_done)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        for task in tasks:
            task.cancel()
        if panel:
            await panel.cleanup()
        # обработчики ещё в работе (оплата, публикация) должны дойти до конца, пока база открыта
        others = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        try:
            await asyncio.wait_for(asyncio.gather(*others, return_exceptions=True), TASKS_STOP_TIMEOUT)
        except TimeoutError:
            log.warning("не все задачи завершились за %s с — останавливаемся", TASKS_STOP_TIMEOUT)
        await db.close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
