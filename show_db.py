# Показує, що зараз лежить у базі (групи, предмети, теми, користувачі, конспекти).
import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "data/bot.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

print("Версія структури бази:", conn.execute("PRAGMA user_version").fetchone()[0])


def show(title, sql):
    print("\n==", title)
    rows = conn.execute(sql).fetchall()
    if not rows:
        print("(порожньо)")
        return
    for row in rows:
        print(dict(row))


show("Групи", "SELECT id, name, course FROM groups ORDER BY course, name")
show("Предмети", "SELECT id, group_id, name FROM subjects")
show("Теми (папки)", "SELECT id, subject_id, title FROM topics ORDER BY subject_id, title")
show(
    "Користувачі",
    "SELECT telegram_id, username, first_name, group_id, is_blocked FROM users",
)
show(
    "Конспекти",
    "SELECT id, subject_id, topic_id, title, file_name, file_type, "
    "uploaded_by, show_author_tag, created_at FROM notes",
)
show(
    "Пропозиції",
    "SELECT id, user_id, status, substr(text, 1, 40) AS text, created_at FROM suggestions",
)
show(
    "Скарги",
    "SELECT id, note_id, user_id, reason, status, substr(comment, 1, 30) AS comment, created_at FROM complaints",
)
