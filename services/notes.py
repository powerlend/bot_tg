import sqlite3

from database.db import get_db
from services.groups import clean_name


async def add_note(
    *,
    group_id: int,
    subject_id: int,
    topic_title: str,
    title: str,
    file_id: str,
    file_unique_id: str,
    file_name: str,
    file_type: str,
    uploaded_by: int,
    show_author_tag: bool = False,
):
    """Зберігає конспект у папку-тему предмета (якщо теми ще немає, вона створюється).

    Тема й конспект зберігаються однією транзакцією: якщо конспект не збережеться
    (наприклад, дубль файлу), порожня папка теж не залишиться.
    Повертає id запису або None, якщо цей файл уже є в предметі.
    """
    db = get_db()
    topic_title = clean_name(topic_title)
    try:
        await db.execute(
            "INSERT OR IGNORE INTO topics (subject_id, title, title_key) VALUES (?, ?, ?)",
            (subject_id, topic_title, topic_title.casefold()),
        )
        async with db.execute(
            "SELECT id FROM topics WHERE subject_id = ? AND title_key = ?",
            (subject_id, topic_title.casefold()),
        ) as cursor:
            topic_id = (await cursor.fetchone())["id"]

        cursor = await db.execute(
            """
            INSERT INTO notes
                (group_id, subject_id, topic_id, title, file_id, file_unique_id,
                 file_name, file_type, uploaded_by, show_author_tag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group_id, subject_id, topic_id, title, file_id, file_unique_id,
                file_name, file_type, uploaded_by, 1 if show_author_tag else 0,
            ),
        )
        await db.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as error:
        await db.rollback()
        if "UNIQUE" in str(error):
            return None  # такий файл у цьому предметі вже збережено
        raise


async def count_notes(subject_id: int) -> int:
    """Кількість конспектів у предметі."""
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM notes WHERE subject_id = ?", (subject_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return row[0]


async def count_topic_notes(topic_id: int) -> int:
    """Кількість конспектів у темі (папці)."""
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM notes WHERE topic_id = ?", (topic_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return row[0]


async def get_topic_notes_page(
    topic_id: int, page: int, page_size: int, newest_first: bool = True
):
    """Одна сторінка конспектів теми (page починається з 0)."""
    order = "DESC" if newest_first else "ASC"  # значення вибираємо ми, не користувач
    db = get_db()
    async with db.execute(
        f"""
        SELECT id, title, created_at
        FROM notes
        WHERE topic_id = ?
        ORDER BY created_at {order}, id {order}
        LIMIT ? OFFSET ?
        """,
        (topic_id, page_size, page * page_size),
    ) as cursor:
        return await cursor.fetchall()


async def get_note(note_id: int):
    """Запис конспекту разом з назвами предмета, теми та поточним username автора."""
    db = get_db()
    async with db.execute(
        """
        SELECT n.*, s.name AS subject_name, t.title AS topic_title,
               u.username AS author_username
        FROM notes n
        JOIN subjects s ON s.id = n.subject_id
        LEFT JOIN topics t ON t.id = n.topic_id
        LEFT JOIN users u ON u.telegram_id = n.uploaded_by
        WHERE n.id = ?
        """,
        (note_id,),
    ) as cursor:
        return await cursor.fetchone()


async def search_notes(group_id: int, query: str, limit: int = 20):
    """Шукає конспекти групи за частиною назви конспекту або теми (регістр не важливий).

    Повертає пару: (знайдені конспекти до limit штук, скільки знайдено всього).
    Пошук робимо в Python, бо SQLite не розрізняє великі й малі кириличні літери.
    """
    db = get_db()
    async with db.execute(
        """
        SELECT n.id, n.title, s.name AS subject_name, t.title AS topic_title
        FROM notes n
        JOIN subjects s ON s.id = n.subject_id
        LEFT JOIN topics t ON t.id = n.topic_id
        WHERE n.group_id = ?
        ORDER BY n.created_at DESC, n.id DESC
        """,
        (group_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    needle = query.casefold()
    matches = [
        row for row in rows
        if needle in row["title"].casefold()
        or needle in (row["topic_title"] or "").casefold()
    ]
    return matches[:limit], len(matches)


async def increment_downloads(note_id: int, user_id=None) -> None:
    """Збільшує лічильник завантажень конспекту і записує завантаження в історію."""
    db = get_db()
    await db.execute(
        "UPDATE notes SET downloads_count = downloads_count + 1 WHERE id = ?",
        (note_id,),
    )
    # INSERT ... SELECT нічого не додасть, якщо конспект саме зараз видалили
    await db.execute(
        "INSERT INTO downloads (note_id, user_id) SELECT id, ? FROM notes WHERE id = ?",
        (user_id, note_id),
    )
    await db.commit()


async def count_recent_uploads(user_id: int, hours: int = 1) -> int:
    """Скільки конспектів користувач додав за останні `hours` годин."""
    db = get_db()
    async with db.execute(
        """
        SELECT COUNT(*) FROM notes
        WHERE uploaded_by = ? AND created_at >= datetime('now', ?)
        """,
        (user_id, f"-{int(hours)} hours"),
    ) as cursor:
        row = await cursor.fetchone()
    return row[0]


# ---------- Функції для адміністратора ----------

def _filters(group_id, subject_id):
    """Умови фільтрації для списків: 0 або None означає «без фільтра»."""
    conditions, params = [], []
    if group_id:
        conditions.append("n.group_id = ?")
        params.append(group_id)
    if subject_id:
        conditions.append("n.subject_id = ?")
        params.append(subject_id)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


async def count_admin_notes(group_id=0, subject_id=0) -> int:
    where, params = _filters(group_id, subject_id)
    db = get_db()
    async with db.execute(f"SELECT COUNT(*) FROM notes n {where}", params) as cursor:
        row = await cursor.fetchone()
    return row[0]


async def get_admin_notes_page(group_id, subject_id, page: int, page_size: int):
    """Сторінка конспектів з урахуванням фільтрів (спочатку найновіші)."""
    where, params = _filters(group_id, subject_id)
    db = get_db()
    async with db.execute(
        f"""
        SELECT n.id, n.title, g.name AS group_name, s.name AS subject_name
        FROM notes n
        JOIN subjects s ON s.id = n.subject_id
        JOIN groups g ON g.id = n.group_id
        {where}
        ORDER BY n.created_at DESC, n.id DESC
        LIMIT ? OFFSET ?
        """,
        params + [page_size, page * page_size],
    ) as cursor:
        return await cursor.fetchall()


async def get_note_full(note_id: int):
    """Усі дані конспекту: група, предмет, тема, автор."""
    db = get_db()
    async with db.execute(
        """
        SELECT n.*, g.name AS group_name, s.name AS subject_name,
               t.title AS topic_title,
               u.first_name AS author_name, u.username AS author_username,
               (SELECT COUNT(*) FROM complaints c WHERE c.note_id = n.id) AS complaints_count
        FROM notes n
        JOIN subjects s ON s.id = n.subject_id
        JOIN groups g ON g.id = n.group_id
        LEFT JOIN topics t ON t.id = n.topic_id
        LEFT JOIN users u ON u.telegram_id = n.uploaded_by
        WHERE n.id = ?
        """,
        (note_id,),
    ) as cursor:
        return await cursor.fetchone()


async def delete_note(note_id: int) -> bool:
    """Видаляє конспект. Якщо в темі більше немає конспектів, порожня тема теж зникає.
    False - якщо конспекту вже немає."""
    db = get_db()
    async with db.execute(
        "SELECT topic_id FROM notes WHERE id = ?", (note_id,)
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return False

    topic_id = row["topic_id"]
    await db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    if topic_id is not None:
        await db.execute(
            """
            DELETE FROM topics
            WHERE id = ? AND NOT EXISTS (SELECT 1 FROM notes WHERE topic_id = ?)
            """,
            (topic_id, topic_id),
        )
    await db.commit()
    return True


async def admin_search_notes(query: str, limit: int = 20):
    """Пошук за назвою конспекту або теми по всіх групах.
    Повертає (список до limit, всього знайдено)."""
    db = get_db()
    async with db.execute(
        """
        SELECT n.id, n.title, g.name AS group_name, s.name AS subject_name,
               t.title AS topic_title
        FROM notes n
        JOIN subjects s ON s.id = n.subject_id
        JOIN groups g ON g.id = n.group_id
        LEFT JOIN topics t ON t.id = n.topic_id
        ORDER BY n.created_at DESC, n.id DESC
        """
    ) as cursor:
        rows = await cursor.fetchall()

    needle = query.casefold()
    matches = [
        row for row in rows
        if needle in row["title"].casefold()
        or needle in (row["topic_title"] or "").casefold()
    ]
    return matches[:limit], len(matches)


# ---------- Власні конспекти користувача ----------

async def count_user_notes(user_id: int) -> int:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM notes WHERE uploaded_by = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return row[0]


async def get_user_notes_page(user_id: int, page: int, page_size: int):
    """Конспекти, додані цим користувачем (спочатку найновіші)."""
    db = get_db()
    async with db.execute(
        """
        SELECT n.id, n.title, t.title AS topic_title, s.name AS subject_name
        FROM notes n
        JOIN subjects s ON s.id = n.subject_id
        LEFT JOIN topics t ON t.id = n.topic_id
        WHERE n.uploaded_by = ?
        ORDER BY n.created_at DESC, n.id DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, page_size, page * page_size),
    ) as cursor:
        return await cursor.fetchall()


async def set_author_tag(note_id: int, user_id: int, show: bool) -> bool:
    """Змінює вибір «показувати тег». Працює лише для власного конспекту. False - не вийшло."""
    db = get_db()
    cursor = await db.execute(
        "UPDATE notes SET show_author_tag = ? WHERE id = ? AND uploaded_by = ?",
        (1 if show else 0, note_id, user_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_own_note(note_id: int, user_id: int) -> bool:
    """Видаляє конспект, якщо його додав саме цей користувач. Порожня тема теж зникає.
    False - конспекту немає або він чужий."""
    db = get_db()
    async with db.execute(
        "SELECT topic_id FROM notes WHERE id = ? AND uploaded_by = ?",
        (note_id, user_id),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return False

    topic_id = row["topic_id"]
    await db.execute(
        "DELETE FROM notes WHERE id = ? AND uploaded_by = ?", (note_id, user_id)
    )
    if topic_id is not None:
        await db.execute(
            """
            DELETE FROM topics
            WHERE id = ? AND NOT EXISTS (SELECT 1 FROM notes WHERE topic_id = ?)
            """,
            (topic_id, topic_id),
        )
    await db.commit()
    return True
