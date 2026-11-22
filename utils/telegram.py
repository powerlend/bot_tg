import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message


async def safe_edit(callback: CallbackQuery, text: str, markup=None) -> None:
    """Змінює текст повідомлення з кнопками й ігнорує помилку «нічого не змінилось»."""
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            logging.warning("Не вдалося змінити повідомлення: %s", error)


def last_int(data):
    """'adm:go:15' -> 15. Якщо числа немає, повертає None."""
    try:
        return int(data.rsplit(":", 1)[1])
    except (AttributeError, IndexError, ValueError):
        return None


async def send_note_file(bot, chat_id: int, note, caption: str) -> None:
    """Надсилає файл конспекту: фото - як фото, решту - як документ."""
    if note["file_type"] == "photo":
        await bot.send_photo(chat_id, note["file_id"], caption=caption)
    else:
        await bot.send_document(chat_id, note["file_id"], caption=caption)
