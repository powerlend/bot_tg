import sqlite3

from database.db import get_db

COURSES = (1, 2, 3, 4)


def clean_name(name: str) -> str:
    """Прибирає зайві пробіли: '  КН-21   ' -> 'КН-21'."""
    return " ".join(name.split())


async def get_all_groups():
    """Усі групи: спочатку за курсом, потім за назвою."""
    db = get_db()
    async with db.execute(
        "SELECT id, name, course FROM groups ORDER BY course, name"
    ) as cursor:
        return await cursor.fetchall()


async def get_groups_by_course(course: int):
    """Групи одного курсу."""
    db = get_db()
    async with db.execute(
        "SELECT id, name, course FROM groups WHERE course = ? ORDER BY name",
        (course,),
    ) as cursor:
        return await cursor.fetchall()


async def get_group(group_id: int):
    db = get_db()
    async with db.execute(
        "SELECT id, name, course FROM groups WHERE id = ?", (group_id,)
    ) as cursor:
        return await cursor.fetchone()


async def get_group_by_name(name: str):
    """Шукає групу за назвою (регістр не важливий)."""
    db = get_db()
    key = clean_name(name).casefold()
    async with db.execute(
        "SELECT id, name, course FROM groups WHERE name_key = ?", (key,)
    ) as cursor:
        return await cursor.fetchone()


async def add_group(name: str, course: int) -> bool:
    """Додає групу на вказаний курс. Повертає False, якщо така назва вже є."""
    if course not in COURSES:
        raise ValueError(f"Курс має бути від 1 до 4, а не {course}")
    db = get_db()
    name = clean_name(name)
    try:
        await db.execute(
            "INSERT INTO groups (name, name_key, course) VALUES (?, ?, ?)",
            (name, name.casefold(), course),
        )
        await db.commit()
        return True
    except sqlite3.IntegrityError:
        await db.rollback()
        return False


async def set_group_course(group_id: int, course: int) -> bool:
    """Змінює курс групи. False - якщо групи вже немає."""
    if course not in COURSES:
        raise ValueError(f"Курс має бути від 1 до 4, а не {course}")
    db = get_db()
    cursor = await db.execute(
        "UPDATE groups SET course = ? WHERE id = ?", (course, group_id)
    )
    await db.commit()
    return cursor.rowcount > 0


async def get_group_stats(group_id: int):
    """Скільки предметів, конспектів і студентів у групі (для підтвердження видалення)."""
    db = get_db()
    async with db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM subjects WHERE group_id = ?) AS subjects,
            (SELECT COUNT(*) FROM notes WHERE group_id = ?) AS notes,
            (SELECT COUNT(*) FROM users WHERE group_id = ?) AS users
        """,
        (group_id, group_id, group_id),
    ) as cursor:
        return await cursor.fetchone()


async def rename_group(group_id: int, new_name: str) -> str:
    """Перейменовує групу. Повертає 'ok', 'exists' (така назва вже є) або 'missing'."""
    db = get_db()
    new_name = clean_name(new_name)
    try:
        cursor = await db.execute(
            "UPDATE groups SET name = ?, name_key = ? WHERE id = ?",
            (new_name, new_name.casefold(), group_id),
        )
        await db.commit()
    except sqlite3.IntegrityError:
        await db.rollback()
        return "exists"
    return "ok" if cursor.rowcount > 0 else "missing"


async def delete_group(group_id: int) -> bool:
    """Видаляє групу разом з її предметами та конспектами. False - якщо групи вже немає."""
    db = get_db()
    cursor = await db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    await db.commit()
    return cursor.rowcount > 0
