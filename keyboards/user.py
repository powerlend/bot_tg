from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from utils.text import short_text

# Тексти кнопок головного меню (використовуються і тут, і в обробниках)
BTN_UPLOAD = "📤 Завантажити конспект"
BTN_FIND = "🔎 Знайти конспект"
BTN_CHANGE_GROUP = "👥 Змінити групу"
BTN_SUBJECTS = "📚 Предмети"
BTN_HELP = "ℹ️ Допомога"
BTN_MY_NOTES = "🗂 Мої конспекти"
BTN_SUGGEST = "💡 Пропозиції"


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def _menu_button() -> InlineKeyboardButton:
    return _btn("🏠 Головне меню", "fmenu")


def _back_button() -> InlineKeyboardButton:
    return _btn("⬅️ Назад", "fback")


def _nav_row(page: int, pages: int, callback_for_page) -> list:
    """Рядок ◀️ 2/5 ▶️. callback_for_page(n) повертає callback для сторінки n."""
    nav = []
    if page > 0:
        nav.append(_btn("◀️", callback_for_page(page - 1)))
    nav.append(_btn(f"{page + 1}/{pages}", "noop"))
    if page < pages - 1:
        nav.append(_btn("▶️", callback_for_page(page + 1)))
    return nav


# ---------- Головне меню ----------

def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_UPLOAD), KeyboardButton(text=BTN_FIND)],
            [KeyboardButton(text=BTN_SUBJECTS), KeyboardButton(text=BTN_MY_NOTES)],
            [KeyboardButton(text=BTN_SUGGEST), KeyboardButton(text=BTN_CHANGE_GROUP)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


# ---------- Вибір курсу та групи ----------

def courses_kb() -> InlineKeyboardMarkup:
    """Вибір курсу: 1 курс, 2 курс, 3 курс, 4 курс."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("1 курс", "crs:1"), _btn("2 курс", "crs:2")],
            [_btn("3 курс", "crs:3"), _btn("4 курс", "crs:4")],
        ]
    )


def groups_kb(groups) -> InlineKeyboardMarkup:
    """Групи вибраного курсу (по дві в рядок) і кнопка «Назад» до вибору курсу.
    У callback_data передаємо лише номер групи."""
    rows, pair = [], []
    for group in groups:
        pair.append(_btn(group["name"], f"grp:{group['id']}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([_btn("⬅️ Назад до курсів", "crsback")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Завантаження конспекту ----------

def subjects_kb(subjects, prefix: str, with_cancel: bool = False) -> InlineKeyboardMarkup:
    """Кнопки з предметами. callback_data має вигляд '<prefix>:<номер предмета>'."""
    rows = [[_btn(s["name"], f"{prefix}:{s['id']}")] for s in subjects]
    if with_cancel:
        rows.append([_btn("❌ Скасувати", "up_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("❌ Скасувати", "up_cancel")]])


def skip_cancel_kb() -> InlineKeyboardMarkup:
    """Для необов'язкового кроку: «Пропустити» і «Скасувати»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("⏭ Пропустити", "upskip")],
            [_btn("❌ Скасувати", "up_cancel")],
        ]
    )


