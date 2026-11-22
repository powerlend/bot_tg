import sqlite3

from database.db import get_db

# Причини скарги та їхні підписи
REASONS = {
    "off_topic": "🚫 Не відповідає темі",
    "low_quality": "📄 Неякісний або нечитабельний файл",
    "copyright": "©️ Порушення авторських прав",
    "inappropriate": "⚠️ Неприйнятний вміст",
    "other": "✏️ Інша причина",
}

# Статуси скарги для адміністратора
STATUSES = ("new", "resolved", "rejected")
STATUS_LABELS = {
    "new": "🆕 Нова",
    "resolved": "✅ Розглянуто",
    "rejected": "🚫 Відхилено (необґрунтована)",
}


async def add_complaint(note_id: int, user_id: int, reason: str, comment=None):
    """Зберігає скаргу. Повертає її номер або None, якщо цей користувач
    уже скаржився на цей конспект."""
    if reason not in REASONS:
        raise ValueError(f"Невідома причина скарги: {reason}")
    db = get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO complaints (note_id, user_id, reason, comment) VALUES (?, ?, ?, ?)",
            (note_id, user_id, reason, comment),
        )
        await db.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as error:
        await db.rollback()
        if "UNIQUE" in str(error):
            return None
        raise


async def has_complained(note_id: int, user_id: int) -> bool:
    db = get_db()
    async with db.execute(
        "SELECT 1 FROM complaints WHERE note_id = ? AND user_id = ?", (note_id, user_id)
    ) as cursor:
        return await cursor.fetchone() is not None


async def count_recent_complaints(user_id: int, hours: int = 24) -> int:
    """Скільки скарг користувач надіслав за останні `hours` годин."""
    db = get_db()
    async with db.execute(
        """
        SELECT COUNT(*) FROM complaints
        WHERE user_id = ? AND created_at >= datetime('now', ?)
        """,
        (user_id, f"-{int(hours)} hours"),
    ) as cursor:
        row = await cursor.fetchone()
    return row[0]


async def count_by_status() -> dict:
    """Кількість скарг за статусами та загалом: {'new': 2, ..., 'all': 5}."""
    db = get_db()
    async with db.execute(
        "SELECT status, COUNT(*) AS n FROM complaints GROUP BY status"
    ) as cursor:
        rows = await cursor.fetchall()
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["status"]] = row["n"]
    counts["all"] = sum(counts[status] for status in STATUSES)
    return counts


async def get_complaints_page(status: str, page: int, page_size: int):
    """Сторінка скарг (спочатку найновіші). status='all' - без фільтра."""
    where, params = "", []
    if status in STATUSES:
        where, params = "WHERE c.status = ?", [status]
    db = get_db()
    async with db.execute(
        f"""
        SELECT c.id, c.reason, c.status, c.created_at, n.title AS note_title
        FROM complaints c
        JOIN notes n ON n.id = c.note_id
        {where}
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT ? OFFSET ?
        """,
        params + [page_size, page * page_size],
    ) as cursor:
        return await cursor.fetchall()


async def get_complaint(complaint_id: int):
    """Скарга з усіма даними: конспект, його шлях і автор, той, хто поскаржився."""
    db = get_db()
    async with db.execute(
        """
        SELECT c.id, c.note_id, c.reason, c.comment, c.status, c.created_at, c.user_id,
               ru.first_name AS reporter_name, ru.username AS reporter_username,
               n.title AS note_title, n.uploaded_by,
               g.name AS group_name, s.name AS subject_name, t.title AS topic_title,
               au.first_name AS author_name, au.username AS author_username,
               (SELECT COUNT(*) FROM complaints c2 WHERE c2.note_id = c.note_id)
                   AS total_for_note
        FROM complaints c
        JOIN notes n ON n.id = c.note_id
        JOIN groups g ON g.id = n.group_id
        JOIN subjects s ON s.id = n.subject_id
        LEFT JOIN topics t ON t.id = n.topic_id
        LEFT JOIN users ru ON ru.telegram_id = c.user_id
        LEFT JOIN users au ON au.telegram_id = n.uploaded_by
        WHERE c.id = ?
        """,
        (complaint_id,),
    ) as cursor:
        return await cursor.fetchone()


async def set_complaint_status(complaint_id: int, status: str) -> bool:
    """Змінює статус скарги. False - якщо статус неприпустимий або скарги немає."""
    if status not in STATUSES:
        return False
    db = get_db()
    cursor = await db.execute(
        "UPDATE complaints SET status = ? WHERE id = ?", (status, complaint_id)
    )
    await db.commit()
    return cursor.rowcount > 0
