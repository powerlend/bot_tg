import logging

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from services.users import is_user_blocked, touch_user


class BlockedUserMiddleware(BaseMiddleware):
    """Зупиняє будь-які дії заблокованих користувачів.

    Підключена до всього бота, тому заблокований користувач не може
    ні завантажувати, ні шукати конспекти. Адміністратори не блокуються ніколи.
    """

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        config = data["config"]

        if (
            user is not None
            and user.id not in config.admin_ids
            and await is_user_blocked(user.id)
        ):
            logging.info("Заблокований користувач user_id=%s намагався користуватися ботом", user.id)
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Ваш доступ до бота обмежено.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⛔ Ваш доступ до бота обмежено адміністратором.")
            return None

        if user is not None:
            await touch_user(user.id, user.username, user.first_name)

        return await handler(event, data)
