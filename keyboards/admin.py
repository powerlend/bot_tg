from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.text import short_text


def _btn(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def admin_menu_kb(new_suggestions: int = 0, new_complaints: int = 0) -> InlineKeyboardMarkup:
    suggestions_label = "💡 Пропозиції" + (f" ({new_suggestions})" if new_suggestions else "")
    complaints_label = "🚩 Скарги" + (f" ({new_complaints})" if new_complaints else "")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("👥 Керування групами", "adm:g")],
            [_btn("📚 Керування предметами", "adm:s")],
            [_btn("📄 Керування конспектами", "adm:n")],
            [_btn("👤 Керування користувачами", "adm:u")],
            [_btn(complaints_label, "adm:c")],
            [_btn(suggestions_label, "adm:v")],
            [_btn("📊 Статистика", "adm:stats")],
            [_btn("⚙️ Налаштування", "adm:settings")],
            [_btn("⬅️ Назад", "adm:close")],
        ]
    )


def cancel_kb(back_callback: str) -> InlineKeyboardMarkup:
    """Кнопка «Скасувати» під запитом на введення тексту."""
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("❌ Скасувати", back_callback)]])


def confirm_kb(yes_callback: str, no_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("✅ Так, видалити", yes_callback)],
            [_btn("❌ Скасувати", no_callback)],
        ]
    )


def _page_nav(page: int, pages: int, callback_for_page) -> list:
    """Рядок кнопок ◀️ 2/5 ▶️. callback_for_page(n) повертає callback для сторінки n."""
    nav = []
    if page > 0:
        nav.append(_btn("◀️", callback_for_page(page - 1)))
    nav.append(_btn(f"{page + 1}/{pages}", "noop"))
    if page < pages - 1:
        nav.append(_btn("▶️", callback_for_page(page + 1)))
    return nav


# ---------- Групи ----------

