from typing import overload

from pydantic import BaseModel, ConfigDict, Field

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.pagination import PageMeta


class Market(BaseModel):
    asset_id: AssetIdentifier
    book_price_decimals: int
    book_quantity_decimals: int


class Asset(BaseModel):
    """One canonical asset index and the token symbols that are fungible into it."""

    index: int
    symbol: str
    name: str
    asset_class: str
    representations: list[str]


class FeeTierConfig(BaseModel):
    min_rolling_volume_usd: int
    taker_fee_rate: int
    maker_fee_rate: int
    maker_rebate_rate_of_taker_fee: int | None = None


class MarketFeeSchedule(BaseModel):
    """Fee ladder and fee account for a market, from the active orderbook config."""

    model_config = ConfigDict(populate_by_name=True)

    fee_account: str
    global_: list[FeeTierConfig] = Field(alias="global")
    per_asset: list[FeeTierConfig]


class MarketResponse(BaseModel):
    asset_id: AssetIdentifier
    book_price_decimals: int
    book_quantity_decimals: int
    max_leverage: str | None = None
    current_long_max_leverage: str | None = None
    current_short_max_leverage: str | None = None
    isolated_only: bool = False
    min_order_size: str | None = None
    tick_size: str | None = None
    fee_schedule: MarketFeeSchedule | None = None


class MarketsPage(PageMeta):
    """One page of markets plus pagination metadata, and the canonical asset
    table when it was requested.

    Behaves like a sequence of `MarketResponse` for list-style callers.
    """

    markets: list[MarketResponse]
    symbol_map: dict[int, Asset] | None = None
    total_markets: int

    def __iter__(self):
        return iter(self.markets)

    def __len__(self) -> int:
        return len(self.markets)

    @overload
    def __getitem__(self, index: int) -> MarketResponse: ...

    @overload
    def __getitem__(self, index: slice) -> list[MarketResponse]: ...

    def __getitem__(self, index: int | slice) -> MarketResponse | list[MarketResponse]:
        return self.markets[index]

    def __bool__(self) -> bool:
        return bool(self.markets)

    def __contains__(self, item: object) -> bool:
        return item in self.markets


def parse_market(data: dict) -> Market:
    return Market(
        asset_id=AssetIdentifier(data["asset_id"]),
        book_price_decimals=data["book_price_decimals"],
        book_quantity_decimals=data["book_quantity_decimals"],
    )
