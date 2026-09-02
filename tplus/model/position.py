from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.pagination import PageMeta

PositionSide = Literal["long", "short", "closed"]


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


class UserPositionsPage(PageMeta):
    positions: list[PositionResponse]
    total_positions: int


class PositionUpdate(BaseModel):
    user_id: str
    positions: list[PositionResponse]
    timestamp_ns: int


def parse_positions(data: list[dict]) -> list[PositionResponse]:
    return [PositionResponse.model_validate(item) for item in data]


def parse_position_update(data: dict) -> PositionUpdate:
    return PositionUpdate.model_validate(data)


def parse_positions_page(data: list[dict] | dict) -> UserPositionsPage:
    if isinstance(data, list):
        positions = parse_positions(data)
        count = len(positions)
        return UserPositionsPage(
            positions=positions,
            total_positions=count,
            **PageMeta.single_page(count).model_dump(),
        )
    return UserPositionsPage.model_validate(data)
