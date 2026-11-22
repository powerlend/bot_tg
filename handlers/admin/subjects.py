from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.admin import (
    cancel_kb,
    confirm_kb,
    pick_group_kb,
    subject_card_kb,
    subjects_list_kb,
)
from services.groups import clean_name, get_all_groups, get_group
from services.notes import count_notes
from services.topics import count_topics
from services.subjects import (
    add_subject,
    delete_subject,
    get_subject,
    get_subjects_with_counts,
    rename_subject,
)
from states.states import AdminStates
from utils.telegram import last_int, safe_edit

router = Router()

MAX_NAME = 100


# ---------- Готові екрани ----------

async def pick_group_view():
    groups = await get_all_groups()
    if groups:
        text = "📚 Керування предметами\n\nОберіть групу:"
    else:
        text = "📚 Керування предметами\n\nГруп поки немає. Спочатку додайте групу."
    return text, pick_group_kb(groups)


async def subjects_list_view(group_id: int):
    group = await get_group(group_id)
    if group is None:
        return None
    subjects = await get_subjects_with_counts(group_id)
    if subjects:
        text = f"📚 Предмети групи {group['name']}\n\nОберіть предмет або додайте новий:"
    else:
        text = f"📚 Предмети групи {group['name']}\n\nПредметів поки немає. Додайте перший."
    return text, subjects_list_kb(subjects, group_id)


async def subject_card_view(subject_id: int):
    subject = await get_subject(subject_id)
    if subject is None:
        return None
    group = await get_group(subject["group_id"])
    notes = await count_notes(subject_id)
    topics = await count_topics(subject_id)
    text = (
        f"📚 Предмет: {subject['name']}\n"
        f"Група: {group['name'] if group else '—'}\n"
        f"Тем (папок): {topics}\n"
        f"Конспектів: {notes}"
    )
    return text, subject_card_kb(subject_id, subject["group_id"])


async def show_missing(callback: CallbackQuery, what: str) -> None:
    """Група або предмет зникли: показуємо актуальний вибір груп."""
    await callback.answer(f"{what} уже немає.", show_alert=True)
    text, markup = await pick_group_view()
    await safe_edit(callback, text, markup)


# ---------- Вибір групи ----------

