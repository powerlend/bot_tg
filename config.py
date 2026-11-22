import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token: str
    admin_ids: list
    db_path: str
    max_file_mb: int
    upload_limit_per_hour: int
    backup_enabled: bool
    backup_hour: int
    backup_keep: int
    # Хостинг (Render): порт для сторінки здоров'я, адреса для самопінгу, чи увімкнена реплікація
    port: int = 0
    keepalive_url: str = ""
    litestream_enabled: bool = False


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задано у файлі .env")

    raw_ids = os.getenv("ADMIN_IDS", "")
    admin_ids = []
    for part in raw_ids.split(","):
        part = part.strip()
        if part.isdigit():
            admin_ids.append(int(part))

    if len(admin_ids) > 5:
        raise RuntimeError("У ADMIN_IDS може бути максимум 5 адміністраторів")

    # Де лежить файл бази. За замовчуванням: data/bot.db
    db_path = os.getenv("DB_PATH", "data/bot.db").strip() or "data/bot.db"

    # Максимальний розмір файлу в МБ. За замовчуванням: 20
    raw_size = os.getenv("MAX_FILE_MB", "20").strip()
    max_file_mb = int(raw_size) if raw_size.isdigit() and int(raw_size) > 0 else 20

    # Скільки конспектів один користувач може додати за годину. За замовчуванням: 20
    raw_limit = os.getenv("UPLOAD_LIMIT_PER_HOUR", "20").strip()
    upload_limit = int(raw_limit) if raw_limit.isdigit() and int(raw_limit) > 0 else 20

    # Резервні копії бази: увімкнено чи ні, о котрій годині (UTC) і скільки копій зберігати
    backup_enabled = os.getenv("BACKUP_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
    raw_hour = os.getenv("BACKUP_HOUR", "3").strip()
    backup_hour = int(raw_hour) if raw_hour.isdigit() and 0 <= int(raw_hour) <= 23 else 3
    raw_keep = os.getenv("BACKUP_KEEP", "7").strip()
    backup_keep = int(raw_keep) if raw_keep.isdigit() and int(raw_keep) > 0 else 7

    # Порт для сторінки здоров'я. Render задає змінну PORT сам; локально її немає (тоді вимкнено)
    raw_port = os.getenv("PORT", "").strip()
    port = int(raw_port) if raw_port.isdigit() and 0 < int(raw_port) < 65536 else 0

    # Публічна адреса сервісу для самопінгу. На Render підставляється автоматично
    keepalive_url = (
        os.getenv("KEEPALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""
    ).strip().rstrip("/")
    if not keepalive_url.startswith(("http://", "https://")):
        keepalive_url = ""

    # Чи налаштована реплікація бази в хмару (Litestream)
    litestream_enabled = bool(os.getenv("LITESTREAM_BUCKET", "").strip())

    return Config(
        bot_token=token,
        admin_ids=admin_ids,
        db_path=db_path,
        max_file_mb=max_file_mb,
        upload_limit_per_hour=upload_limit,
        backup_enabled=backup_enabled,
        backup_hour=backup_hour,
        backup_keep=backup_keep,
        port=port,
        keepalive_url=keepalive_url,
        litestream_enabled=litestream_enabled,
    )
