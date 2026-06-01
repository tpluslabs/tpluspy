"""Read-only client for the `market-data-service` (public market data; no auth)."""

from collections.abc import AsyncIterator
from typing import Any

from tplus.client.base import BaseClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.klines import KlineUpdate, parse_kline_update
from tplus.model.orderbook import OrderBook, OrderBookDiff
from tplus.model.trades import (
    Trade,
    TradeEvent,
    parse_single_trade,
    parse_trade_event,
    parse_trades,
)


def _pagination(page: int | None, limit: int | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if page:
        params["page"] = page

    if limit:
        params["limit"] = limit

    return params


class MarketDataClient(BaseClient):
    """Klines, order-book depth, public trades and 24h tickers (REST + WS streams)."""

    def __init__(self, base_url: str = "http://localhost:8011", **kwargs: Any) -> None:
        super().__init__(base_url, **kwargs)

    async def get_orderbook_snapshot(self, asset_id: AssetIdentifier) -> OrderBook:
        """Current order-book snapshot for `asset_id`."""
        response = await self._request("GET", f"/marketdepth/{asset_id}", requires_auth=False)
        if not isinstance(response, dict):
            raise ValueError(f"Invalid response for order book snapshot: {response}")

        try:
            return OrderBook(**response)
        except TypeError as err:
            raise ValueError(f"Could not parse order book snapshot: {response}") from err

    async def get_klines(
        self,
        asset_id: AssetIdentifier,
        page: int | None = None,
        limit: int | None = None,
        end_timestamp_ns: int | None = None,
    ) -> list[KlineUpdate]:
        """K-line (candlestick) data for `asset_id`."""
        params = _pagination(page, limit)
        if end_timestamp_ns:
            params["end_timestamp_ns"] = end_timestamp_ns

        response = await self._request(
            "GET", f"/klines/{asset_id}", params=params, requires_auth=False
        )
        if not isinstance(response, list):
            raise ValueError(f"Invalid response from get_klines: {response}")

        return parse_kline_update(response)

    async def get_ticker(self, asset_id: AssetIdentifier) -> dict[str, Any]:
        """24h ticker for `asset_id`."""
        response = await self._request("GET", f"/ticker/{asset_id}", requires_auth=False)
        if not isinstance(response, dict):
            raise ValueError(f"Invalid response from get_ticker: {response}")

        return response

    async def get_tickers(self) -> list[dict[str, Any]]:
        """24h tickers for all markets."""
        response = await self._request("GET", "/tickers", requires_auth=False)
        if not isinstance(response, list):
            raise ValueError(f"Invalid response from get_tickers: {response}")

        return response

    async def get_trades(self, page: int | None = None, limit: int | None = None) -> list[Trade]:
        """Confirmed trades across all markets."""
        response = await self._request(
            "GET", "/trades", params=_pagination(page, limit), requires_auth=False
        )
        if not isinstance(response, list):
            raise ValueError(f"Invalid response from get_trades: {response}")

        return parse_trades(response)

    async def get_trades_for_asset(
        self, asset_id: AssetIdentifier, page: int | None = None, limit: int | None = None
    ) -> list[Trade]:
        """Confirmed trades for `asset_id`."""
        response = await self._request(
            "GET", f"/trades/{asset_id}", params=_pagination(page, limit), requires_auth=False
        )
        if not isinstance(response, list):
            raise ValueError(f"Invalid response from get_trades_for_asset: {response}")

        return parse_trades(response)

    async def stream_finalized_trades(self) -> AsyncIterator[Trade]:
        """Confirmed/finalized trades."""
        async for trade in self._stream_ws("/trades", parse_single_trade, requires_auth=False):
            yield trade

    async def stream_all_trades(self) -> AsyncIterator[TradeEvent]:
        """Every trade event, including pending and rolled-back states."""
        async for event in self._stream_ws(
            "/trades/events", parse_trade_event, requires_auth=False
        ):
            yield event

    async def stream_depth(self, asset_id: AssetIdentifier) -> AsyncIterator[OrderBookDiff]:
        """Order-book diff updates for `asset_id`."""
        path = f"/marketdepth/diff/{asset_id}"
        async for diff in self._stream_ws(path, lambda d: OrderBookDiff(**d), requires_auth=False):
            yield diff

    async def stream_klines(self, asset_id: AssetIdentifier) -> AsyncIterator[KlineUpdate]:
        """Candlestick (kline) updates for `asset_id`."""
        async for kline in self._stream_ws(
            f"/klines/diff/{asset_id}", parse_kline_update, requires_auth=False
        ):
            yield kline
