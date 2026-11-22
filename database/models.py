# Схема бази даних для НОВОЇ (порожньої) бази: усі таблиці описані тут.
# Стару базу оновлює файл migrations.py. Змінюєш схему - збільш SCHEMA_VERSION
# і додай відповідну міграцію.
SCHEMA_VERSION = 6

# Дати зберігаються у UTC у форматі "РРРР-ММ-ДД ГГ:ХХ:СС".

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    name_key    TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    course      INTEGER NOT NULL DEFAULT 1 CHECK (course BETWEEN 1 AND 4)
);

CREATE TABLE IF NOT EXISTS subjects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    name_key    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (group_id, name_key),
    UNIQUE (id, group_id)
);

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    username    TEXT,
    first_name  TEXT,
    group_id    INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    is_blocked  INTEGER NOT NULL DEFAULT 0 CHECK (is_blocked IN (0, 1)),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_active_at TEXT
);

-- Папки з темами всередині предмета
CREATE TABLE IF NOT EXISTS topics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    title_key   TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (subject_id, title_key)
);

CREATE TABLE IF NOT EXISTS notes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id         INTEGER NOT NULL,
    subject_id       INTEGER NOT NULL,
    title            TEXT NOT NULL,
    file_id          TEXT NOT NULL,
    file_unique_id   TEXT NOT NULL,
    file_name        TEXT,
    file_type        TEXT,
    uploaded_by      INTEGER REFERENCES users(telegram_id) ON DELETE SET NULL,
    downloads_count  INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    topic_id         INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    show_author_tag  INTEGER NOT NULL DEFAULT 0 CHECK (show_author_tag IN (0, 1)),
    FOREIGN KEY (subject_id, group_id)
        REFERENCES subjects(id, group_id) ON DELETE CASCADE,
    UNIQUE (subject_id, file_unique_id)
);

-- Пропозиції користувачів щодо покращення бота
CREATE TABLE IF NOT EXISTS suggestions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(telegram_id) ON DELETE SET NULL,
    text        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'in_progress', 'done', 'rejected')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Скарги студентів на конспекти (одна скарга від одного студента на конспект)
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
);

-- Історія завантажень файлів (для статистики за день, тиждень, місяць)
CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id     INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    user_id     INTEGER REFERENCES users(telegram_id) ON DELETE SET NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_subjects_group    ON subjects(group_id);
CREATE INDEX IF NOT EXISTS idx_downloads_created ON downloads(created_at);
CREATE INDEX IF NOT EXISTS idx_downloads_note    ON downloads(note_id);
CREATE INDEX IF NOT EXISTS idx_users_active      ON users(last_active_at);
CREATE INDEX IF NOT EXISTS idx_groups_course     ON groups(course);
CREATE INDEX IF NOT EXISTS idx_topics_subject    ON topics(subject_id);
CREATE INDEX IF NOT EXISTS idx_notes_topic       ON notes(topic_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions(status, created_at);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status, created_at);
CREATE INDEX IF NOT EXISTS idx_complaints_note   ON complaints(note_id);
CREATE INDEX IF NOT EXISTS idx_users_group       ON users(group_id);
CREATE INDEX IF NOT EXISTS idx_notes_subject     ON notes(subject_id);
CREATE INDEX IF NOT EXISTS idx_notes_group       ON notes(group_id);
CREATE INDEX IF NOT EXISTS idx_notes_created     ON notes(created_at);
"""
