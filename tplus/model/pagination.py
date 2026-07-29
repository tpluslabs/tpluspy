from pydantic import BaseModel


class PageMeta(BaseModel):
    """Pagination metadata shared by every paged response, mirroring the backend
    `PageMeta` that is flattened into each page."""

    page: int
    limit: int
    total_pages: int
    cursor_size: int
    has_next_page: bool
    next_page: int | None = None

    @classmethod
    def single_page(cls, count: int) -> "PageMeta":
        """Metadata for wrapping a bare, unpaginated list as one full page."""
        return cls(
            page=0,
            limit=count,
            total_pages=1 if count else 0,
            cursor_size=count,
            has_next_page=False,
        )
