from aiogram import Router

from handlers.admin import (
    complaints,
    groups,
    menu,
    notes,
    settings,
    statistics,
    subjects,
    suggestions,
    topics,
    users,
)
from middlewares.admin import AdminOnlyMiddleware

# Головний адмін-роутер. Перевірка прав підключена до нього,
# тому вона діє на всі вкладені роутери.
router = Router(name="admin")
router.message.middleware(AdminOnlyMiddleware())
router.callback_query.middleware(AdminOnlyMiddleware())

router.include_router(menu.router)
router.include_router(groups.router)
router.include_router(subjects.router)
router.include_router(topics.router)
router.include_router(notes.router)
router.include_router(users.router)
router.include_router(statistics.router)
router.include_router(settings.router)
router.include_router(suggestions.router)
router.include_router(complaints.router)
