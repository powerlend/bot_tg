from database.db import get_db


async def get_overview():
    """Загальні цифри: користувачі, групи, предмети, конспекти, завантаження."""
    db = get_db()
    async with db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM users) AS users_total,
            (SELECT COUNT(*) FROM users WHERE is_blocked = 1) AS users_blocked,
            (SELECT COUNT(*) FROM users
              WHERE is_blocked = 0
                AND last_active_at >= datetime('now', '-7 days')) AS users_active,
            (SELECT COUNT(*) FROM groups) AS groups_total,
            (SELECT COUNT(*) FROM subjects) AS subjects_total,
            (SELECT COUNT(*) FROM notes) AS notes_total,
            (SELECT COALESCE(SUM(downloads_count), 0) FROM notes) AS downloads_total,
            (SELECT COUNT(*) FROM suggestions) AS suggestions_total,
            (SELECT COUNT(*) FROM suggestions WHERE status = 'new') AS suggestions_new,
            (SELECT COUNT(*) FROM complaints) AS complaints_total,
            (SELECT COUNT(*) FROM complaints WHERE status = 'new') AS complaints_new
        """
    ) as cursor:
        return await cursor.fetchone()


async def get_period_stats(hours: int):
    """Цифри за останні `hours` годин (рухоме вікно, а не календарний день)."""
    since = f"-{int(hours)} hours"
    db = get_db()
    async with db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM users
              WHERE created_at >= datetime('now', ?)) AS new_users,
            (SELECT COUNT(*) FROM notes
              WHERE created_at >= datetime('now', ?)) AS new_notes,
            (SELECT COUNT(*) FROM downloads
              WHERE created_at >= datetime('now', ?)) AS downloads,
            (SELECT COUNT(*) FROM users
              WHERE is_blocked = 0
                AND last_active_at >= datetime('now', ?)) AS active_users
        """,
        (since, since, since, since),
    ) as cursor:
        return await cursor.fetchone()
