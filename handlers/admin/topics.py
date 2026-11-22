import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.admin import (
    admin_menu_kb,
    cancel_kb,
    confirm_kb,
    topic_card_kb,
    topics_list_kb,
)
from services.groups import clean_name, get_group
from services.notes import count_topic_notes
from services.subjects import get_subject
from services.topics import (
    delete_topic,
    get_topic,
    get_topics_with_counts,
    rename_topic,
)
from states.states import AdminStates
from utils.pagination import PAGE_SIZE, clamp_page, total_pages
from utils.telegram import last_int, safe_edit

router = Router()

MAX_NAME = 100


# ---------- Готові екрани ----------

async def topics_list_view(subject_id: int, page: int):
    subject = await get_subject(subject_id)
    if subject is None:
        return None
    group = await get_group(subject["group_id"])

    topics = await get_topics_with_counts(subject_id)
    pages = total_pages(len(topics))
    page = clamp_page(page, pages)
    chunk = topics[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    text = (
        f"📁 Теми предмета {subject['name']} (група {group['name'] if group else '—'})\n\n"
        f"Всього тем: {len(topics)}"
    )
    if topics:
        text += f"\nСторінка {page + 1} з {pages}\n\nОберіть тему:"
    else:
        text += "\n\nТем поки немає. Вони створюються автоматично, коли студенти додають конспекти."
    return text, topics_list_kb(chunk, subject_id, page, pages)


async def topic_card_view(topic_id: int):
    topic = await get_topic(topic_id)
    if topic is None:
        return None
    subject = await get_subject(topic["subject_id"])
    group = await get_group(subject["group_id"]) if subject else None
    notes = await count_topic_notes(topic_id)
    text = (
        f"📁 Тема: {topic['title']}\n\n"
        f"Предмет: {subject['name'] if subject else '—'}\n"
        f"Група: {group['name'] if group else '—'}\n"
        f"Конспектів: {notes}"
    )
    return text, topic_card_kb(topic_id, topic["subject_id"]), topic


async def show_missing_topic(callback: CallbackQuery, subject_id=None) -> None:
    """Тему вже видалено: повертаємо адміна до списку тем або в головне меню панелі."""
    await callback.answer("Такої теми вже немає.", show_alert=True)
    view = await topics_list_view(subject_id, 0) if subject_id is not None else None
    if view is not None:
        text, markup = view
        await safe_edit(callback, text, markup)
    else:
        await safe_edit(callback, "🔐 Адмін-панель\n\nОберіть розділ:", admin_menu_kb())


# ---------- Список тем предмета ----------

@router.callback_query(F.data.startswith("adm:tl:"))
async def topics_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        _, _, subject_id, page = callback.data.split(":")
        subject_id, page = int(subject_id), int(page)
    except ValueError:
        await callback.answer()
        return

    view = await topics_list_view(subject_id, page)
    if view is None:
        await show_missing_topic(callback)
        return
    text, markup = view
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Картка теми ----------

@router.callback_query(F.data.startswith("adm:to:"))
async def topic_card(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    topic_id = last_int(callback.data)
    view = await topic_card_view(topic_id) if topic_id is not None else None
    if view is None:
        await show_missing_topic(callback)
        return
    text, markup, _ = view
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Перейменування ----------

@router.callback_query(F.data.startswith("adm:tren:"))
async def topic_rename_start(callback: CallbackQuery, state: FSMContext):
    topic_id = last_int(callback.data)
    topic = await get_topic(topic_id) if topic_id is not None else None
    if topic is None:
        await show_missing_topic(callback)
        return

    await state.set_state(AdminStates.topic_rename_name)
    await state.update_data(topic_id=topic_id)
    await safe_edit(
        callback,
        f"✏️ Введіть нову назву для теми «{topic['title']}» (до {MAX_NAME} символів):",
        cancel_kb(f"adm:to:{topic_id}"),
    )
    await callback.answer()


@router.message(AdminStates.topic_rename_name, F.text, ~F.text.startswith("/"))
async def topic_rename_name(message: Message, state: FSMContext):
    data = await state.get_data()
    topic_id = data.get("topic_id")
    if topic_id is None:
        await state.clear()
        await message.answer("⚠️ Дію скасовано. Відкрийте /admin ще раз.")
        return

    name = clean_name(message.text)
    back = cancel_kb(f"adm:to:{topic_id}")
    if not name or len(name) > MAX_NAME:
        await message.answer(
            f"⚠️ Назва має бути від 1 до {MAX_NAME} символів. Спробуйте ще раз.",
            reply_markup=back,
        )
        return

    topic = await get_topic(topic_id)
    if topic is None:
        await state.clear()
        await message.answer("⚠️ Такої теми вже немає. Відкрийте /admin ще раз.")
        return

    result = await rename_topic(topic_id, name)
    if result == "exists":
        await message.answer(
            f"⚠️ Тема «{name}» у цьому предметі вже є. Введіть іншу назву.",
            reply_markup=back,
        )
        return

    await state.clear()
    view = await topics_list_view(topic["subject_id"], 0)
    text, markup = view
    await message.answer(
        f"✅ Тему перейменовано: «{topic['title']}» → «{name}».\n\n{text}",
        reply_markup=markup,
    )


# ---------- Видалення (з підтвердженням) ----------

@router.callback_query(F.data.startswith("adm:tdel:"))
async def topic_delete_ask(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    topic_id = last_int(callback.data)
    topic = await get_topic(topic_id) if topic_id is not None else None
    if topic is None:
        await show_missing_topic(callback)
        return

    notes = await count_topic_notes(topic_id)
    text = (
        f"⚠️ Видалити тему «{topic['title']}»?\n\n"
        f"Разом із нею буде видалено конспектів: {notes}.\n\n"
        "Цю дію не можна скасувати."
    )
    await safe_edit(
        callback, text, confirm_kb(f"adm:tdelok:{topic_id}", f"adm:to:{topic_id}")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:tdelok:"))
async def topic_delete_confirm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    topic_id = last_int(callback.data)
    topic = await get_topic(topic_id) if topic_id is not None else None
    if topic is None:
        await show_missing_topic(callback)
        return

    await delete_topic(topic_id)
    logging.info(
        "Адмін %s видалив тему id=%s «%s»", callback.from_user.id, topic_id, topic["title"]
    )
    view = await topics_list_view(topic["subject_id"], 0)
    text, markup = view
    await safe_edit(callback, f"✅ Тему «{topic['title']}» видалено.\n\n{text}", markup)
    await callback.answer()
