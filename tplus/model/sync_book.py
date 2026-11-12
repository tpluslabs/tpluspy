from enum import Enum

from pydantic import BaseModel


class CreateSyncBookStatus(str, Enum):
    """Whether a create-sync-book request made the book or found the existing one."""

    CREATED = "Created"
    """This request made the sync book."""

    ALREADY_EXISTED = "AlreadyExisted"
    """The market maker already had a sync book on this market; it is left as it was."""


class CreateSyncBookResponse(BaseModel):
    """The reply to ``POST /sync_book/create`` and ``POST /admin/sync-book``.

    A market maker holds at most one sync book per market.
    """

    asset_id: str
    mm_pubkey: str
    status: CreateSyncBookStatus
