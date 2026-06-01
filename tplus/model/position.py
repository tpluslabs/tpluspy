from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier

PositionSide = Literal["long", "short"]


class PositionResponse(BaseModel):
    asset_id: AssetIdentifier
    sub_account_index: int
    name: str
    side: PositionSide
    size: Decimal
    entry_price: Decimal | None = None
    mark_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    margin: Decimal | None = None
    leverage: Decimal | None = None
    liquidation_price: Decimal | None = None
    base_credits: Decimal
    base_liabilities: Decimal
    quote_credits: Decimal
    quote_liabilities: Decimal


class UserPositionsPage(BaseModel):
    positions: list[PositionResponse]
    page: int
    limit: int
    total_positions: int
    total_pages: int
    cursor_size: int
    has_next_page: bool
    next_page: int | None = None


def parse_positions(data: list[dict]) -> list[PositionResponse]:
    return [PositionResponse.model_validate(item) for item in data]


def parse_positions_page(data: list[dict] | dict) -> UserPositionsPage:
    if isinstance(data, list):
        positions = parse_positions(data)
        count = len(positions)
        return UserPositionsPage(
            positions=positions,
            page=0,
            limit=count,
            total_positions=count,
            total_pages=1 if count else 0,
            cursor_size=count,
            has_next_page=False,
        )
    return UserPositionsPage.model_validate(data)
