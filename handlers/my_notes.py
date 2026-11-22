import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.user import (
    BTN_MY_NOTES,
    my_note_card_kb,
    my_note_delete_kb,
    my_notes_kb,
)
from services.notes import (
    count_user_notes,
    delete_own_note,
    get_note_full,
    get_user_notes_page,
    set_author_tag,
)
from utils.pagination import PAGE_SIZE, clamp_page, total_pages
from utils.telegram import last_int, safe_edit, send_note_file
from utils.text import breadcrumb, format_date

router = Router()


# ---------- Готові екрани ----------

async def my_notes_view(user_id: int, page: int):
    total = await count_user_notes(user_id)
    pages = total_pages(total)
    page = clamp_page(page, pages)
    notes = await get_user_notes_page(user_id, page, PAGE_SIZE)

    if total == 0:
        text = (
            "🗂 Мої конспекти\n\n"
            "Ви ще не додали жодного конспекту.\n"
            "Натисніть «📤 Завантажити конспект» у меню."
        )
    else:
        text = (
            f"🗂 Мої конспекти\n\nУсього: {total}\n"
            f"Сторінка {page + 1} з {pages}\n\nОберіть конспект:"
        )
    return text, my_notes_kb(notes, page, pages)


async def own_note(note_id, user_id: int):
    """Конспект, якщо його додав саме цей користувач. Інакше None."""
    if note_id is None:
        return None
    note = await get_note_full(note_id)
    if note is None or note["uploaded_by"] != user_id:
        return None
    return note


def note_card_text(note) -> str:
    if note["show_author_tag"]:
        username = note["author_username"]
        tag = f"👁 показується (@{username})" if username else "👁 увімкнений, але у вас немає @username"
    else:
        tag = "🔒 прихований"
    path = breadcrumb(note["group_name"], note["subject_name"], note["topic_title"])
    return (
        f"📄 {note['title']}\n\n"
        f"📁 {path}\n"
        f"📅 Додано: {format_date(note['created_at'])}\n"
        f"⬇️ Завантажень: {note['downloads_count']}\n"
        f"👤 Тег автора: {tag}"
    )


async def deny(callback: CallbackQuery) -> None:
    await callback.answer("Цей конспект недоступний.", show_alert=True)


# ---------- Список ----------

@router.message(F.text == BTN_MY_NOTES)
async def open_my_notes(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user is None:
        return
    text, markup = await my_notes_view(message.from_user.id, 0)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("mn:"))
async def my_notes_page(callback: CallbackQuery):
    page = last_int(callback.data)
    text, markup = await my_notes_view(callback.from_user.id, page or 0)
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Картка конспекту ----------

@router.callback_query(F.data.startswith("mo:"))
async def my_note_card(callback: CallbackQuery):
    note = await own_note(last_int(callback.data), callback.from_user.id)
    if note is None:
        await deny(callback)
        return
    await safe_edit(
        callback, note_card_text(note), my_note_card_kb(note["id"], bool(note["show_author_tag"]))
    )
    await callback.answer()


# ---------- Тег автора: показати / приховати ----------

@router.callback_query(F.data.startswith("mt:"))
async def my_note_toggle_tag(callback: CallbackQuery):
    try:
        _, note_id, value = callback.data.split(":")
        note_id, show = int(note_id), value == "1"
    except (AttributeError, ValueError):
        await callback.answer()
        return

    note = await own_note(note_id, callback.from_user.id)
    if note is None:
        await deny(callback)
        return

    if show and not callback.from_user.username:
        await callback.answer(
            "У вас немає @username у Telegram. Створіть його в налаштуваннях Telegram "
            "і спробуйте ще раз.",
            show_alert=True,
        )
        return

    await set_author_tag(note_id, callback.from_user.id, show)
    note = await own_note(note_id, callback.from_user.id)
    await safe_edit(
        callback, note_card_text(note), my_note_card_kb(note_id, bool(note["show_author_tag"]))
    )
    await callback.answer("👁 Тег показується" if show else "🔒 Тег прихований")


# ---------- Отримати свій файл ----------

@router.callback_query(F.data.startswith("mg:"))
async def my_note_get_file(callback: CallbackQuery):
    note = await own_note(last_int(callback.data), callback.from_user.id)
    if note is None:
        await deny(callback)
        return

    caption = f"📄 {note['title']}\n📁 {note['topic_title'] or '—'} · 📚 {note['subject_name']}"
    try:
        await send_note_file(callback.bot, callback.from_user.id, note, caption)
    except TelegramAPIError:
        logging.exception("Не вдалося надіслати власний конспект id=%s", note["id"])
        await callback.answer("Не вдалося надіслати файл.", show_alert=True)
        return
    await callback.answer()


# ---------- Видалення власного конспекту (з підтвердженням) ----------

@router.callback_query(F.data.startswith("md:"))
async def my_note_delete_ask(callback: CallbackQuery):
    note = await own_note(last_int(callback.data), callback.from_user.id)
    if note is None:
        await deny(callback)
        return

    text = (
        f"⚠️ Видалити конспект «{note['title']}»?\n\n"
        "Його більше не побачать інші студенти. Цю дію не можна скасувати."
    )
    await safe_edit(callback, text, my_note_delete_kb(note["id"]))
    await callback.answer()


@router.callback_query(F.data.startswith("mdok:"))
async def my_note_delete_confirm(callback: CallbackQuery):
    note = await own_note(last_int(callback.data), callback.from_user.id)
    if note is None:
        await deny(callback)
        return

    # Видалення виконується тільки для власного конспекту (перевіряється ще й у запиті)
    if not await delete_own_note(note["id"], callback.from_user.id):
        await deny(callback)
        return

    logging.info("Користувач %s видалив свій конспект id=%s", callback.from_user.id, note["id"])
    text, markup = await my_notes_view(callback.from_user.id, 0)
    await safe_edit(callback, f"✅ Конспект «{note['title']}» видалено.\n\n{text}", markup)
    await callback.answer()
