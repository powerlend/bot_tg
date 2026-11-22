import os

# Дозволені розширення файлів. Хочеш додати формат - допиши його в цей список.
ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "txt", "rtf", "odt", "odp", "ods", "jpg", "jpeg", "png",
}

FORMATS_TEXT = "PDF, DOC/DOCX, PPT/PPTX, XLS/XLSX, TXT, RTF, ODT, JPG, PNG"


def get_extension(file_name) -> str:
    """'Лекція.PDF' -> 'pdf'. Якщо розширення немає, повертає ''."""
    return os.path.splitext(file_name or "")[1].lower().lstrip(".")


def check_file(extension: str, size, max_mb: int):
    """Перевіряє формат і розмір. Повертає текст помилки або None, якщо все гаразд."""
    if extension not in ALLOWED_EXTENSIONS:
        return (
            "⚠️ Цей формат не підтримується.\n"
            f"Підтримуються: {FORMATS_TEXT}."
        )
    if size is not None and size > max_mb * 1024 * 1024:
        return f"⚠️ Файл завеликий. Максимальний розмір: {max_mb} МБ."
    return None
