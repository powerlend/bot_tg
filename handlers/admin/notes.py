import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.admin import (
    cancel_kb,
    confirm_kb,
    filter_group_kb,
    filter_subject_kb,
    note_card_kb,
    notes_list_kb,
    notes_menu_kb,
    notes_search_results_kb,
)
from services.groups import get_all_groups, get_group
from services.notes import (
    admin_search_notes,
    count_admin_notes,
    delete_note,
    get_admin_notes_page,
    get_note_full,
)
from services.subjects import get_subject, get_subjects_with_counts
from states.states import AdminStates
from utils.pagination import PAGE_SIZE, clamp_page, total_pages
from utils.telegram import last_int, safe_edit, send_note_file
from utils.text import format_date

router = Router()

SEARCH_LIMIT = 20


# ---------- Готові екрани ----------

async def notes_menu_view():
    total = await count_admin_notes(0, 0)
    return f"📄 Керування конспектами\n\nВсього конспектів: {total}", notes_menu_kb()


async def notes_list_view(group_id: int, subject_id: int, page: int):
    """Список конспектів з фільтрами. Неправильні фільтри просто скидаються."""
    group = await get_group(group_id) if group_id else None
    if group is None:
        group_id, subject_id = 0, 0

    subject = None
    if subject_id:
        subject = await get_subject(subject_id)
        if subject is None or subject["group_id"] != group_id:
            subject, subject_id = None, 0

    total = await count_admin_notes(group_id, subject_id)
    pages = total_pages(total)
    page = clamp_page(page, pages)
    notes = await get_admin_notes_page(group_id, subject_id, page, PAGE_SIZE)

    if group is None:
        filter_text = "усі конспекти"
    elif subject is None:
        filter_text = f"група {group['name']}"
    else:
        filter_text = f"група {group['name']} → {subject['name']}"

    text = f"📄 Конспекти\nФільтр: {filter_text}\nЗнайдено: {total}"
    if total > 0:
        text += f"\nСторінка {page + 1} з {pages}\n\nОберіть конспект:"
    else:
        text += "\n\nКонспектів не знайдено."
    return text, notes_list_kb(notes, group_id, subject_id, page, pages)


async def note_card_view(note_id: int):
    note = await get_note_full(note_id)
    if note is None:
        return None

    if note["uploaded_by"] is None:
        author = "невідомий"
    else:
        author = note["author_name"] or "Без імені"
        if note["author_username"]:
            author += f" (@{note['author_username']})"
        author += f", ID {note['uploaded_by']}"

    text = (
        f"📄 {note['title']}\n\n"
        f"📚 Предмет: {note['subject_name']}\n"
        f"📁 Тема: {note['topic_title'] or '—'}\n"
        f"👥 Група: {note['group_name']}\n"
        f"📎 Файл: {note['file_name'] or '—'} ({note['file_type'] or '—'})\n"
        f"👤 Автор: {author}\n"
        f"🏷 Тег автора: {'показується читачам' if note['show_author_tag'] else 'прихований'}\n"
        + (f"🚩 Скарг на конспект: {note['complaints_count']}\n" if note["complaints_count"] else "")
        +
        f"📅 Додано: {format_date(note['created_at'])}\n"
        f"⬇️ Завантажень: {note['downloads_count']}"
    )
    return text, note_card_kb(note_id, note["group_id"], note["subject_id"]), note


async def show_note_missing(callback: CallbackQuery) -> None:
    await callback.answer("Такого конспекту вже немає.", show_alert=True)
    text, markup = await notes_menu_view()
    await safe_edit(callback, text, markup)


# ---------- Меню розділу ----------

@router.callback_query(F.data == "adm:n")
async def notes_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await notes_menu_view()
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Список з фільтрами ----------

@router.callback_query(F.data.startswith("adm:nl:"))
async def notes_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        _, _, group_id, subject_id, page = callback.data.split(":")
        group_id, subject_id, page = int(group_id), int(subject_id), int(page)
    except ValueError:
        await callback.answer()
        return

    text, markup = await notes_list_view(group_id, subject_id, page)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "adm:ng")
