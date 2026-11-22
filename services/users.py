from database.db import get_db


async def register_user(telegram_id: int, username, first_name):
    """Створює користувача при першому запуску або оновлює його ім'я та username."""
    db = get_db()
    await db.execute(
        """
        INSERT INTO users (telegram_id, username, first_name, last_active_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_active_at = datetime('now')
        """,
        (telegram_id, username, first_name),
    )
    await db.commit()
    async with db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    ) as cursor:
        return await cursor.fetchone()


async def set_user_group(telegram_id: int, group_id: int) -> None:
    """Запам'ятовує вибрану групу користувача."""
    db = get_db()
    await db.execute(
        "UPDATE users SET group_id = ? WHERE telegram_id = ?",
        (group_id, telegram_id),
    )
    await db.commit()


async def get_user_group(telegram_id: int):
    """Повертає групу користувача (id, name) або None, якщо групи немає."""
    db = get_db()
    async with db.execute(
        """
        SELECT g.id, g.name, g.course
        FROM users u
        JOIN groups g ON g.id = u.group_id
        WHERE u.telegram_id = ?
        """,
        (telegram_id,),
    ) as cursor:
        return await cursor.fetchone()


async def is_user_blocked(telegram_id: int) -> bool:
    """True, якщо користувача заблоковано. Невідомий користувач не заблокований."""
    db = get_db()
    async with db.execute(
        "SELECT is_blocked FROM users WHERE telegram_id = ?", (telegram_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return bool(row and row["is_blocked"])


async def set_blocked(telegram_id: int, blocked: bool) -> bool:
    """Блокує або розблоковує користувача. False - якщо такого користувача немає."""
    db = get_db()
    cursor = await db.execute(
        "UPDATE users SET is_blocked = ? WHERE telegram_id = ?",
        (1 if blocked else 0, telegram_id),
    )
    await db.commit()
    return cursor.rowcount > 0


async def count_users() -> int:
    db = get_db()
    async with db.execute("SELECT COUNT(*) FROM users") as cursor:
        row = await cursor.fetchone()
    return row[0]


async def get_users_page(page: int, page_size: int):
    """Одна сторінка користувачів (спочатку найновіші). page починається з 0."""
    db = get_db()
    async with db.execute(
        """
        SELECT telegram_id, first_name, username, is_blocked
        FROM users
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (page_size, page * page_size),
    ) as cursor:
        return await cursor.fetchall()


async def get_user_card(telegram_id: int):
    """Повна інформація про користувача для адміна."""
    db = get_db()
    async with db.execute(
        """
        SELECT u.telegram_id, u.first_name, u.username, u.is_blocked, u.created_at,
               g.name AS group_name,
               (SELECT COUNT(*) FROM notes n WHERE n.uploaded_by = u.telegram_id)
                   AS notes_count
        FROM users u
        LEFT JOIN groups g ON g.id = u.group_id
        WHERE u.telegram_id = ?
        """,
        (telegram_id,),
    ) as cursor:
        return await cursor.fetchone()


async def search_users(query: str, limit: int = 20):
    """Шукає за Telegram ID, username або іменем. Повертає (список до limit, всього знайдено)."""
    db = get_db()
    async with db.execute(
        """
        SELECT telegram_id, first_name, username, is_blocked
        FROM users
        ORDER BY created_at DESC, id DESC
        """
    ) as cursor:
        rows = await cursor.fetchall()

    needle = query.strip().lstrip("@").casefold()
    matches = []
    for row in rows:
        haystack = [
            str(row["telegram_id"]),
            (row["username"] or "").casefold(),
            (row["first_name"] or "").casefold(),
        ]
        if any(needle in part for part in haystack if part):
            matches.append(row)
    return matches[:limit], len(matches)


async def touch_user(telegram_id: int, username, first_name) -> None:
    """Запам'ятовує час останньої активності (не частіше ніж раз на 5 хвилин) і
    оновлює username та ім'я, якщо користувач їх змінив у Telegram. Так тег автора
    під конспектом завжди актуальний."""
    db = get_db()
    await db.execute(
        """
        UPDATE users SET last_active_at = datetime('now')
        WHERE telegram_id = ?
          AND (last_active_at IS NULL
               OR last_active_at < datetime('now', '-5 minutes'))
        """,
        (telegram_id,),
    )
    await db.execute(
        """
        UPDATE users SET username = ?, first_name = ?
        WHERE telegram_id = ? AND (username IS NOT ? OR first_name IS NOT ?)
        """,
        (username, first_name, telegram_id, username, first_name),
    )
    await db.commit()
