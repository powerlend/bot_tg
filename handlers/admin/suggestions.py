import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from keyboards.admin import confirm_kb, suggestion_card_kb, suggestions_list_kb
from services.suggestions import (
    BULK_DELETE_STATUSES,
    STATUS_LABELS,
    STATUSES,
    count_by_status,
    delete_suggestion,
    delete_suggestions_by_status,
    get_suggestion,
    get_suggestions_page,
    set_suggestion_status,
)
from utils.pagination import PAGE_SIZE, clamp_page, total_pages
from utils.telegram import last_int, safe_edit
from utils.text import format_date

router = Router()

FILTERS = ("new", "in_progress", "done", "rejected", "all")
FILTER_NAMES = {
    "new": "нові",
    "in_progress": "розглядаються",
    "done": "виконані",
    "rejected": "відхилені",
    "all": "усі",
}
USERNAME_RE = re.compile(r"[A-Za-z0-9_]{4,32}")


# ---------- Готові екрани ----------

async def list_view(status: str, page: int):
    if status not in FILTERS:
        status = "new"
    counts = await count_by_status()
    total = counts[status]
    pages = total_pages(total)
    page = clamp_page(page, pages)
    items = await get_suggestions_page(status, page, PAGE_SIZE)

    text = f"💡 Пропозиції\nФільтр: {FILTER_NAMES[status]}\nЗнайдено: {total}"
    if total:
        text += f"\nСторінка {page + 1} з {pages}\n\nОберіть пропозицію:"
    else:
        text += "\n\nПропозицій з таким статусом немає."
    return text, suggestions_list_kb(items, status, page, pages, counts)


def contact_url(user_id, username):
    """Посилання для зв'язку з автором: за username або (якщо його немає) за ID."""
    if username and USERNAME_RE.fullmatch(username):
        return f"https://t.me/{username}"
    if user_id:
        return f"tg://user?id={user_id}"
    return None


async def card_view(suggestion_id: int):
    item = await get_suggestion(suggestion_id)
    if item is None:
        return None

    name = item["first_name"] or "Без імені"
    username = f"@{item['username']}" if item["username"] else "немає"
    text = (
        f"💡 Пропозиція №{item['id']}\n"
        f"Статус: {STATUS_LABELS[item['status']]}\n\n"
        f"Від: {name}\n"
        f"Username: {username}\n"
        f"Telegram ID: {item['user_id'] or '—'}\n"
        f"Надіслано: {format_date(item['created_at'])}\n\n"
        f"{item['text']}"
    )
    markup = suggestion_card_kb(
        item["id"], item["status"], contact_url(item["user_id"], item["username"])
    )
    return text, markup


async def show_missing(callback: CallbackQuery) -> None:
    await callback.answer("Такої пропозиції немає.", show_alert=True)
    text, markup = await list_view("new", 0)
    await safe_edit(callback, text, markup)


# ---------- Список ----------

@router.callback_query(F.data == "adm:v")
async def open_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await list_view("new", 0)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:vl:"))
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

@router.callback_query(F.data.startswith("adm:vo:"))
async def open_card(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    suggestion_id = last_int(callback.data)
    view = await card_view(suggestion_id) if suggestion_id is not None else None
    if view is None:
        await show_missing(callback)
        return
    text, markup = view
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Зміна статусу ----------

@router.callback_query(F.data.startswith("adm:vs:"))
async def change_status(callback: CallbackQuery):
    try:
        _, _, suggestion_id, status = callback.data.split(":")
        suggestion_id = int(suggestion_id)
    except ValueError:
        await callback.answer()
        return

    if status not in STATUSES:
        await callback.answer()
        return

    if not await set_suggestion_status(suggestion_id, status):
        await show_missing(callback)
        return

    logging.info(
        "Адмін %s змінив статус пропозиції №%s на %s",
        callback.from_user.id, suggestion_id, status,
    )
    view = await card_view(suggestion_id)
    if view is not None:
        text, markup = view
        await safe_edit(callback, text, markup)
    await callback.answer(f"Статус: {STATUS_LABELS[status]}")


# ---------- Видалення однієї пропозиції (з підтвердженням) ----------

@router.callback_query(F.data.startswith("adm:vd:"))
async def delete_ask(callback: CallbackQuery):
    suggestion_id = last_int(callback.data)
    item = await get_suggestion(suggestion_id) if suggestion_id is not None else None
    if item is None:
        await show_missing(callback)
        return

    preview = item["text"] if len(item["text"]) <= 200 else item["text"][:200] + "…"
    text = (
        f"⚠️ Видалити пропозицію №{item['id']} ({STATUS_LABELS[item['status']]})?\n\n"
        f"{preview}\n\n"
        "Цю дію не можна скасувати."
    )
    await safe_edit(
        callback, text, confirm_kb(f"adm:vdok:{item['id']}", f"adm:vo:{item['id']}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:vdok:"))
async def delete_confirm(callback: CallbackQuery):
    suggestion_id = last_int(callback.data)
    item = await get_suggestion(suggestion_id) if suggestion_id is not None else None
    if item is None:
        await show_missing(callback)
        return

    await delete_suggestion(item["id"])
    logging.info("Адмін %s видалив пропозицію №%s", callback.from_user.id, item["id"])
    text, markup = await list_view(item["status"], 0)
    await safe_edit(callback, f"✅ Пропозицію №{item['id']} видалено.\n\n{text}", markup)
    await callback.answer()


# ---------- Масове видалення виконаних / відхилених (з підтвердженням) ----------

@router.callback_query(F.data.startswith("adm:vdall:"))
async def delete_all_ask(callback: CallbackQuery):
    status = callback.data.rsplit(":", 1)[-1]
    if status not in BULK_DELETE_STATUSES:
        await callback.answer()
        return

    counts = await count_by_status()
    if counts[status] == 0:
        await callback.answer("Таких пропозицій немає.", show_alert=True)
        return

    word = "виконані" if status == "done" else "відхилені"
    text = (
        f"⚠️ Видалити всі {word} пропозиції ({counts[status]})?\n\n"
        "Нові та ті, що розглядаються, не буде зачеплено.\n"
        "Цю дію не можна скасувати."
    )
    await safe_edit(
        callback, text, confirm_kb(f"adm:vdallok:{status}", f"adm:vl:{status}:0")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:vdallok:"))
async def delete_all_confirm(callback: CallbackQuery):
    status = callback.data.rsplit(":", 1)[-1]
    if status not in BULK_DELETE_STATUSES:
        await callback.answer()
        return

    deleted = await delete_suggestions_by_status(status)
    logging.info(
        "Адмін %s видалив %s пропозицій зі статусом %s", callback.from_user.id, deleted, status
    )
    text, markup = await list_view(status, 0)
    await safe_edit(callback, f"✅ Видалено пропозицій: {deleted}.\n\n{text}", markup)
    await callback.answer()
