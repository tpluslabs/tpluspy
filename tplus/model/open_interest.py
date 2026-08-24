from decimal import Decimal

from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier


class OpenInterest(BaseModel):
    """Outstanding exposure for a market, per side, in asset quantity."""

    asset_id: AssetIdentifier
    long: Decimal | None = None
    short: Decimal | None = None
    timestamp_ns: int | None = None

    @property
    def total_open_interest(self) -> Decimal | None:
        """Takes the larger side rather than the sum, matching the engine's cap accounting."""
        sides = [side for side in (self.long, self.short) if side is not None]
        if not sides:
            return None

        return max(sides)


def parse_open_interest(data: list[dict]) -> list[OpenInterest]:
    return [OpenInterest.model_validate(row) for row in data]
