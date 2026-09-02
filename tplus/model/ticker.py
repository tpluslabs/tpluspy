from decimal import Decimal

from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier


class BookLevel(BaseModel):
    """A single book level: price and total size resting at that price."""

    price: Decimal
    size: Decimal


class TickerOpenInterest(BaseModel):
    """Outstanding exposure per side, in asset quantity."""

    long: Decimal | None = None
    short: Decimal | None = None
    timestamp_ns: int

    @property
    def total_open_interest(self) -> Decimal | None:
        """Takes the larger side rather than the sum, matching the engine's cap accounting."""
        sides = [side for side in (self.long, self.short) if side is not None]
        if not sides:
            return None

        return max(sides)


class Ticker(BaseModel):
    """24h summary for one market."""

    asset_id: AssetIdentifier
    last_price: Decimal | None = None
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    best_bid: BookLevel | None = None
    best_ask: BookLevel | None = None
    open_interest: TickerOpenInterest | None = None
    volume_24h: Decimal
    high_24h: Decimal | None = None
    low_24h: Decimal | None = None
    price_change_24h: Decimal | None = None
    price_change_pct_24h: Decimal | None = None
    timestamp_ns: int


def parse_tickers(data: list[dict]) -> list[Ticker]:
    return [Ticker.model_validate(row) for row in data]
