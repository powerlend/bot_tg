import logging
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message


class ThrottlingMiddleware(BaseMiddleware):
    """Захист від спаму: обмежує, скільки дій користувач може зробити за короткий час.

    Якщо за `window` секунд користувач зробив більше `limit` дій (повідомлень
    або натискань кнопок), бот на `cooldown` секунд перестає на нього реагувати.
    Адміністратори не обмежуються. Дані зберігаються в пам'яті й
    скидаються при перезапуску бота.
    """

    def __init__(self, limit: int = 10, window: float = 10.0, cooldown: float = 30.0):
        self.limit = limit
        self.window = window
        self.cooldown = cooldown
        self.hits = {}           # user_id -> час останніх дій
        self.blocked_until = {}  # user_id -> до якого часу діє пауза

    def _cleanup(self, now: float) -> None:
        """Прибирає з пам'яті тих, хто давно нічого не робив."""
        for user_id in list(self.hits):
            recent = [t for t in self.hits[user_id] if now - t < self.window]
            if not recent and self.blocked_until.get(user_id, 0) <= now:
                self.hits.pop(user_id, None)
                self.blocked_until.pop(user_id, None)
            else:
                self.hits[user_id] = recent

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        config = data["config"]

        if user is None or user.id in config.admin_ids:
            return await handler(event, data)

        now = time.monotonic()
        if len(self.hits) > 1000:
            self._cleanup(now)

        # Користувач на паузі: мовчки ігноруємо (щоб не відповідати на кожен спам)
        if now < self.blocked_until.get(user.id, 0):
            if isinstance(event, CallbackQuery):
                await event.answer()
            return None

        hits = [t for t in self.hits.get(user.id, []) if now - t < self.window]
        hits.append(now)
        self.hits[user.id] = hits

        if len(hits) > self.limit:
            self.blocked_until[user.id] = now + self.cooldown
            self.hits[user.id] = []
            logging.warning("Спам: user_id=%s отримав паузу на %s с", user.id, int(self.cooldown))
            text = f"⏳ Занадто багато запитів. Зачекайте {int(self.cooldown)} секунд."
            if isinstance(event, CallbackQuery):
                await event.answer(text, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(text)
            return None

        return await handler(event, data)
