import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from keyboards.admin import complaint_card_kb, complaints_list_kb
from services.complaints import (
    REASONS,
    STATUS_LABELS,
    STATUSES,
    count_by_status,
    get_complaint,
    get_complaints_page,
    set_complaint_status,
)
from utils.pagination import PAGE_SIZE, clamp_page, total_pages
from utils.telegram import last_int, safe_edit
from utils.text import breadcrumb, format_date

router = Router()

FILTERS = ("new", "resolved", "rejected", "all")
FILTER_NAMES = {"new": "нові", "resolved": "розглянуті", "rejected": "відхилені", "all": "усі"}


def person(name, username, user_id) -> str:
    """'Анна (@annie), ID 100' або 'Борис, ID 200'."""
    label = name or "Без імені"
    if username:
        label += f" (@{username})"
    return f"{label}, ID {user_id or '—'}"


# ---------- Готові екрани ----------

async def list_view(status: str, page: int):
    if status not in FILTERS:
        status = "new"
    counts = await count_by_status()
    total = counts[status]
    pages = total_pages(total)
    page = clamp_page(page, pages)
    items = await get_complaints_page(status, page, PAGE_SIZE)

    text = f"🚩 Скарги на конспекти\nФільтр: {FILTER_NAMES[status]}\nЗнайдено: {total}"
    if total:
        text += f"\nСторінка {page + 1} з {pages}\n\nОберіть скаргу:"
    else:
        text += "\n\nСкарг з таким статусом немає."
    return text, complaints_list_kb(items, status, page, pages, counts, REASONS)


async def card_view(complaint_id: int):
    item = await get_complaint(complaint_id)
    if item is None:
        return None

    path = breadcrumb(item["group_name"], item["subject_name"], item["topic_title"])
    text = (
        f"🚩 Скарга №{item['id']}\n"
        f"Статус: {STATUS_LABELS[item['status']]}\n"
        f"Усього скарг на цей конспект: {item['total_for_note']}\n\n"
        f"Конспект: «{item['note_title']}»\n"
        f"Шлях: {path}\n"
        f"Автор конспекту: "
        f"{person(item['author_name'], item['author_username'], item['uploaded_by'])}\n\n"
        f"Причина: {REASONS.get(item['reason'], item['reason'])}\n"
        + (f"Коментар: {item['comment']}\n" if item["comment"] else "")
        + f"Від: {person(item['reporter_name'], item['reporter_username'], item['user_id'])}\n"
        f"Дата: {format_date(item['created_at'])}"
    )
    return text, complaint_card_kb(item["id"], item["note_id"], item["status"])


async def show_missing(callback: CallbackQuery) -> None:
    """Скарги вже немає (наприклад, конспект видалили разом зі скаргами)."""
    await callback.answer("Такої скарги немає (можливо, конспект уже видалено).", show_alert=True)
    text, markup = await list_view("new", 0)
    await safe_edit(callback, text, markup)


# ---------- Список ----------

@router.callback_query(F.data == "adm:c")
async def open_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await list_view("new", 0)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:cl:"))
async def filtered_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        _, _, status, page = callback.data.split(":")
        page = int(page)
    except ValueError:
        await callback.answer()
        return

    text, markup = await list_view(status, page)
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Картка ----------

@router.callback_query(F.data.startswith("adm:co:"))
async def open_card(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    complaint_id = last_int(callback.data)
    view = await card_view(complaint_id) if complaint_id is not None else None
    if view is None:
        await show_missing(callback)
        return
    text, markup = view
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Зміна статусу ----------

@router.callback_query(F.data.startswith("adm:cs:"))
async def change_status(callback: CallbackQuery):
    try:
        _, _, complaint_id, status = callback.data.split(":")
        complaint_id = int(complaint_id)
    except ValueError:
        await callback.answer()
        return

    if status not in STATUSES:
        await callback.answer()
        return

    if not await set_complaint_status(complaint_id, status):
        await show_missing(callback)
        return

    logging.info(
        "Адмін %s змінив статус скарги №%s на %s", callback.from_user.id, complaint_id, status
    )
    view = await card_view(complaint_id)
    if view is not None:
        text, markup = view
        await safe_edit(callback, text, markup)
    await callback.answer(f"Статус: {STATUS_LABELS[status]}")
