"""
Точка входа Telegram-бота RAMO.
aiogram v3 + polling.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot import config
from bot.handlers import menu, registration, library, tasks, handover, incident, control, admin, events, promos, task_manager
from bot.middlewares.auth import AuthMiddleware
from bot.utils.db_connector import init_db, init_promos
from bot.utils.cache_manager import get_cache_manager
from bot.utils.menu_db import init_menu_db
from bot.utils import promo_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """Действия при старте бота."""
    logger.info("⚙️ Инициализация базы данных...")
    await init_db()
    await init_promos()
    init_menu_db()
    logger.info("✅ База данных готова")

    logger.info("⚙️ Инициализация кэша...")
    cache_manager = get_cache_manager()
    logger.info("✅ Кэш инициализирован")

    asyncio.create_task(promo_scheduler.scheduler_loop(bot))
    logger.info("✅ Планировщик акций запущен")

    await bot.set_my_commands([
        types.BotCommand(command="start", description="Главное меню / Регистрация"),
        types.BotCommand(command="sync", description="Синхронизировать данные (admin)"),
    ])
    logger.info("✅ Команды бота установлены")


async def on_error(event: types.ErrorEvent):
    """
    Ловит любое необработанное исключение при обработке update.
    Логирует traceback и, если это callback, снимает «часики» с кнопки,
    чтобы у пользователя не было ощущения зависания.
    """
    logger.exception(
        "Необработанная ошибка при обработке update",
        exc_info=event.exception,
    )
    callback = event.update.callback_query
    if callback is not None:
        try:
            await callback.answer()
        except Exception:
            pass
    return True  # помечаем как обработанное, чтобы aiogram не дублировал лог


async def main():
    # Проверка BOT_TOKEN (происходит при импорте config)
    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN не найден в .env")

    # aiogram 3.7.0+: parse_mode через DefaultBotProperties
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.startup.register(on_startup)

    # Глобальный перехватчик ошибок: гарантирует, что inline-кнопка не «зависнет»
    # в состоянии загрузки, даже если хендлер упал с исключением до callback.answer().
    dp.errors.register(on_error)

    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Регистрация всех маршрутизаторов (порядок важен — admin раньше menu)
    dp.include_router(registration.router)
    dp.include_router(admin.router)
    dp.include_router(events.router)
    dp.include_router(promos.router)
    dp.include_router(task_manager.router)
    dp.include_router(menu.router)
    dp.include_router(library.router)
    dp.include_router(tasks.router)
    dp.include_router(handover.router)
    dp.include_router(incident.router)
    dp.include_router(control.router)

    logger.info("🤖 Бот RAMO запущен. Ожидаю сообщения...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())