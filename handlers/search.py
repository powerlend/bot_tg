import logging
import re

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from handlers.start import ask_group
from keyboards.user import (
    BTN_FIND,
    back_kb,
    back_menu_kb,
    note_actions_kb,
    find_subjects_kb,
    main_menu_kb,
    search_results_kb,
    topic_notes_kb,
    topics_kb,
)
from services.notes import (
    count_topic_notes,
    get_note,
    get_topic_notes_page,
    increment_downloads,
    search_notes,
)
from services.subjects import get_subject, get_subjects_with_counts
from services.topics import get_topic, get_topics_with_counts
from services.users import get_user_group
from states.states import SearchStates
from utils.pagination import PAGE_SIZE, clamp_page, total_pages
from utils.telegram import last_int, safe_edit
from utils.text import breadcrumb, format_date

router = Router()

SEARCH_LIMIT = 20  # скільки результатів пошуку показувати

# Telegram-username: латиниця, цифри, підкреслення
USERNAME_RE = re.compile(r"[A-Za-z0-9_]{4,32}")


def author_contact(note, viewer_id: int):
    """Рядок про автора і його username для кнопки зв'язку. Показуємо їх ТІЛЬКИ якщо автор
    дозволив тег (і не показуємо автору його ж конспект).
    Повертає (рядок або None, username або None)."""
    if not note["show_author_tag"] or note["uploaded_by"] == viewer_id:
        return None, None

    username = note["author_username"]
    if username and USERNAME_RE.fullmatch(username):
        return f"👤 Автор: @{username}", username
    return (
        "👤 Автор дозволив показувати контакт, але в нього зараз немає @username "
        "у Telegram, тому прямий зв'язок неможливий.",
        None,
    )


# ---------- Готові екрани ----------

async def build_subjects_view(user_id: int):
    """Текст і кнопки зі списком предметів. Повертає None, якщо в користувача немає групи."""
    group = await get_user_group(user_id)
    if group is None:
        return None

    crumb = breadcrumb(f"{group['course']} курс", group["name"])
    subjects = await get_subjects_with_counts(group["id"])
    if not subjects:
        return (
            f"🔎 {crumb}\n\nУ вашій групі поки немає предметів.",
            None,
        )
    return f"🔎 {crumb}\n\nОберіть предмет:", find_subjects_kb(subjects)


