"""Client for the `market-data-service` (public market data + per-user endpoints)."""

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from tplus.client.base import BaseClient
from tplus.model.asset_identifier import AssetIdentifier

if TYPE_CHECKING:
    from tplus.client.auth import AuthenticatedClient
    from tplus.types import UserType
from tplus.model.klines import KlinesPage, KlineUpdate, parse_kline_update, parse_klines_page
from tplus.model.orderbook import OrderBook, OrderBookDiff
from tplus.model.trades import (
    Trade,
    TradeEvent,
    parse_single_trade,
    parse_trade_event,
    parse_trades,
)

DEFAULT_BASE_URL = "http://localhost:8011"


def _pagination(page: int | None, limit: int | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if page:
        params["page"] = page

    if limit:
        params["limit"] = limit

    return params


class MarketDataClient(BaseClient):
    """Klines, order-book depth, public trades and 24h tickers (REST + WS streams)."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        auth_client: "AuthenticatedClient | None" = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(base_url, **kwargs)
        # Per-user endpoints borrow the OMS bearer token from this client.
        self._auth_client = auth_client

    async def _authed_get(
        self,
        endpoint: str,
        *,
        user: "UserType | None" = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """GET an MDS endpoint with the OMS bearer token attached."""
        if self._auth_client is None:
            raise ValueError("per-user market-data endpoints require an `auth_client`")

        signer = user if not isinstance(user, str) else None
        await self._auth_client._ensure_auth(user=signer)
        headers = self._auth_client._get_auth_headers(user=user)
        response = await self._send("GET", endpoint, params=params, headers=headers)
        return self._handle_response(response)

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
    ) -> KlinesPage:
        """A page of k-line (candlestick) data for `asset_id`, with pagination metadata."""
        params = _pagination(page, limit)
        if end_timestamp_ns:
            params["end_timestamp_ns"] = end_timestamp_ns

        response = await self._request(
            "GET", f"/klines/{asset_id}", params=params, requires_auth=False
        )
        if not isinstance(response, dict | list):
            raise ValueError(f"Invalid response from get_klines: {response}")

        return parse_klines_page(response)

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
