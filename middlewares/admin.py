import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery


class AdminOnlyMiddleware(BaseMiddleware):
    """Пропускає тільки адміністраторів (ID з ADMIN_IDS у файлі .env).

    Підключена до всієї адмін-панелі, тому перевірка виконується
    при кожному натисканні кнопки та при кожному повідомленні,
    а не лише при відкритті панелі.
    """

    async def __call__(self, handler, event, data):
        config = data["config"]
        user = getattr(event, "from_user", None)

        if user is None or user.id not in config.admin_ids:
            logging.warning(
                "Спроба доступу до адмін-функції без прав: user_id=%s",
                user.id if user else None,
            )
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Немає доступу.", show_alert=True)
            return None

        return await handler(event, data)