@router.callback_query(F.data == "adm:s")
async def choose_group(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await pick_group_view()
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Список предметів групи ----------

@router.callback_query(F.data.startswith("adm:sg:"))
async def subjects_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    group_id = last_int(callback.data)
    view = await subjects_list_view(group_id) if group_id is not None else None
    if view is None:
        await show_missing(callback, "Такої групи")
        return
    text, markup = view
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Додавання предмета ----------

@router.callback_query(F.data.startswith("adm:sadd:"))
async def subject_add_start(callback: CallbackQuery, state: FSMContext):
    group_id = last_int(callback.data)
    group = await get_group(group_id) if group_id is not None else None
    if group is None:
        await show_missing(callback, "Такої групи")
        return

    await state.set_state(AdminStates.subject_add_name)
    await state.update_data(group_id=group_id)
    await safe_edit(
        callback,
        f"➕ Введіть назву нового предмета для групи {group['name']} "
        f"(до {MAX_NAME} символів).\nНаприклад: Вища математика",
        cancel_kb(f"adm:sg:{group_id}"),
    )
    await callback.answer()


@router.message(AdminStates.subject_add_name, F.text, ~F.text.startswith("/"))
async def subject_add_name(message: Message, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("group_id")
    if group_id is None:
        await state.clear()
        await message.answer("⚠️ Дію скасовано. Відкрийте /admin ще раз.")
        return

    name = clean_name(message.text)
    back = cancel_kb(f"adm:sg:{group_id}")
    if not name or len(name) > MAX_NAME:
        await message.answer(
            f"⚠️ Назва має бути від 1 до {MAX_NAME} символів. Спробуйте ще раз.",
            reply_markup=back,
        )
        return

    group = await get_group(group_id)
    if group is None:
        await state.clear()
        text, markup = await pick_group_view()
        await message.answer(f"⚠️ Такої групи вже немає.\n\n{text}", reply_markup=markup)
        return

    if not await add_subject(group_id, name):
        await message.answer(
            f"⚠️ Предмет «{name}» у групі {group['name']} уже існує. Введіть іншу назву.",
            reply_markup=back,
        )
        return

    await state.clear()
    text, markup = (await subjects_list_view(group_id))
    await message.answer(f"✅ Предмет «{name}» додано.\n\n{text}", reply_markup=markup)


# ---------- Картка предмета ----------

@router.callback_query(F.data.startswith("adm:so:"))
async def subject_card(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    subject_id = last_int(callback.data)
    view = await subject_card_view(subject_id) if subject_id is not None else None
    if view is None:
        await show_missing(callback, "Такого предмета")
        return
    text, markup = view
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Перейменування ----------

@router.callback_query(F.data.startswith("adm:sren:"))
async def subject_rename_start(callback: CallbackQuery, state: FSMContext):
    subject_id = last_int(callback.data)
    subject = await get_subject(subject_id) if subject_id is not None else None
    if subject is None:
        await show_missing(callback, "Такого предмета")
        return

    await state.set_state(AdminStates.subject_rename_name)
    await state.update_data(subject_id=subject_id)
    await safe_edit(
        callback,
        f"✏️ Введіть нову назву для предмета «{subject['name']}» (до {MAX_NAME} символів):",
        cancel_kb(f"adm:so:{subject_id}"),
    )
    await callback.answer()


@router.message(AdminStates.subject_rename_name, F.text, ~F.text.startswith("/"))
async def subject_rename_name(message: Message, state: FSMContext):
    data = await state.get_data()
    subject_id = data.get("subject_id")
    if subject_id is None:
        await state.clear()
        await message.answer("⚠️ Дію скасовано. Відкрийте /admin ще раз.")
        return

    name = clean_name(message.text)
    back = cancel_kb(f"adm:so:{subject_id}")
    if not name or len(name) > MAX_NAME:
        await message.answer(
            f"⚠️ Назва має бути від 1 до {MAX_NAME} символів. Спробуйте ще раз.",
            reply_markup=back,
        )
        return

    subject = await get_subject(subject_id)
    if subject is None:
        await state.clear()
        text, markup = await pick_group_view()
        await message.answer(f"⚠️ Такого предмета вже немає.\n\n{text}", reply_markup=markup)
        return

    result = await rename_subject(subject_id, name)
    if result == "exists":
        await message.answer(
            f"⚠️ Предмет «{name}» у цій групі вже є. Введіть іншу назву.",
            reply_markup=back,
        )
        return

    await state.clear()
    text, markup = await subjects_list_view(subject["group_id"])
    await message.answer(
        f"✅ Предмет перейменовано: «{subject['name']}» → «{name}».\n\n{text}",
        reply_markup=markup,
    )


# ---------- Видалення (з підтвердженням) ----------

@router.callback_query(F.data.startswith("adm:sdel:"))
async def subject_delete_ask(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    subject_id = last_int(callback.data)
    subject = await get_subject(subject_id) if subject_id is not None else None
    if subject is None:
        await show_missing(callback, "Такого предмета")
        return

    group = await get_group(subject["group_id"])
    notes = await count_notes(subject_id)
    text = (
        f"⚠️ Видалити предмет «{subject['name']}» (група {group['name'] if group else '—'})?\n\n"
        f"Разом із ним буде видалено конспектів: {notes}.\n\n"
        "Цю дію не можна скасувати."
    )
    await safe_edit(
        callback,
        text,
        confirm_kb(f"adm:sdelok:{subject_id}", f"adm:so:{subject_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:sdelok:"))
async def subject_delete_confirm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    subject_id = last_int(callback.data)
    subject = await get_subject(subject_id) if subject_id is not None else None
    if subject is None:
        await show_missing(callback, "Такого предмета")
        return

    await delete_subject(subject_id)
    view = await subjects_list_view(subject["group_id"])
    if view is None:
        text, markup = await pick_group_view()
    else:
        text, markup = view
    await safe_edit(callback, f"✅ Предмет «{subject['name']}» видалено.\n\n{text}", markup)
    await callback.answer()
