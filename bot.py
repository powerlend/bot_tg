import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent

from config import load_config
from database.db import close_db, init_db
from handlers import (
    complaints,
    menu,
    my_notes,
    search,
    start,
    subjects,
    suggestions,
    upload,
)
from handlers.admin import router as admin_router
from middlewares.access import BlockedUserMiddleware
from middlewares.throttling import ThrottlingMiddleware
from services.backup import backup_scheduler
from services.keepalive import keep_alive_loop, start_health_server


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(
            "logs/bot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        ),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
    )


async def on_error(event: ErrorEvent):
    """Усі помилки пишемо в лог, а користувачу показуємо коротке повідомлення."""
    logging.error("Помилка при обробці оновлення", exc_info=event.exception)

    update = event.update
    try:
        if update.message:
            await update.message.answer(
                "⚠️ Сталася помилка. Спробуйте пізніше."
            )
        elif update.callback_query:
            await update.callback_query.answer(
                "⚠️ Сталася помилка. Спробуйте пізніше.", show_alert=True
            )
    except Exception:
        logging.exception("Не вдалося повідомити користувача про помилку")
    return True


async def main():
    setup_logging()
    config = load_config()

    # Сторінка здоров'я для хостингу (Render вимагає відкритий порт)
    health_server = None
    if config.port:
        health_server = await start_health_server(config.port)
        logging.info("Сторінка здоров'я запущена на порту %s", config.port)

    await init_db(config.db_path)

    bot = Bot(token=config.bot_token)
    # config передаємо в диспетчер, щоб обробники могли його отримувати
    dp = Dispatcher(config=config)
    dp.errors.register(on_error)
    # Захист від спаму (перевірка швидка, тому стоїть першою)
    dp.message.outer_middleware(ThrottlingMiddleware())
    dp.callback_query.outer_middleware(ThrottlingMiddleware())
    # Заблоковані користувачі не можуть користуватися ботом
    dp.message.outer_middleware(BlockedUserMiddleware())
    dp.callback_query.outer_middleware(BlockedUserMiddleware())

    dp.include_router(admin_router)
    dp.include_router(start.router)
    dp.include_router(subjects.router)
    dp.include_router(menu.router)
    dp.include_router(search.router)
    dp.include_router(my_notes.router)
    dp.include_router(suggestions.router)
    dp.include_router(complaints.router)
    dp.include_router(upload.router)

    # Щоденні резервні копії бази (працюють у фоні)
    backup_task = None
    if config.backup_enabled and config.admin_ids:
        backup_task = asyncio.create_task(backup_scheduler(bot, config))

    # Самопінг: щоб безкоштовний сервіс не засинав
    keepalive_task = None
    if config.keepalive_url and config.port:
        keepalive_task = asyncio.create_task(keep_alive_loop(config.keepalive_url))

    logging.info("Бот запускається...")
    try:
        await dp.start_polling(bot)
    finally:
        for task in (backup_task, keepalive_task):
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if health_server is not None:
            health_server.close()
            await health_server.wait_closed()
        await bot.session.close()
        await close_db()
        logging.info("Бот зупинено")


if __name__ == "__main__":
    asyncio.run(main())
