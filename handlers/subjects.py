from aiogram import F, Router
from aiogram.types import Message

from handlers.start import ask_group
from keyboards.user import BTN_SUBJECTS
from services.subjects import get_subjects_with_counts
from services.users import get_user_group
from utils.text import plural_notes

router = Router()


@router.message(F.text == BTN_SUBJECTS)
async def show_subjects(message: Message):
    if message.from_user is None:
        return

    group = await get_user_group(message.from_user.id)
    if group is None:
        await message.answer("Спочатку потрібно вибрати навчальну групу.")
        await ask_group(message)
        return

    subjects = await get_subjects_with_counts(group["id"])
    if not subjects:
        await message.answer(
            f"📚 Предмети групи {group['name']}\n\n"
            "Поки що немає жодного предмета.\n"
            "Зверніться до адміністратора, щоб він їх додав."
        )
        return

    lines = [f"📚 Предмети групи {group['name']}:", ""]
    for subject in subjects:
        lines.append(f"• {subject['name']} — {plural_notes(subject['notes_count'])}")
    await message.answer("\n".join(lines))
