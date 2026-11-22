import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.admin import (
    cancel_kb,
    confirm_kb,
    course_pick_kb,
    group_card_kb,
    groups_list_kb,
)
from services.groups import (
    add_group,
    clean_name,
    delete_group,
    get_all_groups,
    get_group,
    get_group_stats,
    rename_group,
    set_group_course,
)
from states.states import AdminStates
from utils.telegram import last_int, safe_edit

router = Router()

MAX_NAME = 50


# ---------- Готові екрани ----------

async def groups_list_view():
    groups = await get_all_groups()
    if groups:
        text = "👥 Керування групами\n\nОберіть групу або додайте нову:"
    else:
        text = "👥 Керування групами\n\nГруп поки немає. Додайте першу."
    return text, groups_list_kb(groups)


async def group_card_view(group_id: int):
    group = await get_group(group_id)
    if group is None:
        return None
    stats = await get_group_stats(group_id)
    text = (
        f"👥 Група {group['name']}\n\n"
        f"Курс: {group['course']}\n"
        f"Предметів: {stats['subjects']}\n"
        f"Конспектів: {stats['notes']}\n"
        f"Студентів: {stats['users']}"
    )
    return text, group_card_kb(group_id)


async def show_missing_group(callback: CallbackQuery) -> None:
    """Група зникла (наприклад, її видалив інший адмін): показуємо актуальний список."""
    await callback.answer("Такої групи вже немає.", show_alert=True)
    text, markup = await groups_list_view()
    await safe_edit(callback, text, markup)


# ---------- Список груп ----------

@router.callback_query(F.data == "adm:g")
async def groups_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text, markup = await groups_list_view()
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Додавання групи: спочатку курс, потім назва ----------

