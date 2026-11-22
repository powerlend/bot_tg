import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config
from keyboards.admin import (
    cancel_kb,
    user_card_kb,
    users_list_kb,
    users_search_results_kb,
)
from services.users import (
    count_users,
    get_user_card,
    get_users_page,
    search_users,
    set_blocked,
)
from states.states import AdminStates
from utils.pagination import PAGE_SIZE, clamp_page, total_pages
from utils.telegram import last_int, safe_edit
from utils.text import format_date

router = Router()

SEARCH_LIMIT = 20


# ---------- Готові екрани ----------

async def users_list_view(page: int):
    total = await count_users()
    pages = total_pages(total)
    page = clamp_page(page, pages)
    users = await get_users_page(page, PAGE_SIZE)

    text = f"👤 Керування користувачами\n\nВсього користувачів: {total}"
    if total > 0:
        text += f"\nСторінка {page + 1} з {pages}\n\nОберіть користувача:"
    return text, users_list_kb(users, page, pages)


async def user_card_view(telegram_id: int, config: Config):
    user = await get_user_card(telegram_id)
    if user is None:
        return None

    is_admin = telegram_id in config.admin_ids
    username = f"@{user['username']}" if user["username"] else "—"
    status = "⛔ заблокований" if user["is_blocked"] else "🟢 активний"
    text = (
        f"👤 {user['first_name'] or 'Без імені'}"
        f"{' (адміністратор)' if is_admin else ''}\n\n"
        f"Telegram ID: {user['telegram_id']}\n"
        f"Username: {username}\n"
        f"Група: {user['group_name'] or 'не вибрана'}\n"
        f"Перший запуск: {format_date(user['created_at'])}\n"
        f"Завантажено конспектів: {user['notes_count']}\n"
        f"Статус: {status}"
    )
    return text, user_card_kb(telegram_id, bool(user["is_blocked"]), is_admin)


async def show_user_missing(callback: CallbackQuery) -> None:
    await callback.answer("Такого користувача немає.", show_alert=True)
    text, markup = await users_list_view(0)
    await safe_edit(callback, text, markup)


# ---------- Список ----------

@router.callback_query(F.data == "adm:u")
async def users_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await users_list_view(0)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.startswith("adm:ul:"))
async def users_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    page = last_int(callback.data)
    text, markup = await users_list_view(page or 0)
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Пошук ----------

@router.callback_query(F.data == "adm:usearch")
async def search_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.users_search)
    await safe_edit(
        callback,
        "🔍 Введіть Telegram ID, username або ім'я користувача:",
        cancel_kb("adm:u"),
    )
    await callback.answer()


@router.message(AdminStates.users_search, F.text, ~F.text.startswith("/"))
async def search_query(message: Message, state: FSMContext):
    query = " ".join(message.text.split())
    if not query or len(query) > 50:
        await message.answer(
            "⚠️ Запит має бути від 1 до 50 символів. Спробуйте ще раз.",
            reply_markup=cancel_kb("adm:u"),
        )
        return

    matches, found = await search_users(query, SEARCH_LIMIT)
    await state.clear()

    if found == 0:
        await message.answer(
            f"Нікого не знайдено за запитом «{query}».",
            reply_markup=users_search_results_kb([]),
        )
        return

    text = f"🔍 Результати за запитом «{query}»: знайдено {found}"
    if found > SEARCH_LIMIT:
        text += f"\nПоказано перші {SEARCH_LIMIT}. Уточніть запит."
    await message.answer(text, reply_markup=users_search_results_kb(matches))


# ---------- Картка користувача ----------

@router.callback_query(F.data.startswith("adm:uo:"))
async def user_card(callback: CallbackQuery, state: FSMContext, config: Config):
    await state.clear()
    telegram_id = last_int(callback.data)
    view = await user_card_view(telegram_id, config) if telegram_id is not None else None
    if view is None:
        await show_user_missing(callback)
        return
    text, markup = view
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Блокування ----------

async def change_block(callback: CallbackQuery, config: Config, blocked: bool) -> None:
    telegram_id = last_int(callback.data)
    if telegram_id is None:
        await callback.answer()
        return

    # Адміністраторів блокувати не можна
    if telegram_id in config.admin_ids:
        await callback.answer("Адміністратора заблокувати не можна.", show_alert=True)
        return

    if not await set_blocked(telegram_id, blocked):
        await show_user_missing(callback)
        return

    logging.info(
        "Адмін %s %s користувача %s",
        callback.from_user.id,
        "заблокував" if blocked else "розблокував",
        telegram_id,
    )
    view = await user_card_view(telegram_id, config)
    if view is not None:
        text, markup = view
        await safe_edit(callback, text, markup)
    await callback.answer("⛔ Заблоковано" if blocked else "✅ Розблоковано")


@router.callback_query(F.data.startswith("adm:ublock:"))
async def block_user(callback: CallbackQuery, config: Config):
    await change_block(callback, config, True)


@router.callback_query(F.data.startswith("adm:uunblock:"))
async def unblock_user(callback: CallbackQuery, config: Config):
    await change_block(callback, config, False)