def upload_topics_kb(topics, page: int, pages: int) -> InlineKeyboardMarkup:
    """Вибір теми (папки) при завантаженні: наявні теми, сторінки, «Нова тема»."""
    rows = [
        [_btn(short_text(f"📁 {t['title']} — {t['notes_count']}", 55), f"upt:{t['id']}")]
        for t in topics
    ]
    if pages > 1:
        rows.append(_nav_row(page, pages, lambda p: f"upp:{p}"))
    rows.append([_btn("➕ Нова тема", "upnew")])
    rows.append([_btn("❌ Скасувати", "up_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Пошук і перегляд: предмети → теми → конспекти ----------

def find_subjects_kb(subjects) -> InlineKeyboardMarkup:
    """Предмети з кількістю конспектів + пошук + головне меню."""
    rows = [
        [_btn(f"{s['name']} — {s['notes_count']}", f"ft:{s['id']}:0")]
        for s in subjects
    ]
    rows.append([_btn("🔍 Пошук за назвою", "fsearch")])
    rows.append([_menu_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topics_kb(topics, subject_id: int, page: int, pages: int) -> InlineKeyboardMarkup:
    """Папки з темами предмета: кожна тема з кількістю конспектів."""
    rows = [
        [_btn(short_text(f"📁 {t['title']} — {t['notes_count']}", 55), f"fl:{t['id']}:0:0")]
        for t in topics
    ]
    if pages > 1:
        rows.append(_nav_row(page, pages, lambda p: f"ft:{subject_id}:{p}"))
    rows.append([_back_button(), _menu_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topic_notes_kb(
    notes, topic_id: int, subject_id: int, page: int, pages: int, sort: int, total: int
) -> InlineKeyboardMarkup:
    """Конспекти однієї теми: список, сторінки, сортування, навігація."""
    rows = [[_btn("📄 " + short_text(n["title"]), f"fo:{n['id']}")] for n in notes]
    if pages > 1:
        rows.append(_nav_row(page, pages, lambda p: f"fl:{topic_id}:{p}:{sort}"))
    if total > 1:
        if sort == 0:
            label, new_sort = "↕️ Показати спочатку старі", 1
        else:
            label, new_sort = "↕️ Показати спочатку нові", 0
        rows.append([_btn(label, f"fl:{topic_id}:0:{new_sort}")])
    rows.append([_btn("⬅️ Назад до тем", f"ft:{subject_id}:0"), _menu_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_results_kb(matches) -> InlineKeyboardMarkup:
    """Результати пошуку: кнопка на кожен конспект + навігація."""
    rows = [
        [
            _btn(
                short_text(
                    f"📄 {m['title']} ({m['topic_title'] or '—'} · {m['subject_name']})", 55
                ),
                f"fo:{m['id']}",
            )
        ]
        for m in matches
    ]
    rows.append([_back_button(), _menu_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_back_button()]])


def back_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_back_button(), _menu_button()]])


# ---------- Тег автора ----------

def tag_choice_kb(username: str) -> InlineKeyboardMarkup:
    """Вибір під час завантаження: показувати свій @username чи приховати."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(f"👁 Показувати мій тег (@{username})", "uptag:1")],
            [_btn("🔒 Приховати мій тег", "uptag:0")],
            [_btn("❌ Скасувати", "up_cancel")],
        ]
    )


def contact_kb(username: str) -> InlineKeyboardMarkup:
    """Кнопка під файлом: відкриває чат з автором у Telegram."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Написати автору", url=f"https://t.me/{username}")]
        ]
    )


# ---------- Мої конспекти ----------

def my_notes_kb(notes, page: int, pages: int) -> InlineKeyboardMarkup:
    rows = [
        [
            _btn(
                short_text(f"📄 {n['title']} · {n['topic_title'] or '—'}", 55),
                f"mo:{n['id']}",
            )
        ]
        for n in notes
    ]
    if pages > 1:
        rows.append(_nav_row(page, pages, lambda p: f"mn:{p}"))
    rows.append([_menu_button()])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def my_note_card_kb(note_id: int, show_tag: bool) -> InlineKeyboardMarkup:
    if show_tag:
        toggle = _btn("🔒 Приховати мій тег", f"mt:{note_id}:0")
    else:
        toggle = _btn("👁 Показувати мій тег", f"mt:{note_id}:1")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [toggle],
            [_btn("📥 Отримати файл", f"mg:{note_id}")],
            [_btn("🗑 Видалити", f"md:{note_id}")],
            [_btn("⬅️ Назад", "mn:0")],
        ]
    )


def my_note_delete_kb(note_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("✅ Так, видалити", f"mdok:{note_id}")],
            [_btn("❌ Скасувати", f"mo:{note_id}")],
        ]
    )


# ---------- Пропозиції ----------

def suggest_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("❌ Скасувати", "sg_cancel")]])


# ---------- Дії під файлом конспекту та скарги ----------

def note_actions_kb(note_id: int, contact_username=None, can_complain: bool = True):
    """Кнопки під файлом: «Написати автору» (якщо автор дозволив тег) і «Поскаржитись».
    Повертає None, якщо кнопок немає."""
    rows = []
    if contact_username:
        rows.append(
            [InlineKeyboardButton(text="✉️ Написати автору", url=f"https://t.me/{contact_username}")]
        )
    if can_complain:
        rows.append([_btn("🚩 Поскаржитись", f"cx:{note_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def complaint_reasons_kb(note_id: int, reasons) -> InlineKeyboardMarkup:
    """Вибір причини скарги. reasons - словник {код: підпис}."""
    rows = [[_btn(label, f"cxr:{note_id}:{code}")] for code, label in reasons.items()]
    rows.append([_btn("❌ Скасувати", "cx_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def complaint_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("❌ Скасувати", "cx_cancel")]])
