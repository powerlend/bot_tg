from database.db import get_db

# Статуси пропозиції та їхні підписи для адміністратора
STATUSES = ("new", "in_progress", "done", "rejected")
STATUS_LABELS = {
    "new": "🆕 Нова",
    "in_progress": "⏳ Розглядається",
    "done": "✅ Виконана",
    "rejected": "❌ Відхилена",
}


async def add_suggestion(user_id: int, text: str) -> int:
    """Зберігає пропозицію зі статусом «нова». Повертає її номер."""
    db = get_db()
    cursor = await db.execute(
        "INSERT INTO suggestions (user_id, text) VALUES (?, ?)", (user_id, text)
    )
    await db.commit()
    return cursor.lastrowid


async def count_recent_suggestions(user_id: int, hours: int = 24) -> int:
    """Скільки пропозицій користувач надіслав за останні `hours` годин."""
    db = get_db()
    async with db.execute(
        """
        SELECT COUNT(*) FROM suggestions
        WHERE user_id = ? AND created_at >= datetime('now', ?)
        """,
        (user_id, f"-{int(hours)} hours"),
    ) as cursor:
        row = await cursor.fetchone()
    return row[0]


async def count_by_status() -> dict:
    """Кількість пропозицій за статусами та загалом: {'new': 2, ..., 'all': 5}."""
    db = get_db()
    async with db.execute(
        "SELECT status, COUNT(*) AS n FROM suggestions GROUP BY status"
    ) as cursor:
        rows = await cursor.fetchall()
    counts = {status: 0 for status in STATUSES}
    for row in rows:
        counts[row["status"]] = row["n"]
    counts["all"] = sum(counts[status] for status in STATUSES)
    return counts


async def get_suggestions_page(status: str, page: int, page_size: int):
    """Сторінка пропозицій (спочатку найновіші). status='all' - без фільтра."""
    where, params = "", []
    if status in STATUSES:
        where, params = "WHERE s.status = ?", [status]
    db = get_db()
    async with db.execute(
        f"""
        SELECT s.id, s.text, s.status, s.created_at, s.user_id,
               u.first_name, u.username
        FROM suggestions s
        LEFT JOIN users u ON u.telegram_id = s.user_id
        {where}
        ORDER BY s.created_at DESC, s.id DESC
        LIMIT ? OFFSET ?
        """,
        params + [page_size, page * page_size],
    ) as cursor:
        return await cursor.fetchall()


async def get_suggestion(suggestion_id: int):
    db = get_db()
    async with db.execute(
        """
        SELECT s.id, s.text, s.status, s.created_at, s.updated_at, s.user_id,
               u.first_name, u.username
        FROM suggestions s
        LEFT JOIN users u ON u.telegram_id = s.user_id
        WHERE s.id = ?
        """,
        (suggestion_id,),
    ) as cursor:
        return await cursor.fetchone()


async def set_suggestion_status(suggestion_id: int, status: str) -> bool:
    """Змінює статус. False - якщо статус неприпустимий або пропозиції немає."""
    if status not in STATUSES:
        return False
    db = get_db()
    cursor = await db.execute(
        "UPDATE suggestions SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, suggestion_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def delete_suggestion(suggestion_id: int) -> bool:
    """Видаляє одну пропозицію. False - якщо її вже немає."""
    db = get_db()
    cursor = await db.execute("DELETE FROM suggestions WHERE id = ?", (suggestion_id,))
    await db.commit()
    return cursor.rowcount > 0


# Масово можна видаляти лише завершені пропозиції, щоб випадково не стерти активні
BULK_DELETE_STATUSES = ("done", "rejected")


async def delete_suggestions_by_status(status: str) -> int:
    """Видаляє всі пропозиції зі статусом «виконана» або «відхилена».
    Повертає, скільки видалено. Для інших статусів нічого не робить (повертає 0)."""
    if status not in BULK_DELETE_STATUSES:
        return 0
    db = get_db()
    cursor = await db.execute("DELETE FROM suggestions WHERE status = ?", (status,))
    await db.commit()
    return cursor.rowcount
