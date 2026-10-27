"""How a canonical ledger amount becomes the integer a chain transfers."""

from pydantic import BaseModel


class ConversionInfo(BaseModel):
    """What a leg's canonical amount became under the rate its approval was signed at."""

    canonical_per_representation: int
    state_id: str
    canonical_amount: int
    representation_amount: int
    chain_amount: int
    representation_remainder: int
