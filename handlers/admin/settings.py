import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from config import Config
from keyboards.admin import settings_kb
from services.backup import create_backup, send_backup
from utils.telegram import safe_edit

router = Router()


def settings_text(config: Config) -> str:
    if config.backup_enabled:
        schedule = f"щодня о {config.backup_hour:02d}:00 (за UTC)"
    else:
        schedule = "вимкнено (змінюється в .env: BACKUP_ENABLED)"

    if config.litestream_enabled:
        replication = "увімкнена (зміни бази постійно копіюються в хмару)"
    else:
        replication = "не налаштована (потрібна лише на безкоштовному Render)"

    return (
        "⚙️ Налаштування\n\n"
        "💾 Резервне копіювання бази\n"
        f"• Автоматично: {schedule}\n"
        "• Копія надходить адміністраторам у цей чат файлом .zip\n"
        f"• На сервері зберігається останніх копій: {config.backup_keep}\n\n"
        "☁️ Постійна реплікація бази в хмару (Litestream)\n"
        f"• Стан: {replication}\n\n"
        "⚠️ У копії є дані користувачів (ID та імена), тож нікому її не пересилайте."
    )


@router.callback_query(F.data == "adm:settings")
async def show_settings(callback: CallbackQuery, config: Config):
    await safe_edit(callback, settings_text(config), settings_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:backup")
async def backup_now(callback: CallbackQuery, config: Config):
    await callback.answer("💾 Створюю копію, зачекайте...")
    try:
        path = await create_backup(config.db_path, config.backup_keep)
    except Exception:
        logging.exception("Не вдалося створити резервну копію вручну")
        await callback.bot.send_message(
            callback.from_user.id,
            "⚠️ Не вдалося створити копію. Подробиці в logs/bot.log.",
        )
        return

    logging.info("Адмін %s створив резервну копію: %s", callback.from_user.id, path)
    await send_backup(callback.bot, [callback.from_user.id], path)
