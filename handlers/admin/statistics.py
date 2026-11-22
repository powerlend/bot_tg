from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from keyboards.admin import stats_kb
from services.stats import get_overview, get_period_stats
from utils.telegram import safe_edit

router = Router()


def period_block(title: str, stats) -> str:
    return (
        f"{title}\n"
        f"• нових користувачів: {stats['new_users']}\n"
        f"• додано конспектів: {stats['new_notes']}\n"
        f"• завантажень файлів: {stats['downloads']}\n"
        f"• активних користувачів: {stats['active_users']}"
    )


async def build_stats_text() -> str:
    overview = await get_overview()
    day = await get_period_stats(24)
    week = await get_period_stats(24 * 7)
    month = await get_period_stats(24 * 30)

    return (
        "📊 Статистика\n\n"
        "👤 Користувачі\n"
        f"• усього: {overview['users_total']}\n"
        f"• активних (за 7 днів): {overview['users_active']}\n"
        f"• заблокованих: {overview['users_blocked']}\n\n"
        "📚 Вміст\n"
        f"• груп: {overview['groups_total']}\n"
        f"• предметів: {overview['subjects_total']}\n"
        f"• конспектів: {overview['notes_total']}\n"
        f"• завантажень файлів: {overview['downloads_total']}\n"
        f"• пропозицій: {overview['suggestions_total']} (нових: {overview['suggestions_new']})\n"
        f"• скарг: {overview['complaints_total']} (нових: {overview['complaints_new']})\n\n"
        + period_block("📅 За останні 24 години", day)
        + "\n\n"
        + period_block("📅 За останні 7 днів", week)
        + "\n\n"
        + period_block("📅 За останні 30 днів", month)
    )


@router.callback_query(F.data == "adm:stats")
async def show_statistics(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback, await build_stats_text(), stats_kb())
    await callback.answer()