def groups_list_kb(groups) -> InlineKeyboardMarkup:
    rows = [[_btn(f"{g['name']} · {g['course']} курс", f"adm:go:{g['id']}")] for g in groups]
    rows.append([_btn("➕ Додати групу", "adm:gadd")])
    rows.append([_btn("⬅️ Назад", "adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def group_card_kb(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("✏️ Перейменувати", f"adm:gren:{group_id}")],
            [_btn("🎓 Змінити курс", f"adm:gcrs:{group_id}")],
            [_btn("🗑 Видалити", f"adm:gdel:{group_id}")],
            [_btn("⬅️ Назад", "adm:g")],
        ]
    )


# ---------- Предмети ----------

def pick_group_kb(groups) -> InlineKeyboardMarkup:
    rows = [[_btn(g["name"], f"adm:sg:{g['id']}")] for g in groups]
    rows.append([_btn("⬅️ Назад", "adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subjects_list_kb(subjects, group_id: int) -> InlineKeyboardMarkup:
    rows = [
        [_btn(f"{s['name']} — {s['notes_count']}", f"adm:so:{s['id']}")]
        for s in subjects
    ]
    rows.append([_btn("➕ Додати предмет", f"adm:sadd:{group_id}")])
    rows.append([_btn("⬅️ Назад", "adm:s")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subject_card_kb(subject_id: int, group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📁 Теми", f"adm:tl:{subject_id}:0")],
            [_btn("✏️ Перейменувати", f"adm:sren:{subject_id}")],
            [_btn("🗑 Видалити", f"adm:sdel:{subject_id}")],
            [_btn("⬅️ Назад", f"adm:sg:{group_id}")],
        ]
    )


# ---------- Конспекти ----------

def notes_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📋 Усі конспекти", "adm:nl:0:0:0")],
            [_btn("👥 Фільтр за групою", "adm:ng")],
            [_btn("🔍 Пошук за назвою", "adm:nsearch")],
            [_btn("⬅️ Назад", "adm:home")],
        ]
    )


def notes_list_kb(notes, group_id: int, subject_id: int, page: int, pages: int):
    rows = [
        [
            _btn(
                short_text(f"📄 {n['title']} · {n['group_name']}/{n['subject_name']}", 55),
                f"adm:no:{n['id']}",
            )
        ]
        for n in notes
    ]
    if pages > 1:
        rows.append(
            _page_nav(page, pages, lambda p: f"adm:nl:{group_id}:{subject_id}:{p}")
        )
    rows.append([_btn("👥 Група", "adm:ng")])
    if group_id:
        rows[-1].append(_btn("📚 Предмет", f"adm:nsg:{group_id}"))
    if group_id or subject_id:
        rows.append([_btn("🔄 Скинути фільтри", "adm:nl:0:0:0")])
    rows.append([_btn("⬅️ Назад", "adm:n")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def filter_group_kb(groups) -> InlineKeyboardMarkup:
    rows = [[_btn("Усі групи", "adm:nl:0:0:0")]]
    rows += [[_btn(g["name"], f"adm:nl:{g['id']}:0:0")] for g in groups]
    rows.append([_btn("⬅️ Назад", "adm:n")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def filter_subject_kb(subjects, group_id: int) -> InlineKeyboardMarkup:
    rows = [[_btn("Усі предмети групи", f"adm:nl:{group_id}:0:0")]]
    rows += [[_btn(s["name"], f"adm:nl:{group_id}:{s['id']}:0")] for s in subjects]
    rows.append([_btn("⬅️ Назад", f"adm:nl:{group_id}:0:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def note_card_kb(note_id: int, group_id: int, subject_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📥 Отримати файл", f"adm:nget:{note_id}")],
            [_btn("🗑 Видалити", f"adm:ndel:{note_id}")],
            [_btn("⬅️ Назад", f"adm:nl:{group_id}:{subject_id}:0")],
        ]
    )


def notes_search_results_kb(matches) -> InlineKeyboardMarkup:
    rows = [
        [
            _btn(
                short_text(f"📄 {m['title']} · {m['group_name']}/{m['subject_name']}", 55),
                f"adm:no:{m['id']}",
            )
        ]
        for m in matches
    ]
    rows.append([_btn("⬅️ Назад", "adm:n")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Користувачі ----------

def _user_label(user) -> str:
    name = user["first_name"] or "Без імені"
    if user["username"]:
        name += f" @{user['username']}"
    if user["is_blocked"]:
        name = "⛔ " + name
    return short_text("👤 " + name, 55)


def users_list_kb(users, page: int, pages: int) -> InlineKeyboardMarkup:
    rows = [[_btn(_user_label(u), f"adm:uo:{u['telegram_id']}")] for u in users]
    if pages > 1:
        rows.append(_page_nav(page, pages, lambda p: f"adm:ul:{p}"))
    rows.append([_btn("🔍 Знайти користувача", "adm:usearch")])
    rows.append([_btn("⬅️ Назад", "adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_card_kb(telegram_id: int, is_blocked: bool, is_admin: bool) -> InlineKeyboardMarkup:
    rows = []
    if not is_admin:
        if is_blocked:
            rows.append([_btn("✅ Розблокувати", f"adm:uunblock:{telegram_id}")])
        else:
            rows.append([_btn("⛔ Заблокувати", f"adm:ublock:{telegram_id}")])
    rows.append([_btn("⬅️ Назад", "adm:ul:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_search_results_kb(users) -> InlineKeyboardMarkup:
    rows = [[_btn(_user_label(u), f"adm:uo:{u['telegram_id']}")] for u in users]
    rows.append([_btn("⬅️ Назад", "adm:u")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Статистика ----------

def stats_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("🔄 Оновити", "adm:stats")],
            [_btn("⬅️ Назад", "adm:home")],
        ]
    )


# ---------- Налаштування ----------

def settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("💾 Створити копію зараз", "adm:backup")],
            [_btn("⬅️ Назад", "adm:home")],
        ]
    )


# ---------- Вибір курсу (для нової групи та зміни курсу) ----------

def course_pick_kb(callback_prefix: str, back_callback: str) -> InlineKeyboardMarkup:
    """Чотири кнопки курсів. До callback_prefix додається номер курсу: 'adm:gnew:' -> 'adm:gnew:2'."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("1 курс", f"{callback_prefix}1"),
                _btn("2 курс", f"{callback_prefix}2"),
            ],
            [
                _btn("3 курс", f"{callback_prefix}3"),
                _btn("4 курс", f"{callback_prefix}4"),
            ],
            [_btn("⬅️ Назад", back_callback)],
        ]
    )


# ---------- Теми (папки) ----------

def topics_list_kb(topics, subject_id: int, page: int, pages: int) -> InlineKeyboardMarkup:
    rows = [
        [_btn(short_text(f"📁 {t['title']} — {t['notes_count']}", 55), f"adm:to:{t['id']}")]
        for t in topics
    ]
    if pages > 1:
        rows.append(_page_nav(page, pages, lambda p: f"adm:tl:{subject_id}:{p}"))
    rows.append([_btn("⬅️ Назад", f"adm:so:{subject_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topic_card_kb(topic_id: int, subject_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("✏️ Перейменувати", f"adm:tren:{topic_id}")],
            [_btn("🗑 Видалити", f"adm:tdel:{topic_id}")],
            [_btn("⬅️ Назад", f"adm:tl:{subject_id}:0")],
        ]
    )


# ---------- Пропозиції ----------

SUGGESTION_FILTERS = (
    ("new", "🆕 Нові"),
    ("in_progress", "⏳ Розглядаються"),
    ("done", "✅ Виконані"),
    ("rejected", "❌ Відхилені"),
    ("all", "📋 Усі"),
)
STATUS_EMOJI = {"new": "🆕", "in_progress": "⏳", "done": "✅", "rejected": "❌"}


def suggestion_open_kb(suggestion_id: int) -> InlineKeyboardMarkup:
    """Кнопка під сповіщенням про нову пропозицію."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("📋 Відкрити", f"adm:vo:{suggestion_id}")]]
    )


def suggestions_list_kb(items, status: str, page: int, pages: int, counts) -> InlineKeyboardMarkup:
    """Фільтри за статусом (з кількістю), пропозиції списком, сторінки."""
    def filter_button(key, label):
        mark = "✔ " if key == status else ""
        return _btn(f"{mark}{label} ({counts[key]})", f"adm:vl:{key}:0")

    rows = [
        [filter_button("new", "🆕 Нові"), filter_button("in_progress", "⏳ Розглядаються")],
        [filter_button("done", "✅ Виконані"), filter_button("rejected", "❌ Відхилені")],
        [filter_button("all", "📋 Усі")],
    ]
    for item in items:
        name = item["first_name"] or "Без імені"
        label = f"{STATUS_EMOJI.get(item['status'], '')} №{item['id']} · {name} · {item['text']}"
        rows.append([_btn(short_text(label.replace("\n", " "), 55), f"adm:vo:{item['id']}")])
    if pages > 1:
        rows.append(_page_nav(page, pages, lambda p: f"adm:vl:{status}:{p}"))
    # Масове очищення завершених пропозицій
    if status in ("done", "rejected") and counts[status] > 0:
        word = "виконані" if status == "done" else "відхилені"
        rows.append([_btn(f"🧹 Видалити всі {word} ({counts[status]})", f"adm:vdall:{status}")])
    rows.append([_btn("⬅️ Назад", "adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def suggestion_card_kb(suggestion_id: int, status: str, contact_url) -> InlineKeyboardMarkup:
    """Кнопки зміни статусу (поточний позначено галочкою) і зв'язку з автором."""
    def status_button(key, label):
        mark = "✔ " if key == status else ""
        return _btn(f"{mark}{label}", f"adm:vs:{suggestion_id}:{key}")

    rows = [
        [status_button("new", "🆕 Нова"), status_button("in_progress", "⏳ Розглядається")],
        [status_button("done", "✅ Виконана"), status_button("rejected", "❌ Відхилена")],
    ]
    if contact_url:
        rows.append([InlineKeyboardButton(text="✉️ Написати автору", url=contact_url)])
    rows.append([_btn("🗑 Видалити пропозицію", f"adm:vd:{suggestion_id}")])
    rows.append([_btn("⬅️ До списку", f"adm:vl:{status}:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Скарги ----------

COMPLAINT_STATUS_EMOJI = {"new": "🆕", "resolved": "✅", "rejected": "🚫"}


def complaints_list_kb(items, status: str, page: int, pages: int, counts, reason_labels):
    """Фільтри за статусом (з кількістю), скарги списком, сторінки."""
    def filter_button(key, label):
        mark = "✔ " if key == status else ""
        return _btn(f"{mark}{label} ({counts[key]})", f"adm:cl:{key}:0")

    rows = [
        [filter_button("new", "🆕 Нові"), filter_button("resolved", "✅ Розглянуті")],
        [filter_button("rejected", "🚫 Відхилені"), filter_button("all", "📋 Усі")],
    ]
    for item in items:
        reason = reason_labels.get(item["reason"], item["reason"])
        label = f"{COMPLAINT_STATUS_EMOJI.get(item['status'], '')} №{item['id']} · {item['note_title']} · {reason}"
        rows.append([_btn(short_text(label, 55), f"adm:co:{item['id']}")])
    if pages > 1:
        rows.append(_page_nav(page, pages, lambda p: f"adm:cl:{status}:{p}"))
    rows.append([_btn("⬅️ Назад", "adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def complaint_open_kb(complaint_id: int) -> InlineKeyboardMarkup:
    """Кнопка під сповіщенням про нову скаргу."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("📋 Відкрити", f"adm:co:{complaint_id}")]]
    )


def complaint_card_kb(complaint_id: int, note_id: int, status: str) -> InlineKeyboardMarkup:
    """Дії зі скаргою: переглянути або видалити конспект, змінити статус скарги."""
    def status_button(key, label):
        mark = "✔ " if key == status else ""
        return _btn(f"{mark}{label}", f"adm:cs:{complaint_id}:{key}")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📄 Відкрити конспект", f"adm:no:{note_id}")],
            [_btn("🗑 Видалити конспект", f"adm:ndel:{note_id}")],
            [status_button("resolved", "✅ Розглянуто"), status_button("rejected", "🚫 Відхилити")],
            [status_button("new", "🆕 Повернути в нові")],
            [_btn("⬅️ До списку", f"adm:cl:{status}:0")],
        ]
    )
