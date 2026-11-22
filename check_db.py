# Перевірка схеми бази. Працює в пам'яті, твою справжню базу не чіпає.
import sqlite3

from database.models import SCHEMA

conn = sqlite3.connect(":memory:")
conn.execute("PRAGMA foreign_keys = ON")
conn.executescript(SCHEMA)


def ok(text, sql, params=()):
    conn.execute(sql, params)
    print("✅", text)


def expect_error(text, sql, params=()):
    try:
        conn.execute(sql, params)
        print("❌", text, "- помилки НЕ було, а мала бути")
    except sqlite3.IntegrityError:
        print("✅", text)


G = "INSERT INTO groups (name, name_key) VALUES (?, ?)"
S = "INSERT INTO subjects (group_id, name, name_key) VALUES (?, ?, ?)"
N = (
    "INSERT INTO notes (group_id, subject_id, title, file_id, "
    "file_unique_id, uploaded_by) VALUES (?, ?, ?, ?, ?, ?)"
)

ok("Створено групу КН-21", G, ("КН-21", "кн-21"))
ok("Створено групу КН-22", G, ("КН-22", "кн-22"))
expect_error("Дубль назви групи заборонено", G, ("кн-21", "кн-21"))

expect_error("Предмет у неіснуючій групі заборонено", S, (999, "C++", "c++"))
ok("Предмет C++ у КН-21", S, (1, "C++", "c++"))
expect_error("Дубль предмета в одній групі заборонено", S, (1, "c++", "c++"))
ok("Той самий предмет C++ у КН-22 дозволено", S, (2, "C++", "c++"))

ok(
    "Створено користувача в групі КН-21",
    "INSERT INTO users (telegram_id, first_name, group_id) VALUES (111, 'Тест', 1)",
)

expect_error(
    "Конспект із предметом чужої групи заборонено",
    N,
    (1, 2, "Лекція 1", "file1", "uniq1", 111),
)
ok("Конспект збережено", N, (1, 1, "Лекція 1", "file1", "uniq1", 111))
expect_error(
    "Повторне збереження того самого файлу заборонено",
    N,
    (1, 1, "Лекція 1 (копія)", "file1", "uniq1", 111),
)

conn.execute("DELETE FROM groups WHERE id = 1")
notes = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
subjects = conn.execute("SELECT COUNT(*) FROM subjects WHERE group_id = 1").fetchone()[0]
user_group = conn.execute("SELECT group_id FROM users WHERE telegram_id = 111").fetchone()[0]

print("✅" if notes == 0 else "❌", "Після видалення групи конспекти видалено")
print("✅" if subjects == 0 else "❌", "Після видалення групи предмети видалено")
print("✅" if user_group is None else "❌", "У користувача група стала порожньою")
print("Перевірку завершено")
