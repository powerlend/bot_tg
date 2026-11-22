from aiogram.fsm.state import State, StatesGroup


class UploadStates(StatesGroup):
    """Кроки завантаження конспекту."""

    choosing_topic = State()      # вибір теми (папки) кнопкою
    waiting_topic_title = State() # введення назви нової теми
    waiting_title = State()       # назва самого конспекту (можна пропустити)
    choosing_tag = State()        # показувати свій тег автора чи ні
    waiting_file = State()   # чекаємо файл


class SearchStates(StatesGroup):
    """Пошук конспекту за назвою."""

    waiting_query = State()  # чекаємо текст запиту


class AdminStates(StatesGroup):
    """Введення назв в адмін-панелі."""

    group_add_name = State()
    group_rename_name = State()
    subject_add_name = State()
    subject_rename_name = State()
    notes_search = State()
    users_search = State()
    topic_rename_name = State()


class SuggestStates(StatesGroup):
    """Розділ «Пропозиції»."""

    waiting_text = State()  # чекаємо текст пропозиції


class ComplaintStates(StatesGroup):
    """Скарга на конспект."""

    waiting_comment = State()  # чекаємо опис проблеми (для причини «Інша»)