async def filter_group(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    groups = await get_all_groups()
    await safe_edit(callback, "👥 Оберіть групу для фільтра:", filter_group_kb(groups))
    await callback.answer()


@router.callback_query(F.data.startswith("adm:nsg:"))
async def filter_subject(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    group_id = last_int(callback.data)
    group = await get_group(group_id) if group_id is not None else None
    if group is None:
        await callback.answer("Такої групи вже немає.", show_alert=True)
        return

    subjects = await get_subjects_with_counts(group_id)
    await safe_edit(
        callback,
        f"📚 Оберіть предмет групи {group['name']}:",
        filter_subject_kb(subjects, group_id),
    )
    await callback.answer()


# ---------- Пошук за назвою ----------

@router.callback_query(F.data == "adm:nsearch")
async def search_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.notes_search)
    await safe_edit(
        callback,
        "🔍 Введіть частину назви конспекту (пошук по всіх групах):",
        cancel_kb("adm:n"),
    )
    await callback.answer()


@router.message(AdminStates.notes_search, F.text, ~F.text.startswith("/"))
async def search_query(message: Message, state: FSMContext):
    query = " ".join(message.text.split())
    if len(query) < 2 or len(query) > 50:
        await message.answer(
            "⚠️ Запит має бути від 2 до 50 символів. Спробуйте ще раз.",
            reply_markup=cancel_kb("adm:n"),
        )
        return

    matches, found = await admin_search_notes(query, SEARCH_LIMIT)
    await state.clear()

    text = f"🔍 Результати за запитом «{query}»: знайдено {found}"
    if found > SEARCH_LIMIT:
        text += f"\nПоказано перші {SEARCH_LIMIT}. Уточніть запит."
    await message.answer(text, reply_markup=notes_search_results_kb(matches))


# ---------- Картка конспекту ----------

@router.callback_query(F.data.startswith("adm:no:"))
async def note_card(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    note_id = last_int(callback.data)
    view = await note_card_view(note_id) if note_id is not None else None
    if view is None:
        await show_note_missing(callback)
        return
    text, markup, _ = view
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:nget:"))
async def note_get_file(callback: CallbackQuery):
    note_id = last_int(callback.data)
    note = await get_note_full(note_id) if note_id is not None else None
    if note is None:
        await show_note_missing(callback)
        return

    caption = f"📄 {note['title']}\n📚 {note['subject_name']} · 👥 {note['group_name']}"
    try:
        await send_note_file(callback.bot, callback.from_user.id, note, caption)
    except TelegramAPIError:
        logging.exception("Адмін не зміг отримати файл конспекту id=%s", note_id)
        await callback.answer("Не вдалося надіслати файл.", show_alert=True)
        return
    await callback.answer()


# ---------- Видалення (з підтвердженням) ----------

@router.callback_query(F.data.startswith("adm:ndel:"))
async def note_delete_ask(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    note_id = last_int(callback.data)
    note = await get_note_full(note_id) if note_id is not None else None
    if note is None:
        await show_note_missing(callback)
        return

    text = (
        f"⚠️ Видалити конспект «{note['title']}»?\n\n"
        f"Предмет: {note['subject_name']}, група {note['group_name']}.\n\n"
        "Цю дію не можна скасувати."
    )
    await safe_edit(
        callback, text, confirm_kb(f"adm:ndelok:{note_id}", f"adm:no:{note_id}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:ndelok:"))
async def note_delete_confirm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    note_id = last_int(callback.data)
    note = await get_note_full(note_id) if note_id is not None else None
    if note is None:
        await show_note_missing(callback)
        return

    await delete_note(note_id)
    logging.info(
        "Адмін %s видалив конспект id=%s «%s»", callback.from_user.id, note_id, note["title"]
    )
    text, markup = await notes_list_view(note["group_id"], note["subject_id"], 0)
    await safe_edit(callback, f"✅ Конспект «{note['title']}» видалено.\n\n{text}", markup)
    await callback.answer()
