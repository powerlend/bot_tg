import sqlite3

from database.db import get_db
from services.groups import clean_name
from utils.text import natural_key

# Назва папки для старих конспектів (див. database/migrations.py)
DEFAULT_TOPIC = "Загальне"


def topic_key(title: str) -> str:
    """Ключ для порівняння тем: без зайвих пробілів і без різниці великих/малих літер."""
    return clean_name(title).casefold()


async def get_topics_with_counts(subject_id: int):
    """Усі теми предмета з кількістю конспектів, відсортовані «по-людськи» (Тема 2 перед Тема 10)."""
    db = get_db()
    async with db.execute(
        """
        SELECT t.id, t.title, COUNT(n.id) AS notes_count
        FROM topics t
        LEFT JOIN notes n ON n.topic_id = t.id
        WHERE t.subject_id = ?
        GROUP BY t.id
        """,
        (subject_id,),
    ) as cursor:
        rows = list(await cursor.fetchall())
    rows.sort(key=lambda row: natural_key(row["title"]))
    return rows


async def count_topics(subject_id: int) -> int:
    db = get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM topics WHERE subject_id = ?", (subject_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return row[0]


async def get_topic(topic_id: int):
    db = get_db()
    async with db.execute(
        "SELECT id, subject_id, title FROM topics WHERE id = ?", (topic_id,)
    ) as cursor:
        return await cursor.fetchone()


async def find_topic(subject_id: int, title: str):
    """Шукає тему в предметі за назвою (регістр і зайві пробіли не важливі)."""
    db = get_db()
    async with db.execute(
        "SELECT id, subject_id, title FROM topics WHERE subject_id = ? AND title_key = ?",
        (subject_id, topic_key(title)),
    ) as cursor:
        return await cursor.fetchone()


async def rename_topic(topic_id: int, new_title: str) -> str:
    """Перейменовує тему. Повертає 'ok', 'exists' (така тема вже є) або 'missing'."""
    db = get_db()
    new_title = clean_name(new_title)
    try:
        cursor = await db.execute(
            "UPDATE topics SET title = ?, title_key = ? WHERE id = ?",
            (new_title, new_title.casefold(), topic_id),
        )
        await db.commit()
    except sqlite3.IntegrityError:
        await db.rollback()
        return "exists"
    return "ok" if cursor.rowcount > 0 else "missing"


async def delete_topic(topic_id: int) -> bool:
    """Видаляє тему разом з її конспектами. False - якщо теми вже немає."""
    db = get_db()
    cursor = await db.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
    await db.commit()
    return cursor.rowcount > 0
