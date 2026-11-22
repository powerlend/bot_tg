from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.user import courses_kb, groups_kb, main_menu_kb
from services.groups import get_group, get_groups_by_course
from services.users import register_user, set_user_group
from utils.telegram import last_int, safe_edit

router = Router()

COURSE_TEXT = "🎓 На якому ти курсі?"


async def ask_group(message: Message) -> None:
    """Починає вибір групи: спочатку питаємо курс."""
    await message.answer(COURSE_TEXT, reply_markup=courses_kb())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    # /start завжди скидає незавершені дії (наприклад, завантаження)
    await state.clear()

    user = await register_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
    )

    group = None
    if user["group_id"] is not None:
        group = await get_group(user["group_id"])

    if group is None:
        await message.answer(
            "Привіт! 👋\nСпочатку потрібно вибрати курс і навчальну групу."
        )
        await ask_group(message)
        return

    await message.answer(
        f"З поверненням! Ваша група: {group['name']} ({group['course']} курс)",
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data.startswith("crs:"))
async def choose_course(callback: CallbackQuery):
    """Користувач вибрав курс: показуємо групи тільки цього курсу."""
    course = last_int(callback.data)
    if course not in (1, 2, 3, 4):
        await callback.answer()
        return

    groups = await get_groups_by_course(course)
    if groups:
        text = f"🎓 {course} курс\n\nОберіть свою групу:"
    else:
        text = (
            f"🎓 {course} курс\n\n"
            "На цьому курсі поки немає груп.\n"
            "Зверніться до адміністратора, щоб він додав вашу групу."
        )
    await safe_edit(callback, text, groups_kb(groups))
    await callback.answer()


@router.callback_query(F.data == "crsback")
async def back_to_courses(callback: CallbackQuery):
    await safe_edit(callback, COURSE_TEXT, courses_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("grp:"))
async def choose_group(callback: CallbackQuery, state: FSMContext):
    group_id = last_int(callback.data)
    group = await get_group(group_id) if group_id is not None else None
    if group is None:
        await callback.answer(
            "Ця група більше не існує. Почніть вибір спочатку.",
            show_alert=True,
        )
        return

    # Зміна групи скидає незавершене завантаження
    await state.clear()

    user = callback.from_user
    await register_user(user.id, user.username, user.first_name)
    await set_user_group(user.id, group_id)

    await safe_edit(
        callback, f"✅ Групу обрано: {group['name']} ({group['course']} курс)"
    )
    await callback.bot.send_message(
        user.id,
        "Головне меню 👇",
        reply_markup=main_menu_kb(),
    )
    await callback.answer()
