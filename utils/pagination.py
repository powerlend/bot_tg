PAGE_SIZE = 8  # скільки конспектів показувати на одній сторінці


def total_pages(total: int, page_size: int = PAGE_SIZE) -> int:
    """Скільки всього сторінок (мінімум 1, навіть якщо список порожній)."""
    return max(1, (total + page_size - 1) // page_size)


def clamp_page(page: int, pages: int) -> int:
    """Не дає вийти за межі: номер сторінки завжди від 0 до pages-1."""
    return min(max(page, 0), pages - 1)
