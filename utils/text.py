import re
from datetime import datetime


def plural_notes(count: int) -> str:
    """Правильна форма слова: 1 конспект, 2 конспекти, 5 конспектів."""
    last_digit = count % 10
    last_two = count % 100
    if last_digit == 1 and last_two != 11:
        word = "конспект"
    elif 2 <= last_digit <= 4 and not (12 <= last_two <= 14):
        word = "конспекти"
    else:
        word = "конспектів"
    return f"{count} {word}"


def short_text(text: str, limit: int = 45) -> str:
    """Скорочує довгий текст для кнопки: 'Дуже довга назва...' """
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def format_date(value: str) -> str:
    """'2026-11-18 00:02:35' -> '18.11.2026'."""
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return value or ""


def natural_key(text: str):
    """Ключ для «людського» сортування: 'Тема 2' іде перед 'Тема 10'."""
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", text or "")
    ]


def breadcrumb(*parts) -> str:
    """Шлях у вигляді: 1 курс › КН-11 › Мат. Аналіз › Тема 1."""
    return " › ".join(str(part) for part in parts if part)
