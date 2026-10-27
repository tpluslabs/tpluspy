from pydantic import BaseModel


class VaultBalance(BaseModel):
    """A token's free and locked vault balance at 18 decimals."""

    balance: int
    locked_balance: int
