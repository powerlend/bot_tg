import os
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config
from handlers.start import ask_group
from keyboards.user import (
    BTN_UPLOAD,
    cancel_kb,
    skip_cancel_kb,
    subjects_kb,
    tag_choice_kb,
    upload_topics_kb,
)
from services.notes import add_note, count_recent_uploads
from services.subjects import get_subject, get_subjects_with_counts
from services.topics import find_topic, get_topic, get_topics_with_counts
from services.users import get_user_group
from states.states import UploadStates
from utils.files import FORMATS_TEXT, check_file, get_extension
from utils.pagination import PAGE_SIZE, clamp_page, total_pages
from utils.telegram import last_int, safe_edit
from utils.text import breadcrumb

router = Router()

MAX_TOPIC = 100  # довжина назви теми
MAX_TITLE = 150  # довжина назви конспекту

NEW_TOPIC_PROMPT = (
    "📁 Введіть назву теми (папки), наприклад:\n"
    "Тема 1. Границі\n\n"
    "Якщо така тема вже є, конспект потрапить у неї."
)
NOTE_NAME_PROMPT = (
    "✏️ Введіть назву конспекту (наприклад: Конспект Іваненка)\n"
    "або натисніть «Пропустити» — тоді назвою буде ім'я файлу."
)


# ---------- Допоміжні функції ----------

def crumb_for(group, subject, topic_title=None) -> str:
    return breadcrumb(
        f"{group['course']} курс", group["name"], subject["name"], topic_title
    )


async def get_group_and_subject(user_id: int, subject_id):
    """Група користувача й предмет, якщо предмет належить цій групі. Інакше (None, None)."""
    group = await get_user_group(user_id)
    subject = await get_subject(subject_id) if subject_id is not None else None
    if group is None or subject is None or subject["group_id"] != group["id"]:
        return None, None
    return group, subject


