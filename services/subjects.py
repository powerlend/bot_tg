import sqlite3

from database.db import get_db
from services.groups import clean_name


async def get_subjects_with_counts(group_id: int):
    """Предмети групи разом з кількістю конспектів у кожному."""
    db = get_db()
    async with db.execute(
        """
        SELECT s.id, s.name, COUNT(n.id) AS notes_count
        FROM subjects s
        LEFT JOIN notes n ON n.subject_id = s.id
        WHERE s.group_id = ?
        GROUP BY s.id
        ORDER BY s.name
        """,
        (group_id,),
    ) as cursor:
        return await cursor.fetchall()


async def add_subject(group_id: int, name: str) -> bool:
    """Додає предмет у групу. Повертає False, якщо такий предмет там уже є."""
    db = get_db()
    name = clean_name(name)
    try:
        await db.execute(
            "INSERT INTO subjects (group_id, name, name_key) VALUES (?, ?, ?)",
            (group_id, name, name.casefold()),
        )
        await db.commit()
        return True
    except sqlite3.IntegrityError:
        await db.rollback()
        return False


async def get_subject(subject_id: int):
    """Повертає предмет (id, group_id, name) або None."""
    db = get_db()
    async with db.execute(
        "SELECT id, group_id, name FROM subjects WHERE id = ?", (subject_id,)
    ) as cursor:
        return await cursor.fetchone()


async def rename_subject(subject_id: int, new_name: str) -> str:
    """Перейменовує предмет. Повертає 'ok', 'exists' (у групі вже є такий) або 'missing'."""
    db = get_db()
    new_name = clean_name(new_name)
    try:
        cursor = await db.execute(
            "UPDATE subjects SET name = ?, name_key = ? WHERE id = ?",
            (new_name, new_name.casefold(), subject_id),
        )
        await db.commit()
    except sqlite3.IntegrityError:
        await db.rollback()
        return "exists"
    return "ok" if cursor.rowcount > 0 else "missing"


async def delete_subject(subject_id: int) -> bool:
    """Видаляє предмет разом з його конспектами. False - якщо предмета вже немає."""
    db = get_db()
    cursor = await db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    await db.commit()
    return cursor.rowcount > 0
