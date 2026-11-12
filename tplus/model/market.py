from enum import Enum
from typing import Any, overload

from pydantic import BaseModel, ConfigDict, Field

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.pagination import PageMeta


class MarketTypeFilter(str, Enum):
    """Which markets `GET /markets` keeps, by `is_spot_enabled` or `is_margin_enabled`."""

    SPOT = "spot"
    MARGIN = "margin"

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if isinstance(value, str):
            val_lower = value.lower()
            for member in cls:
                if member.value == val_lower:
                    return member
        return super()._missing_(value)


class Market(BaseModel):
    asset_id: AssetIdentifier
    book_price_decimals: int
    book_quantity_decimals: int


class ChainAsset(BaseModel):
    """One token deployment of an asset."""

    chain: str
    chain_id: str
    address: str


class MarketAsset(BaseModel):
    """A market's asset; fields are None when the OMS does not know them."""

    symbol: str | None = None
    name: str | None = None
    asset_class: str | None = None
    representations: list[str] | None = None
    chain_assets: list[ChainAsset] | None = None


class FeeTierConfig(BaseModel):
    min_rolling_volume_usd: int
    taker_fee_rate: int
    maker_fee_rate: int
    maker_rebate_rate_of_taker_fee: int | None = None


class MarketFeeSchedule(BaseModel):
    """Fee ladder for a market, from the active orderbook config."""

    model_config = ConfigDict(populate_by_name=True)

    global_: list[FeeTierConfig] = Field(alias="global")
    per_asset: list[FeeTierConfig]


class MarketResponse(BaseModel):
    asset_id: AssetIdentifier
    book_price_decimals: int
    book_quantity_decimals: int
    max_leverage: str | None = None
    current_long_max_leverage: str | None = None
    current_short_max_leverage: str | None = None
    is_spot_enabled: bool = False
    is_margin_enabled: bool = False
    isolated_only: bool = False
    min_order_size: str | None = None
    tick_size: str | None = None
    fee_schedule: MarketFeeSchedule | None = None
    asset: MarketAsset = Field(default_factory=MarketAsset)


class MarketsPage(PageMeta):
    """One page of markets plus pagination metadata.

    Behaves like a sequence of `MarketResponse` for list-style callers.
    """

    markets: list[MarketResponse]
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