async def picker_view(group, subject, page: int):
    """Текст і кнопки вибору теми. Повертає також виправлений номер сторінки."""
    topics = await get_topics_with_counts(subject["id"])
    pages = total_pages(len(topics))
    page = clamp_page(page, pages)
    chunk = topics[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    text = (
        f"📤 {crumb_for(group, subject)}\n\n"
        "📁 Оберіть тему (папку) для конспекту або створіть нову:"
    )
    return text, upload_topics_kb(chunk, page, pages), page


async def prompt_file(bot, chat_id: int, state: FSMContext, config: Config) -> None:
    """Просить надіслати файл і переводить у відповідний стан."""
    await state.set_state(UploadStates.waiting_file)
    await bot.send_message(
        chat_id,
        "📎 Тепер надішліть файл конспекту.\n\n"
        f"Підтримуються: {FORMATS_TEXT}.\n"
        f"Максимальний розмір: {config.max_file_mb} МБ.\n"
        "Фото краще надсилати як файл (без стискання).",
        reply_markup=cancel_kb(),
    )


async def ask_tag(bot, user, state: FSMContext, config: Config) -> None:
    """Питає, чи показувати @username автора під конспектом. Вибір добровільний.
    Якщо у користувача немає username, пояснюємо це й одразу переходимо до файлу."""
    if not user.username:
        await state.update_data(show_tag=0)
        await bot.send_message(
            user.id,
            "ℹ️ У вас немає @username у Telegram, тому тег автора показати неможливо: "
            "конспект буде без контакту.\n\n"
            "Щоб студенти могли вам написати, створіть username у налаштуваннях Telegram, "
            "а потім увімкніть тег у «🗂 Мої конспекти».",
        )
        await prompt_file(bot, user.id, state, config)
        return

    await state.set_state(UploadStates.choosing_tag)
    await bot.send_message(
        user.id,
        "👤 Контакт автора\n\n"
        "Показувати ваш тег (@" + user.username + ") під конспектом? Тоді інші студенти "
        "зможуть написати вам кнопкою «Написати автору».\n\n"
        "Вибір добровільний. Змінити його можна будь-коли в «🗂 Мої конспекти».",
        reply_markup=tag_choice_kb(user.username),
    )


# ---------- Крок 1. Користувач натискає «Завантажити конспект» ----------

@router.message(F.text == BTN_UPLOAD)
async def begin_upload(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user is None:
        return

    group = await get_user_group(message.from_user.id)
    if group is None:
        await message.answer("Спочатку потрібно вибрати курс і навчальну групу.")
        await ask_group(message)
        return

    subjects = await get_subjects_with_counts(group["id"])
    if not subjects:
        await message.answer(
            "У вашій групі поки немає предметів.\n"
            "Зверніться до адміністратора, щоб він їх додав."
        )
        return

    await message.answer(
        "Оберіть предмет, до якого хочете додати конспект:",
        reply_markup=subjects_kb(subjects, "ups", with_cancel=True),
    )


# ---------- Крок 2. Вибір предмета ----------

@router.callback_query(F.data.startswith("ups:"))
async def choose_subject(callback: CallbackQuery, state: FSMContext):
    subject_id = last_int(callback.data)
    group, subject = await get_group_and_subject(callback.from_user.id, subject_id)
    if subject is None:
        await callback.answer(
            "Цей предмет недоступний. Почніть завантаження спочатку.",
            show_alert=True,
        )
        return

    await state.clear()
    await state.update_data(subject_id=subject["id"], topic_page=0)

    topics = await get_topics_with_counts(subject["id"])
    if not topics:
        # У предметі ще немає тем: одразу просимо назву першої
        await state.set_state(UploadStates.waiting_topic_title)
        await safe_edit(
            callback,
            f"📤 {crumb_for(group, subject)}\n\n"
            "У цьому предметі ще немає тем.\n\n" + NEW_TOPIC_PROMPT,
            cancel_kb(),
        )
    else:
        await state.set_state(UploadStates.choosing_topic)
        text, markup, _ = await picker_view(group, subject, 0)
        await safe_edit(callback, text, markup)
    await callback.answer()


# ---------- Крок 3. Вибір теми (папки) ----------

@router.callback_query(UploadStates.choosing_topic, F.data.startswith("upp:"))
async def topics_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group, subject = await get_group_and_subject(callback.from_user.id, data.get("subject_id"))
    page = last_int(callback.data)
    if subject is None or page is None:
        await callback.answer("Сеанс завантаження застарів.", show_alert=True)
        return

    text, markup, page = await picker_view(group, subject, page)
    await state.update_data(topic_page=page)
    await safe_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(UploadStates.choosing_topic, F.data.startswith("upt:"))
async def pick_topic(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    group, subject = await get_group_and_subject(callback.from_user.id, data.get("subject_id"))
    topic_id = last_int(callback.data)
    topic = await get_topic(topic_id) if topic_id is not None else None
    if subject is None or topic is None or topic["subject_id"] != subject["id"]:
        await callback.answer(
            "Ця тема недоступна. Почніть завантаження спочатку.", show_alert=True
        )
        return

    await state.update_data(topic_title=topic["title"])
    await state.set_state(UploadStates.waiting_title)
    await safe_edit(callback, f"📤 {crumb_for(group, subject, topic['title'])} ✅")
    await callback.bot.send_message(
        callback.from_user.id, NOTE_NAME_PROMPT, reply_markup=skip_cancel_kb()
    )
    await callback.answer()


@router.callback_query(UploadStates.choosing_topic, F.data == "upnew")
async def new_topic_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UploadStates.waiting_topic_title)
    await safe_edit(callback, NEW_TOPIC_PROMPT, cancel_kb())
    await callback.answer()


@router.message(UploadStates.waiting_topic_title, F.text, ~F.text.startswith("/"))
async def got_topic_title(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    title = " ".join(message.text.split())
    if len(title) < 2 or len(title) > MAX_TOPIC:
        await message.answer(
            f"⚠️ Назва теми має бути від 2 до {MAX_TOPIC} символів. Спробуйте ще раз.",
            reply_markup=cancel_kb(),
        )
        return

    data = await state.get_data()
    group, subject = await get_group_and_subject(message.from_user.id, data.get("subject_id"))
    if subject is None:
        await state.clear()
        await message.answer(
            "⚠️ Цей предмет уже недоступний. Натисніть «📤 Завантажити конспект» ще раз."
        )
        return

    # Така тема вже є: конспект потрапить у неї, дубль папки не створюється
    existing = await find_topic(subject["id"], title)
    topic_title = existing["title"] if existing else title
    await state.update_data(topic_title=topic_title)
    await state.set_state(UploadStates.waiting_title)

    if existing:
        info = f"📁 Така тема вже є, конспект потрапить у неї:\n{crumb_for(group, subject, topic_title)}"
    else:
        info = f"📁 Нова тема:\n{crumb_for(group, subject, topic_title)}"
    await message.answer(f"{info}\n\n{NOTE_NAME_PROMPT}", reply_markup=skip_cancel_kb())


@router.message(UploadStates.waiting_topic_title, ~F.text.startswith("/"))
async def topic_title_wrong_type(message: Message):
    await message.answer(
        "Введіть назву теми текстом або натисніть «Скасувати».",
        reply_markup=cancel_kb(),
    )


# ---------- Крок 4. Назва конспекту (необов'язково) ----------

@router.message(UploadStates.waiting_title, F.text, ~F.text.startswith("/"))
async def got_title(message: Message, state: FSMContext, config: Config):
    title = " ".join(message.text.split())
    if len(title) < 2 or len(title) > MAX_TITLE:
        await message.answer(
            f"⚠️ Назва має бути від 2 до {MAX_TITLE} символів. Спробуйте ще раз "
            "або натисніть «Пропустити».",
            reply_markup=skip_cancel_kb(),
        )
        return

    await state.update_data(title=title)
    await ask_tag(message.bot, message.from_user, state, config)


@router.callback_query(UploadStates.waiting_title, F.data == "upskip")
async def skip_title(callback: CallbackQuery, state: FSMContext, config: Config):
    await state.update_data(title=None)
    await safe_edit(callback, "✏️ Назва конспекту: ім'я файлу ✅")
    await ask_tag(callback.bot, callback.from_user, state, config)
    await callback.answer()


@router.message(UploadStates.waiting_title, ~F.text.startswith("/"))
async def title_wrong_type(message: Message):
    await message.answer(
        "Введіть назву текстом, натисніть «Пропустити» або «Скасувати».",
        reply_markup=skip_cancel_kb(),
    )


@router.callback_query(UploadStates.choosing_tag, F.data.startswith("uptag:"))
async def choose_tag(callback: CallbackQuery, state: FSMContext, config: Config):
    show = last_int(callback.data) == 1
    # Показати тег можна лише якщо username справді є
    if show and not callback.from_user.username:
        await callback.answer(
            "У вас немає @username у Telegram. Створіть його в налаштуваннях і спробуйте ще раз.",
            show_alert=True,
        )
        return

    await state.update_data(show_tag=1 if show else 0)
    await safe_edit(
        callback,
        "👤 Тег автора: " + ("показується ✅" if show else "прихований ✅"),
    )
    await prompt_file(callback.bot, callback.from_user.id, state, config)
    await callback.answer()


@router.message(UploadStates.choosing_tag, ~F.text.startswith("/"))
async def tag_wrong_type(message: Message):
    await message.answer("Оберіть варіант кнопкою нижче або натисніть «Скасувати».")


# ---------- Крок 5. Файл ----------

@router.message(UploadStates.waiting_file, F.document | F.photo)
async def got_file(message: Message, state: FSMContext, config: Config):
    if message.from_user is None:
        return

    if message.document:
        document = message.document
        file_name = document.file_name or "file"
        file_type = get_extension(file_name)
        error = check_file(file_type, document.file_size, config.max_file_mb)
        file_id = document.file_id
        file_unique_id = document.file_unique_id
    else:
        # Telegram надсилає фото в кількох розмірах, беремо найбільший
        photo = message.photo[-1]
        file_name = "photo.jpg"
        file_type = "photo"
        error = check_file("jpg", photo.file_size, config.max_file_mb)
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id

    if error:
        await message.answer(error, reply_markup=cancel_kb())
        return

    data = await state.get_data()
    subject_id = data.get("subject_id")
    topic_title = data.get("topic_title")
    if not subject_id or not topic_title:
        await state.clear()
        await message.answer(
            "⚠️ Сеанс завантаження застарів. Натисніть «📤 Завантажити конспект» ще раз."
        )
        return

    # Ще раз перевіряємо доступ: група користувача могла змінитися
    group, subject = await get_group_and_subject(message.from_user.id, subject_id)
    if subject is None:
        await state.clear()
        await message.answer(
            "⚠️ Цей предмет уже недоступний. Натисніть «📤 Завантажити конспект» ще раз."
        )
        return

    # Назва конспекту: введена користувачем або ім'я файлу
    title = data.get("title")
    if not title:
        if file_type == "photo":
            title = "Фото " + datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")
        else:
            title = os.path.splitext(file_name)[0].strip() or "Конспект"
        title = title[:MAX_TITLE]

    # Тег показуємо лише якщо автор його вибрав і username у нього досі є
    show_tag = bool(data.get("show_tag")) and bool(message.from_user.username)

    # Захист від спаму файлами: ліміт конспектів на годину (адміністраторів не стосується)
    if message.from_user.id not in config.admin_ids:
        recent = await count_recent_uploads(message.from_user.id, 1)
        if recent >= config.upload_limit_per_hour:
            await state.clear()
            await message.answer(
                f"⚠️ Ліміт: не більше {config.upload_limit_per_hour} конспектів на годину. "
                "Спробуйте пізніше."
            )
            return

    note_id = await add_note(
        group_id=group["id"],
        subject_id=subject["id"],
        topic_title=topic_title,
        title=title,
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_name=file_name,
        file_type=file_type,
        uploaded_by=message.from_user.id,
        show_author_tag=show_tag,
    )
    await state.clear()

    if note_id is None:
        await message.answer("⚠️ Цей файл уже додано до цього предмета.")
        return

    tag_line = "👁 Тег автора показується" if show_tag else "🔒 Тег автора прихований"
    await message.answer(
        f"✅ Конспект «{title}» збережено.\n"
        f"📁 {crumb_for(group, subject, topic_title)}\n"
        f"{tag_line}"
    )


@router.message(UploadStates.waiting_file, ~F.text.startswith("/"))
async def file_wrong_type(message: Message):
    await message.answer(
        "Надішліть файл (документ або фото) або натисніть «Скасувати».\n"
        f"Підтримуються: {FORMATS_TEXT}.",
        reply_markup=cancel_kb(),
    )


# ---------- Скасування ----------

@router.callback_query(F.data == "up_cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback, "❌ Завантаження скасовано.")
    await callback.answer()


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    if await state.get_state() is None:
        await message.answer("Немає активної дії для скасування.")
        return
    await state.clear()
    await message.answer("❌ Дію скасовано.")


# ---------- Застарілі кнопки (процес завантаження вже скінчився або скинутий) ----------

@router.callback_query(F.data.startswith("uptag:"))
@router.callback_query(F.data.startswith("upt:"))
@router.callback_query(F.data.startswith("upp:"))
@router.callback_query(F.data == "upnew")
@router.callback_query(F.data == "upskip")
async def stale_upload_button(callback: CallbackQuery):
    await callback.answer(
        "Сеанс завантаження застарів. Натисніть «📤 Завантажити конспект» ще раз.",
        show_alert=True,
    )


# ---------- Файл надіслано без початку завантаження ----------

@router.message(F.document | F.photo)
async def file_without_upload(message: Message):
    await message.answer(
        "Щоб додати конспект, натисніть «📤 Завантажити конспект» у меню."
    )