@router.callback_query(F.data == "adm:gadd")
async def group_add_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(
        callback,
        "➕ Нова група\n\nДля якого курсу ця група?",
        course_pick_kb("adm:gnew:", "adm:g"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:gnew:"))
async def group_add_course(callback: CallbackQuery, state: FSMContext):
    course = last_int(callback.data)
    if course not in (1, 2, 3, 4):
        await callback.answer()
        return

    await state.set_state(AdminStates.group_add_name)
    await state.update_data(course=course)
    await safe_edit(
        callback,
        f"➕ Введіть назву нової групи для {course} курсу (до {MAX_NAME} символів).\n"
        "Наприклад: КН-14",
        cancel_kb("adm:g"),
    )
    await callback.answer()


@router.message(AdminStates.group_add_name, F.text, ~F.text.startswith("/"))
async def group_add_name(message: Message, state: FSMContext):
    data = await state.get_data()
    course = data.get("course")
    if course not in (1, 2, 3, 4):
        await state.clear()
        await message.answer("⚠️ Дію скасовано. Відкрийте /admin ще раз.")
        return

    name = clean_name(message.text)
    if not name or len(name) > MAX_NAME:
        await message.answer(
            f"⚠️ Назва має бути від 1 до {MAX_NAME} символів. Спробуйте ще раз.",
            reply_markup=cancel_kb("adm:g"),
        )
        return

    if not await add_group(name, course):
        await message.answer(
            f"⚠️ Група «{name}» уже існує. Введіть іншу назву.",
            reply_markup=cancel_kb("adm:g"),
        )
        return

    await state.clear()
    text, markup = await groups_list_view()
    await message.answer(
        f"✅ Групу «{name}» додано ({course} курс).\n\n{text}", reply_markup=markup
    )


# ---------- Картка групи ----------

@router.callback_query(F.data.startswith("adm:go:"))
async def group_card(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    group_id = last_int(callback.data)
    view = await group_card_view(group_id) if group_id is not None else None
    if view is None:
        await show_missing_group(callback)
        return
    text, markup = view
    await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Зміна курсу групи ----------

@router.callback_query(F.data.startswith("adm:gcrs:"))
async def group_course_pick(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    group_id = last_int(callback.data)
    group = await get_group(group_id) if group_id is not None else None
    if group is None:
        await show_missing_group(callback)
        return

    await safe_edit(
        callback,
        f"🎓 Оберіть курс для групи {group['name']} (зараз {group['course']} курс):",
        course_pick_kb(f"adm:gcrset:{group_id}:", f"adm:go:{group_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:gcrset:"))
async def group_course_set(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        _, _, group_id, course = callback.data.split(":")
        group_id, course = int(group_id), int(course)
    except ValueError:
        await callback.answer()
        return
    if course not in (1, 2, 3, 4):
        await callback.answer()
        return

    if not await set_group_course(group_id, course):
        await show_missing_group(callback)
        return

    logging.info("Адмін %s змінив курс групи id=%s на %s", callback.from_user.id, group_id, course)
    view = await group_card_view(group_id)
    if view is not None:
        text, markup = view
        await safe_edit(callback, text, markup)
    await callback.answer(f"✅ Курс змінено на {course}")


# ---------- Перейменування ----------

@router.callback_query(F.data.startswith("adm:gren:"))
async def group_rename_start(callback: CallbackQuery, state: FSMContext):
    group_id = last_int(callback.data)
    group = await get_group(group_id) if group_id is not None else None
    if group is None:
        await show_missing_group(callback)
        return

    await state.set_state(AdminStates.group_rename_name)
    await state.update_data(group_id=group_id)
    await safe_edit(
        callback,
        f"✏️ Введіть нову назву для групи «{group['name']}» (до {MAX_NAME} символів):",
        cancel_kb(f"adm:go:{group_id}"),
    )
    await callback.answer()


@router.message(AdminStates.group_rename_name, F.text, ~F.text.startswith("/"))
async def group_rename_name(message: Message, state: FSMContext):
    data = await state.get_data()
    group_id = data.get("group_id")
    if group_id is None:
        await state.clear()
        await message.answer("⚠️ Дію скасовано. Відкрийте /admin ще раз.")
        return

    name = clean_name(message.text)
    back = cancel_kb(f"adm:go:{group_id}")
    if not name or len(name) > MAX_NAME:
        await message.answer(
            f"⚠️ Назва має бути від 1 до {MAX_NAME} символів. Спробуйте ще раз.",
            reply_markup=back,
        )
        return

    old_group = await get_group(group_id)
    result = await rename_group(group_id, name)
    if result == "exists":
        await message.answer(
            f"⚠️ Група «{name}» уже існує. Введіть іншу назву.", reply_markup=back
        )
        return

    await state.clear()
    if result == "missing" or old_group is None:
        text, markup = await groups_list_view()
        await message.answer(f"⚠️ Такої групи вже немає.\n\n{text}", reply_markup=markup)
        return

    text, markup = await groups_list_view()
    await message.answer(
        f"✅ Групу перейменовано: «{old_group['name']}» → «{name}».\n\n{text}",
        reply_markup=markup,
    )


# ---------- Видалення (з підтвердженням) ----------

@router.callback_query(F.data.startswith("adm:gdel:"))
async def group_delete_ask(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    group_id = last_int(callback.data)
    group = await get_group(group_id) if group_id is not None else None
    if group is None:
        await show_missing_group(callback)
        return

    stats = await get_group_stats(group_id)
    text = (
        f"⚠️ Видалити групу «{group['name']}»?\n\n"
        f"Разом із нею буде видалено:\n"
        f"• предметів: {stats['subjects']}\n"
        f"• конспектів: {stats['notes']}\n\n"
        f"У студентів цієї групи ({stats['users']}) група стане не вибраною, "
        "і бот попросить їх вибрати нову.\n\n"
        "Цю дію не можна скасувати."
    )
    await safe_edit(
        callback,
        text,
        confirm_kb(f"adm:gdelok:{group_id}", f"adm:go:{group_id}"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:gdelok:"))
async def group_delete_confirm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    group_id = last_int(callback.data)
    group = await get_group(group_id) if group_id is not None else None
    if group is None:
        await show_missing_group(callback)
        return

    await delete_group(group_id)
    logging.info("Адмін %s видалив групу id=%s «%s»", callback.from_user.id, group_id, group["name"])
    text, markup = await groups_list_view()
    await safe_edit(callback, f"✅ Групу «{group['name']}» видалено.\n\n{text}", markup)
    await callback.answer()
