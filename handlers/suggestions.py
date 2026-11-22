import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config
from keyboards.admin import suggestion_open_kb
from keyboards.user import BTN_SUGGEST, suggest_cancel_kb
from services.suggestions import add_suggestion, count_recent_suggestions
from services.users import register_user
from states.states import SuggestStates
from utils.telegram import safe_edit

router = Router()

MIN_LEN = 5          # мінімальна довжина пропозиції
MAX_LEN = 1000       # максимальна довжина пропозиції
DAILY_LIMIT = 5      # скільки пропозицій на добу може надіслати один користувач

INTRO_TEXT = (
    "💡 Пропозиції\n\n"
    "Тут можна запропонувати нову функцію, повідомити про проблему "
    "або залишити будь-яку ідею для покращення бота.\n\n"
    f"Напишіть своє повідомлення одним текстом (до {MAX_LEN} символів).\n\n"
    "ℹ️ Адміністратор побачить ваш @username або ID, щоб мати змогу відповісти."
)


def author_label(user) -> str:
    """'Анна (@annie), ID 100' для повідомлення адміністратору."""
    label = user.first_name or "Без імені"
    if user.username:
        label += f" (@{user.username})"
    return f"{label}, ID {user.id}"


async def notify_admins(bot, config: Config, suggestion_id: int, user, text: str) -> None:
    """Сповіщає всіх адміністраторів про нову пропозицію. Помилки лише записуємо в лог."""
    body = f"💡 Нова пропозиція №{suggestion_id}\n\nВід: {author_label(user)}\n\n{text}"
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(
                admin_id, body, reply_markup=suggestion_open_kb(suggestion_id)
            )
        except TelegramAPIError:
            logging.warning("Не вдалося сповістити адміністратора %s про пропозицію", admin_id)


# ---------- Початок: кнопка «Пропозиції» ----------

@router.message(F.text == BTN_SUGGEST)
async def open_suggestions(message: Message, state: FSMContext, config: Config):
    await state.clear()
    if message.from_user is None:
        return

    # Ліміт на добу (адміністраторів не стосується)
    if message.from_user.id not in config.admin_ids:
        recent = await count_recent_suggestions(message.from_user.id, 24)
        if recent >= DAILY_LIMIT:
            await message.answer(
                f"Ви вже надіслали {DAILY_LIMIT} пропозицій за останню добу. "
                "Спробуйте, будь ласка, пізніше. Дякуємо за активність! 🙏"
            )
            return

    await state.set_state(SuggestStates.waiting_text)
    await message.answer(INTRO_TEXT, reply_markup=suggest_cancel_kb())


# ---------- Текст пропозиції ----------

@router.message(SuggestStates.waiting_text, F.text, ~F.text.startswith("/"))
async def got_suggestion(message: Message, state: FSMContext, config: Config):
    user = message.from_user
    if user is None:
        return

    text = message.text.strip()
    if len(text) < MIN_LEN:
        await message.answer(
            f"⚠️ Занадто коротко: напишіть хоча б {MIN_LEN} символів.",
            reply_markup=suggest_cancel_kb(),
        )
        return
    if len(text) > MAX_LEN:
        await message.answer(
            f"⚠️ Занадто довго: максимум {MAX_LEN} символів (у вас {len(text)}). "
            "Скоротіть, будь ласка, і надішліть ще раз.",
            reply_markup=suggest_cancel_kb(),
        )
        return

    # Ліміт перевіряємо ще раз: за час написання могли надіслати іншу пропозицію
    if user.id not in config.admin_ids:
        if await count_recent_suggestions(user.id, 24) >= DAILY_LIMIT:
            await state.clear()
            await message.answer(f"Ви вже надіслали {DAILY_LIMIT} пропозицій за останню добу.")
            return

    # Користувач має існувати в базі (пропозиція прив'язана до його ID)
    await register_user(user.id, user.username, user.first_name)
    suggestion_id = await add_suggestion(user.id, text)
    await state.clear()
    logging.info("Нова пропозиція №%s від %s", suggestion_id, user.id)

    await message.answer(
        f"✅ Дякуємо! Вашу пропозицію прийнято (№{suggestion_id}). "
        "Адміністратор обов'язково її розгляне."
    )
    await notify_admins(message.bot, config, suggestion_id, user, text)


@router.message(SuggestStates.waiting_text, ~F.text.startswith("/"))
async def wrong_type(message: Message):
    await message.answer(
        "Надішліть пропозицію текстом або натисніть «Скасувати».",
        reply_markup=suggest_cancel_kb(),
    )


# ---------- Скасування ----------

@router.callback_query(F.data == "sg_cancel")
async def cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback, "❌ Скасовано.")
    await callback.answer()
