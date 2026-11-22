"""Створення та оновлення структури бази даних.

Версія структури зберігається в самій базі (PRAGMA user_version).
Нова база створюється одразу за останньою схемою. Стара база оновлюється
по кроках (міграціях), кожен крок виконується в одній транзакції:
якщо щось піде не так, база лишається такою, якою була.
Перед оновленням автоматично робиться резервна копія бази.
"""
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone

from database.models import SCHEMA, SCHEMA_VERSION

logger = logging.getLogger(__name__)

# Папка, у яку потрапляють усі старі конспекти (завантажені до появи тем)
DEFAULT_TOPIC = "Загальне"


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _column_exists(conn, table: str, column: str) -> bool:
    # назва таблиці береться з нашого коду, а не від користувача
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def guess_course(group_name: str) -> int:
    """Вгадує курс за першою цифрою в назві групи: КН-11 -> 1, КН-21 -> 2. Не вийшло -> 1."""
    match = re.search(r"\d", group_name or "")
    if match and match.group() in "1234":
        return int(match.group())
    return 1


# ---------- Міграції ----------

def migrate_to_v1(conn) -> None:
    """Версія 1: структура після кроків 1-10 (останні зміни: активність і історія
    завантажень). Усе перевіряється, тому повторний запуск безпечний."""
    if not _column_exists(conn, "users", "last_active_at"):
        conn.execute("ALTER TABLE users ADD COLUMN last_active_at TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS downloads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id     INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            user_id     INTEGER REFERENCES users(telegram_id) ON DELETE SET NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_created ON downloads(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_note ON downloads(note_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_active ON users(last_active_at)")


def migrate_to_v2(conn) -> None:
    """Версія 2: у груп з'являється курс (1-4)."""
    if not _column_exists(conn, "groups", "course"):
        conn.execute(
            "ALTER TABLE groups ADD COLUMN course INTEGER NOT NULL DEFAULT 1 "
            "CHECK (course BETWEEN 1 AND 4)"
        )
        # Існуючим групам ставимо курс за назвою (адмін зможе змінити його в панелі)
        for group_id, name in conn.execute("SELECT id, name FROM groups").fetchall():
            conn.execute(
                "UPDATE groups SET course = ? WHERE id = ?", (guess_course(name), group_id)
            )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_groups_course ON groups(course)")


def _backfill_default_topic(conn) -> None:
    """Конспекти без теми переносить у папку «Загальне» свого предмета.
    Безпечно викликати повторно: нічого не робить, якщо таких конспектів немає."""
    key = DEFAULT_TOPIC.casefold()
    subject_ids = [
        row[0]
        for row in conn.execute(
            "SELECT DISTINCT subject_id FROM notes WHERE topic_id IS NULL"
        ).fetchall()
    ]
    for subject_id in subject_ids:
        conn.execute(
            "INSERT OR IGNORE INTO topics (subject_id, title, title_key) VALUES (?, ?, ?)",
            (subject_id, DEFAULT_TOPIC, key),
        )
        topic_id = conn.execute(
            "SELECT id FROM topics WHERE subject_id = ? AND title_key = ?",
            (subject_id, key),
        ).fetchone()[0]
        conn.execute(
            "UPDATE notes SET topic_id = ? WHERE subject_id = ? AND topic_id IS NULL",
            (topic_id, subject_id),
        )


def migrate_to_v4(conn) -> None:
    """Версія 4: для кожного конспекту зберігається вибір автора - показувати свій
    @username чи ні. Усі наявні конспекти отримують 0 (тег прихований), тобто
    нічого не розкривається автоматично."""
    if not _column_exists(conn, "notes", "show_author_tag"):
        conn.execute(
            "ALTER TABLE notes ADD COLUMN show_author_tag INTEGER NOT NULL DEFAULT 0 "
            "CHECK (show_author_tag IN (0, 1))"
        )
    # Страховка: конспекти без теми були б невидимими для студентів
    _backfill_default_topic(conn)


def migrate_to_v3(conn) -> None:
    """Версія 3: папки з темами. Усі наявні конспекти потрапляють у папку «Загальне»
    свого предмета, тож нічого не губиться."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS topics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            title       TEXT NOT NULL,
            title_key   TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (subject_id, title_key)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topics_subject ON topics(subject_id)")
    if not _column_exists(conn, "notes", "topic_id"):
        conn.execute(
            "ALTER TABLE notes ADD COLUMN topic_id INTEGER "
            "REFERENCES topics(id) ON DELETE CASCADE"
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notes_topic ON notes(topic_id)")

    _backfill_default_topic(conn)


def migrate_to_v5(conn) -> None:
    """Версія 5: нова таблиця пропозицій користувачів. Наявні дані не чіпаємо."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS suggestions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER REFERENCES users(telegram_id) ON DELETE SET NULL,
            text        TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'new'
                        CHECK (status IN ('new', 'in_progress', 'done', 'rejected')),
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions(status, created_at)"
    )


def migrate_to_v6(conn) -> None:
    """Версія 6: нова таблиця скарг на конспекти. Наявні дані не чіпаємо."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS complaints (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id     INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            user_id     INTEGER REFERENCES users(telegram_id) ON DELETE SET NULL,
            reason      TEXT NOT NULL
                        CHECK (reason IN ('off_topic', 'low_quality', 'copyright', 'inappropriate', 'other')),
            comment     TEXT,
            status      TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'resolved', 'rejected')),
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (note_id, user_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status, created_at)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_complaints_note ON complaints(note_id)")


MIGRATIONS = {
    1: migrate_to_v1,
    2: migrate_to_v2,
    3: migrate_to_v3,
    4: migrate_to_v4,
    5: migrate_to_v5,
    6: migrate_to_v6,
}


# ---------- Запуск ----------

def _backup_before_migration(conn, db_path: str, current_version: int) -> str:
    """Копія бази перед оновленням структури (лежить у data/backups)."""
    folder = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    target = os.path.join(folder, f"pre_migration_v{current_version}_{stamp}.db")
    dest = sqlite3.connect(target)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    return target


def migrate(db_path: str) -> None:
    """Створює нову базу або оновлює стару до останньої версії структури."""
    folder = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(folder, exist_ok=True)

    # isolation_level=None: транзакціями керуємо вручну (BEGIN / COMMIT)
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        # Режим WAL: його вимагає Litestream для реплікації й він надійніший при одночасному читанні та записі
        conn.execute("PRAGMA journal_mode = WAL")
        current = conn.execute("PRAGMA user_version").fetchone()[0]

        # Нова порожня база: одразу створюємо за останньою схемою
        if not _table_exists(conn, "groups"):
            conn.executescript(SCHEMA)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            logger.info("Створено нову базу даних (версія структури %s)", SCHEMA_VERSION)
            return

        if current >= SCHEMA_VERSION:
            return

        backup = _backup_before_migration(conn, db_path, current)
        logger.info("Перед оновленням бази створено копію: %s", backup)

        for version in range(current + 1, SCHEMA_VERSION + 1):
            conn.execute("BEGIN")
            try:
                MIGRATIONS[version](conn)
                conn.execute(f"PRAGMA user_version = {version}")
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                logger.exception("Не вдалося оновити базу до версії %s", version)
                raise
            logger.info("Базу оновлено до версії %s", version)
    finally:
        conn.close()
