from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.admin import admin_menu_kb
from services.complaints import count_by_status as complaint_counts
from services.suggestions import count_by_status
from utils.telegram import safe_edit

router = Router()

PANEL_TEXT = "🔐 Адмін-панель\n\nОберіть розділ:"


@router.message(Command("admin"))
async def open_admin(message: Message, state: FSMContext):
    await state.clear()
    counts = await count_by_status()
    complaints = await complaint_counts()
    await message.answer(
        PANEL_TEXT, reply_markup=admin_menu_kb(counts['new'], complaints['new'])
    )


@router.callback_query(F.data == "adm:home")
async def admin_home(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    counts = await count_by_status()
    complaints = await complaint_counts()
    await safe_edit(callback, PANEL_TEXT, admin_menu_kb(counts['new'], complaints['new']))
    await callback.answer()


@router.callback_query(F.data == "adm:close")
async def admin_close(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback, "🔐 Адмін-панель закрито.")
    await callback.answer()


@router.callback_query(F.data == "adm:soon")
async def admin_soon(callback: CallbackQuery):
    await callback.answer(
        "🚧 Цей розділ додамо на наступних кроках.", show_alert=True
    )
