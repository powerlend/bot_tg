import asyncio
import logging
import os
import sqlite3

import aiosqlite

from database.migrations import migrate

logger = logging.getLogger(__name__)

# Одне спільне підключення до бази на весь час роботи бота
_connection = None


async def init_db(db_path: str) -> None:
    """Створює або оновлює базу, потім відкриває підключення."""
    global _connection

    folder = os.path.dirname(db_path)
    if folder:
        os.makedirs(folder, exist_ok=True)

    try:
        # Створення або оновлення структури (виконується в окремому потоці)
        await asyncio.to_thread(migrate, db_path)

        _connection = await aiosqlite.connect(db_path)
        _connection.row_factory = aiosqlite.Row
        # Без цього SQLite не перевіряє зв'язки між таблицями
        await _connection.execute("PRAGMA foreign_keys = ON")
        # Якщо база зайнята (наприклад, Litestream робить контрольну точку), чекаємо до 5 с, а не падаємо
        await _connection.execute("PRAGMA busy_timeout = 5000")
        await _connection.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.Error:
        logger.exception("Не вдалося підготувати базу даних")
        raise

    logger.info("База даних готова: %s", db_path)


def get_db() -> aiosqlite.Connection:
    """Повертає підключення до бази (його використовують сервіси)."""
    if _connection is None:
        raise RuntimeError("База даних ще не ініціалізована")
    return _connection


async def close_db() -> None:
    """Закриває базу при зупинці бота."""
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None
        logger.info("Базу даних закрито")