async def build_topics_view(user_id: int, subject_id: int, page: int):
    """Папки з темами предмета. None - якщо предмет недоступний користувачу."""
    group = await get_user_group(user_id)
    subject = await get_subject(subject_id)
    # Показуємо тільки предмети групи самого користувача
    if group is None or subject is None or subject["group_id"] != group["id"]:
        return None

    topics = await get_topics_with_counts(subject_id)
    pages = total_pages(len(topics))
    page = clamp_page(page, pages)
    chunk = topics[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    crumb = breadcrumb(f"{group['course']} курс", group["name"], subject["name"])

    if not topics:
        text = (
            f"📂 {crumb}\n\n"
            "Поки що немає жодної теми.\n"
            "Додайте перший конспект через «📤 Завантажити конспект»."
        )
    else:
        text = (
            f"📂 {crumb}\n"
            f"Тем: {len(topics)}\n"
            f"Сторінка {page + 1} з {pages}\n\n"
            "Оберіть тему:"
        )
    return text, topics_kb(chunk, subject_id, page, pages)


async def build_notes_view(user_id: int, topic_id: int, page: int, sort: int):
    """Конспекти однієї теми. None - якщо тема недоступна користувачу."""
    group = await get_user_group(user_id)
    topic = await get_topic(topic_id)
    subject = await get_subject(topic["subject_id"]) if topic else None
    if group is None or subject is None or subject["group_id"] != group["id"]:
        return None

    total = await count_topic_notes(topic_id)
    pages = total_pages(total)
    page = clamp_page(page, pages)
    notes = await get_topic_notes_page(topic_id, page, PAGE_SIZE, newest_first=(sort == 0))
    crumb = breadcrumb(
        f"{group['course']} курс", group["name"], subject["name"], topic["title"]
    )

    if total == 0:
        text = f"📁 {crumb}\n\nУ цій темі поки немає конспектів."
    else:
        order_text = "спочатку нові" if sort == 0 else "спочатку старі"
        text = (
            f"📁 {crumb}\n"
            f"Конспектів: {total}\n"
            f"Сторінка {page + 1} з {pages} ({order_text})\n\n"
            "Оберіть конспект:"
        )
    return text, topic_notes_kb(notes, topic_id, subject["id"], page, pages, sort, total)


# ---------- Початок: кнопка «Знайти конспект» ----------

@router.message(F.text == BTN_FIND)
async def open_find(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user is None:
        return

    view = await build_subjects_view(message.from_user.id)
    if view is None:
        await message.answer("Спочатку потрібно вибрати курс і навчальну групу.")
        await ask_group(message)
        return

    text, markup = view
    await message.answer(text, reply_markup=markup)


# ---------- Предмет → список тем (папок) ----------

# «fn:» - старі кнопки з повідомлень, надісланих до оновлення: ведуть у той самий список тем
@router.callback_query(F.data.startswith("ft:"))
@router.callback_query(F.data.startswith("fn:"))
async def show_topics(callback: CallbackQuery):
    try:
        parts = callback.data.split(":")
        subject_id = int(parts[1])
        page = int(parts[2]) if parts[0] == "ft" and len(parts) > 2 else 0
    except (AttributeError, IndexError, ValueError):
        await callback.answer()
        return

    view = await build_topics_view(callback.from_user.id, subject_id, page)
    if view is None:
        await callback.answer("Цей предмет недоступний.", show_alert=True)
        return

    text, markup = view
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Тема → список конспектів ----------

@router.callback_query(F.data.startswith("fl:"))
async def show_notes(callback: CallbackQuery):
    try:
        _, topic_id, page, sort = callback.data.split(":")
        topic_id, page, sort = int(topic_id), int(page), int(sort)
    except (AttributeError, ValueError):
        await callback.answer()
        return
    sort = 1 if sort == 1 else 0

    view = await build_notes_view(callback.from_user.id, topic_id, page, sort)
    if view is None:
        await callback.answer("Ця тема недоступна.", show_alert=True)
        return

    text, markup = view
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Надсилання файлу ----------

@router.callback_query(F.data.startswith("fo:"))
async def open_note(callback: CallbackQuery):
    note_id = last_int(callback.data)
    if note_id is None:
        await callback.answer()
        return

    group = await get_user_group(callback.from_user.id)
    note = await get_note(note_id)
    # Конспект іншої групи показувати не можна
    if group is None or note is None or note["group_id"] != group["id"]:
        await callback.answer("Цей конспект недоступний.", show_alert=True)
        return

    caption = (
        f"📄 {note['title']}\n"
        f"📁 {note['topic_title'] or '—'}\n"
        f"📚 {note['subject_name']}\n"
        f"📅 Додано: {format_date(note['created_at'])}\n"
        f"⬇️ Завантажень: {note['downloads_count'] + 1}"
    )

    author_line, contact_username = author_contact(note, callback.from_user.id)
    if author_line:
        caption += "\n" + author_line

    # Під файлом: «Написати автору» (якщо дозволено) і «Поскаржитись» (на чужі конспекти)
    markup = note_actions_kb(
        note["id"],
        contact_username,
        can_complain=note["uploaded_by"] != callback.from_user.id,
    )

    try:
        if note["file_type"] == "photo":
            await callback.bot.send_photo(
                callback.from_user.id,
                note["file_id"],
                caption=caption,
                reply_markup=markup,
            )
        else:
            await callback.bot.send_document(
                callback.from_user.id,
                note["file_id"],
                caption=caption,
                reply_markup=markup,
            )
    except TelegramAPIError:
        logging.exception("Не вдалося надіслати конспект id=%s", note_id)
        await callback.answer(
            "Не вдалося надіслати файл. Спробуйте пізніше.", show_alert=True
        )
        return

    await increment_downloads(note_id, callback.from_user.id)
    await callback.answer()


# ---------- Пошук за назвою ----------

@router.callback_query(F.data == "fsearch")
async def start_search(callback: CallbackQuery, state: FSMContext):
    group = await get_user_group(callback.from_user.id)
    if group is None:
        await callback.answer("Спочатку виберіть групу.", show_alert=True)
        return

    await state.set_state(SearchStates.waiting_query)
    await safe_edit(
        callback,
        "🔍 Введіть частину назви конспекту або теми:",
        back_kb(),
    )
    await callback.answer()


@router.message(SearchStates.waiting_query, F.text, ~F.text.startswith("/"))
async def got_query(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    query = " ".join(message.text.split())
    if len(query) < 2 or len(query) > 50:
        await message.answer(
            "⚠️ Запит має бути від 2 до 50 символів. Спробуйте ще раз.",
            reply_markup=back_kb(),
        )
        return

    group = await get_user_group(message.from_user.id)
    if group is None:
        await state.clear()
        await message.answer("Спочатку потрібно вибрати курс і навчальну групу.")
        await ask_group(message)
        return

    matches, found = await search_notes(group["id"], query, SEARCH_LIMIT)
    await state.clear()

    if found == 0:
        await message.answer(
            f"Нічого не знайдено за запитом «{query}».",
            reply_markup=back_menu_kb(),
        )
        return

    text = f"🔍 Результати за запитом «{query}»: знайдено {found}"
    if found > SEARCH_LIMIT:
        text += f"\nПоказано перші {SEARCH_LIMIT}. Уточніть запит, щоб побачити інші."
    await message.answer(text, reply_markup=search_results_kb(matches))


@router.message(SearchStates.waiting_query, ~F.text.startswith("/"))
async def query_wrong_type(message: Message):
    await message.answer(
        "Введіть запит текстом або натисніть «Назад».", reply_markup=back_kb()
    )


# ---------- Навігація ----------

@router.callback_query(F.data == "fback")
async def go_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    view = await build_subjects_view(callback.from_user.id)
    if view is None:
        await callback.answer("Спочатку виберіть групу.", show_alert=True)
        return

    text, markup = view
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "fmenu")
async def go_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback, "🏠 Головне меню")
    await callback.bot.send_message(
        callback.from_user.id, "Оберіть дію 👇", reply_markup=main_menu_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()
