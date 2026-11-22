import asyncio
import logging
import os
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone

from aiogram.exceptions import TelegramAPIError
from aiogram.types import FSInputFile

logger = logging.getLogger(__name__)

# Telegram не приймає від ботів файли більші за 50 МБ, беремо з запасом
MAX_SEND_MB = 45

# Щоб два бекапи (наприклад, ручний і автоматичний) не створювались одночасно
_lock = asyncio.Lock()


def get_backups_dir(db_path: str) -> str:
    """Папка для копій лежить поруч із файлом бази: data/backups."""
    return os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")


def _make_backup_sync(db_path: str, keep: int) -> str:
    """Робить безпечну копію бази, перевіряє її, архівує і прибирає старі копії."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Файл бази не знайдено: {db_path}")

    backups_dir = get_backups_dir(db_path)
    os.makedirs(backups_dir, exist_ok=True)

    # Ім'я містить мілісекунди, щоб дві копії ніколи не отримали однакову назву
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d_%H-%M-%S") + f"_{now.microsecond // 1000:03d}"
    tmp_db = os.path.join(backups_dir, f"bot_{stamp}.db")
    zip_path = os.path.join(backups_dir, f"bot_{stamp}.zip")

    try:
        # Офіційний спосіб копіювання працюючої бази SQLite: копія завжди цілісна
        source = sqlite3.connect(db_path, timeout=30)
        try:
            dest = sqlite3.connect(tmp_db)
            try:
                source.backup(dest)
                result = dest.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                dest.close()
        finally:
            source.close()

        if result != "ok":
            raise RuntimeError(f"Копія бази пошкоджена: {result}")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(tmp_db, arcname="bot.db")
    except Exception:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        raise
    finally:
        if os.path.exists(tmp_db):
            os.remove(tmp_db)

    # Залишаємо тільки останні `keep` копій
    archives = sorted(
        name for name in os.listdir(backups_dir)
        if name.startswith("bot_") and name.endswith(".zip")
    )
    for name in archives[:-keep] if keep > 0 else []:
        os.remove(os.path.join(backups_dir, name))

    return zip_path


async def create_backup(db_path: str, keep: int = 7) -> str:
    """Створює резервну копію (у окремому потоці, щоб бот не зависав). Повертає шлях до zip."""
    async with _lock:
        return await asyncio.to_thread(_make_backup_sync, db_path, keep)


async def send_backup(bot, chat_ids, zip_path: str) -> None:
    """Надсилає файл копії в Telegram вказаним користувачам (адміністраторам)."""
    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    name = os.path.basename(zip_path)

    if size_mb > MAX_SEND_MB:
        logger.warning("Копія завелика для Telegram (%.1f МБ): %s", size_mb, zip_path)
        for chat_id in chat_ids:
            try:
                await bot.send_message(
                    chat_id,
                    f"⚠️ Резервна копія створена, але завелика для Telegram "
                    f"({size_mb:.1f} МБ). Вона лежить на сервері: {name}",
                )
            except TelegramAPIError:
                logger.exception("Не вдалося повідомити адміністратора %s", chat_id)
        return

    caption = f"💾 Резервна копія бази\n{name}\nРозмір: {size_mb:.2f} МБ"
    for chat_id in chat_ids:
        try:
            await bot.send_document(chat_id, FSInputFile(zip_path), caption=caption)
        except TelegramAPIError:
            logger.exception("Не вдалося надіслати копію адміністратору %s", chat_id)


def seconds_until(hour_utc: int, now=None) -> float:
    """Скільки секунд до найближчої години hour_utc:00 (за UTC)."""
    now = now or datetime.now(timezone.utc)
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def backup_scheduler(bot, config) -> None:
    """Щодня о config.backup_hour (UTC) робить копію й надсилає її адміністраторам."""
    logger.info(
        "Автоматичні копії увімкнено: щодня о %02d:00 UTC, зберігаємо останні %s",
        config.backup_hour, config.backup_keep,
    )
    while True:
        await asyncio.sleep(seconds_until(config.backup_hour))
        try:
            path = await create_backup(config.db_path, config.backup_keep)
            await send_backup(bot, config.admin_ids, path)
            logger.info("Резервну копію створено: %s", path)
        except Exception:
            logger.exception("Не вдалося створити резервну копію")
            for chat_id in config.admin_ids:
                try:
                    await bot.send_message(
                        chat_id,
                        "⚠️ Не вдалося створити автоматичну резервну копію. "
                        "Подробиці в logs/bot.log.",
                    )
                except TelegramAPIError:
                    pass
        await asyncio.sleep(1)
