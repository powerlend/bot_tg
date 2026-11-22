from aiogram import F, Router
from aiogram.types import Message

from handlers.start import ask_group
from keyboards.user import BTN_CHANGE_GROUP, BTN_HELP

router = Router()

HELP_TEXT = (
    "ℹ️ Допомога\n\n"
    "📤 Завантажити конспект — додати свій конспект до предмета\n"
    "🔎 Знайти конспект — переглянути й знайти конспекти вашої групи\n"
    "📚 Предмети — список предметів вашої групи\n"
    "🗂 Мої конспекти — ваші конспекти: тег автора, видалення\n"
    "💡 Пропозиції — ідея чи повідомлення про проблему для адміністратора\n"
    "👥 Змінити групу — вибрати іншу навчальну групу\n\n"
    "Бачити конспекти можна лише своєї групи.\n"
    "Якщо з конспектом щось не так, натисніть «🚩 Поскаржитись» під файлом."
)


@router.message(F.text == BTN_CHANGE_GROUP)
async def change_group(message: Message):
    await ask_group(message)


@router.message(F.text == BTN_HELP)
async def show_help(message: Message):
    await message.answer(HELP_TEXT)
