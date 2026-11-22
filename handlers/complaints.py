import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config
from handlers.suggestions import author_label
from keyboards.admin import complaint_open_kb
from keyboards.user import complaint_cancel_kb, complaint_reasons_kb
from services.complaints import (
    REASONS,
    add_complaint,
    count_recent_complaints,
    has_complained,
)
from services.notes import get_note
from services.users import get_user_group, register_user
from states.states import ComplaintStates
from utils.telegram import last_int, safe_edit
from utils.text import breadcrumb

router = Router()

MIN_COMMENT = 5      # мінімальна довжина опису проблеми
MAX_COMMENT = 500    # максимальна довжина опису проблеми
DAILY_LIMIT = 10     # скільки скарг на добу може надіслати один користувач

THANKS_TEXT = "✅ Дякуємо! Скаргу прийнято, адміністратор перевірить конспект."


# ---------- Допоміжні функції ----------

async def check_can_complain(user, note_id, config: Config):
    """Перевіряє, чи може користувач поскаржитись на конспект.
    Повертає (конспект, None) або (None, текст помилки)."""
    note = await get_note(note_id) if note_id is not None else None
    group = await get_user_group(user.id)
    # Скаржитись можна лише на конспекти своєї групи
    if note is None or group is None or note["group_id"] != group["id"]:
        return None, "Цей конспект недоступний."
    if note["uploaded_by"] == user.id:
        return None, "На власний конспект скаржитись не можна."
    if await has_complained(note["id"], user.id):
        return None, "Ви вже скаржились на цей конспект. Дякуємо!"
    if user.id not in config.admin_ids:
        if await count_recent_complaints(user.id, 24) >= DAILY_LIMIT:
            return None, f"Ви вже надіслали {DAILY_LIMIT} скарг за добу. Спробуйте пізніше."
    return note, None


async def save_complaint(bot, user, config: Config, note, reason: str, comment):
    """Зберігає скаргу й сповіщає адміністраторів. Повертає номер скарги або None (дубль)."""
    await register_user(user.id, user.username, user.first_name)
    complaint_id = await add_complaint(note["id"], user.id, reason, comment)
    if complaint_id is None:
        return None

    logging.info("Нова скарга №%s на конспект id=%s від %s", complaint_id, note["id"], user.id)
    path = breadcrumb(note["subject_name"], note["topic_title"])
    body = (
        f"🚩 Нова скарга №{complaint_id}\n\n"
        f"Конспект: «{note['title']}» ({path})\n"
        f"Причина: {REASONS[reason]}\n"
        + (f"Коментар: {comment}\n" if comment else "")
        + f"Від: {author_label(user)}"
    )
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(admin_id, body, reply_markup=complaint_open_kb(complaint_id))
        except TelegramAPIError:
            logging.warning("Не вдалося сповістити адміністратора %s про скаргу", admin_id)
    return complaint_id


# ---------- Крок 1. Кнопка «Поскаржитись» під файлом ----------

@router.callback_query(F.data.startswith("cx:"))
async def start_complaint(callback: CallbackQuery, state: FSMContext, config: Config):
    note, error = await check_can_complain(callback.from_user, last_int(callback.data), config)
    if error:
        await callback.answer(error, show_alert=True)
        return

    await state.clear()
    await callback.bot.send_message(
        callback.from_user.id,
        f"🚩 Скарга на конспект «{note['title']}»\n\nОберіть причину:",
        reply_markup=complaint_reasons_kb(note["id"], REASONS),
    )
    await callback.answer()


# ---------- Крок 2. Вибір причини ----------

@router.callback_query(F.data.startswith("cxr:"))
async def choose_reason(callback: CallbackQuery, state: FSMContext, config: Config):
    try:
        _, note_id, reason = callback.data.split(":")
        note_id = int(note_id)
    except ValueError:
        await callback.answer()
        return
    if reason not in REASONS:
        await callback.answer()
        return

    note, error = await check_can_complain(callback.from_user, note_id, config)
    if error:
        await callback.answer(error, show_alert=True)
        return

    if reason == "other":
        # Для «Інша причина» просимо короткий опис
        await state.set_state(ComplaintStates.waiting_comment)
        await state.update_data(note_id=note_id)
        await safe_edit(
            callback,
            f"✏️ Опишіть проблему кількома словами "
            f"(від {MIN_COMMENT} до {MAX_COMMENT} символів):",
            complaint_cancel_kb(),
        )
        await callback.answer()
        return

    await state.clear()
    complaint_id = await save_complaint(
        callback.bot, callback.from_user, config, note, reason, None
    )
    await safe_edit(
        callback,
        THANKS_TEXT if complaint_id else "Ви вже скаржились на цей конспект. Дякуємо!",
    )
    await callback.answer()


# ---------- Крок 3 (лише для «Інша причина»). Опис проблеми ----------

@router.message(ComplaintStates.waiting_comment, F.text, ~F.text.startswith("/"))
async def got_comment(message: Message, state: FSMContext, config: Config):
    if message.from_user is None:
        return

    text = message.text.strip()
    if len(text) < MIN_COMMENT or len(text) > MAX_COMMENT:
        await message.answer(
            f"⚠️ Опис має бути від {MIN_COMMENT} до {MAX_COMMENT} символів "
            f"(у вас {len(text)}). Спробуйте ще раз.",
            reply_markup=complaint_cancel_kb(),
        )
        return

    data = await state.get_data()
    note, error = await check_can_complain(message.from_user, data.get("note_id"), config)
    if error:
        await state.clear()
        await message.answer("⚠️ " + error)
        return

    complaint_id = await save_complaint(
        message.bot, message.from_user, config, note, "other", text
    )
    await state.clear()
    await message.answer(
        THANKS_TEXT if complaint_id else "Ви вже скаржились на цей конспект. Дякуємо!"
    )


@router.message(ComplaintStates.waiting_comment, ~F.text.startswith("/"))
async def comment_wrong_type(message: Message):
    await message.answer(
        "Опишіть проблему текстом або натисніть «Скасувати».",
        reply_markup=complaint_cancel_kb(),
    )


# ---------- Скасування ----------

@router.callback_query(F.data == "cx_cancel")
async def cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback, "❌ Скасовано.")
    await callback.answer()
