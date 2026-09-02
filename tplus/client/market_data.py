"""Client for the `market-data-service` (public market data + per-user endpoints)."""

import time
from collections.abc import AsyncIterator
from typing import Any

from tplus.client.auth import AuthenticatedClient
from tplus.client.base import page_params
from tplus.exceptions import NotFoundError
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.klines import (
    Interval,
    KlinesPage,
    Timebar,
    parse_klines_page,
    parse_timebars,
)
from tplus.model.open_interest import OpenInterest, parse_open_interest
from tplus.model.order import UserOrdersPage, parse_user_orders_page
from tplus.model.orderbook import OrderBook, OrderBookDiff
from tplus.model.position_basis import PositionBasisResponse, parse_position_basis
from tplus.model.sub_account import SubAccountNamesResponse
from tplus.model.ticker import Ticker, parse_tickers
from tplus.model.trades import (
    Trade,
    TradeEvent,
    UserTradesPage,
    parse_single_trade,
    parse_trade_event,
    parse_trades,
    parse_user_trades_page,
)
from tplus.types import UserType

DEFAULT_BASE_URL = "http://localhost:8011"
DEFAULT_MAX_KLINE_PAGES = 50


class MarketDataClient(AuthenticatedClient):
    """Klines, order-book depth, public trades and 24h tickers (REST + WS streams).

    Public endpoints are anonymous; per-user trade history authenticates against
    MDS itself (its own nonce/token handshake, separate from the OMS token).
    """

    def __init__(self, base_url: str = DEFAULT_BASE_URL, **kwargs: Any) -> None:
        super().__init__(base_url, **kwargs)

    async def get_orderbook_snapshot(self, asset_id: AssetIdentifier) -> OrderBook:
        """Current order-book snapshot for `asset_id`."""
        response = await self._get(f"/marketdepth/{asset_id}", requires_auth=False)
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
        interval: Interval | str | None = None,
    ) -> KlinesPage:
        """A page of k-line (candlestick) data for `asset_id`, with pagination metadata.

        `interval` asks for wider candlesticks, e.g. `Interval.HOUR_4`. A raw string is
        passed through, so the suffixed forms (`4h`, `1d`) also work.
        """
        params = page_params(
            page,
            limit,
            end_timestamp_ns=end_timestamp_ns,
            interval=str(interval) if interval is not None else None,
        )
        response = await self._get(f"/klines/{asset_id}", params=params, requires_auth=False)
        if not isinstance(response, dict | list):
            raise ValueError(f"Invalid response from get_klines: {response}")

        return parse_klines_page(response)

    async def iter_klines(
        self,
        asset_id: AssetIdentifier,
        limit: int | None = None,
        end_timestamp_ns: int | None = None,
        interval: Interval | str | None = None,
        max_pages: int | None = DEFAULT_MAX_KLINE_PAGES,
    ) -> AsyncIterator[Timebar]:
        """Every candlestick for `asset_id`, newest first; pins `end_timestamp_ns` so pages cannot slide.

        `max_pages` bounds reads taken, not history reached: a clamped window resumes at its cutoff.
        `None` lifts the bound and walks the asset's whole history.
        """
        end_timestamp_ns = end_timestamp_ns if end_timestamp_ns is not None else time.time_ns()
        page = 0
        reads = 0
        while max_pages is None or reads < max_pages:
            result = await self.get_klines(
                asset_id,
                page=page,
                limit=limit,
                end_timestamp_ns=end_timestamp_ns,
                interval=interval,
            )
            reads += 1
            for timebar in result.items:
                yield timebar

            if result.has_next_page:
                page += 1
                continue

            # The clamped end of a window too wide to read whole; the rest is older still.
            cutoff = result.truncated_before_ns
            if cutoff is None or cutoff > end_timestamp_ns or cutoff == 0:
                return

            end_timestamp_ns = cutoff - 1
            page = 0

    async def get_ticker(self, asset_id: AssetIdentifier) -> Ticker:
        """24h ticker for `asset_id`."""
        response = await self._get(f"/ticker/{asset_id}", requires_auth=False)
        return Ticker.model_validate(response)

    async def get_tickers(self) -> list[Ticker]:
        """24h tickers for all markets."""
        response = await self._get("/tickers", requires_auth=False)
        if not isinstance(response, list):
            raise ValueError(f"Invalid response from get_tickers: {response}")

        return parse_tickers(response)

    async def get_open_interest(self, asset_id: AssetIdentifier) -> OpenInterest:
        """Open interest for `asset_id`, `None` until the market first reports it."""
        response = await self._get(f"/openinterest/{asset_id}", requires_auth=False)
        return OpenInterest.model_validate(response)

    async def get_all_open_interest(self) -> list[OpenInterest]:
        """Open interest for every market, one row per listed market."""
        response = await self._get("/openinterest", requires_auth=False)
        if not isinstance(response, list):
            raise ValueError(f"Invalid response from get_all_open_interest: {response}")

        return parse_open_interest(response)

    async def get_trades(self, page: int | None = None, limit: int | None = None) -> list[Trade]:
        """Confirmed trades across all markets."""
        response = await self._get("/trades", params=page_params(page, limit), requires_auth=False)
        if not isinstance(response, list):
            raise ValueError(f"Invalid response from get_trades: {response}")

        return parse_trades(response)

    async def get_trades_for_asset(
        self, asset_id: AssetIdentifier, page: int | None = None, limit: int | None = None
    ) -> list[Trade]:
        """Confirmed trades for `asset_id`."""
        response = await self._get(
            f"/trades/{asset_id}", params=page_params(page, limit), requires_auth=False
        )
        if not isinstance(response, list):
            raise ValueError(f"Invalid response from get_trades_for_asset: {response}")

        return parse_trades(response)

    async def get_user_trades(
        self,
        user: UserType | None = None,
        *,
        page: int | None = None,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        side: str | None = None,
        sub_account: int | None = None,
        status: str | None = None,
    ) -> UserTradesPage:
        """
        Trades for `user`, newest first; empty unless the user's data is exported to MDS.

        `start_time`/`end_time` are inclusive nanosecond Unix timestamps; `side` is
        `"buy"` or `"sell"`, matching the caller's role in the fill.
        """
        return await self._get_user_trades(
            user=user,
            page=page,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            side=side,
            sub_account=sub_account,
            status=status,
        )

    async def get_user_trades_for_asset(
        self,
        asset_id: AssetIdentifier,
        user: UserType | None = None,
        *,
        page: int | None = None,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        side: str | None = None,
        sub_account: int | None = None,
        status: str | None = None,
    ) -> UserTradesPage:
        """
        Trades for `user` on `asset_id`, newest first.

        `start_time`/`end_time` are inclusive nanosecond Unix timestamps; `side` is
        `"buy"` or `"sell"`, matching the caller's role in the fill.
        """
        return await self._get_user_trades(
            asset_id=asset_id,
            user=user,
            page=page,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            side=side,
            sub_account=sub_account,
            status=status,
        )

    async def _get_user_trades(
        self,
        *,
        asset_id: AssetIdentifier | None = None,
        page: int | None = None,
        limit: int | None = None,
        sub_account: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        side: str | None = None,
        status: str | None = None,
        user: UserType | None = None,
    ) -> UserTradesPage:
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/trades/user/{public_key}"
        if asset_id is not None:
            endpoint = f"{endpoint}/{asset_id}"

        params = page_params(
            page,
            limit,
            sub_account=sub_account,
            start_time=start_time,
            end_time=end_time,
            side=side,
            status=status,
        )
        try:
            data = await self._get(endpoint, params=params, requires_auth=True, user=user)
        except NotFoundError:
            return parse_user_trades_page([])

        return parse_user_trades_page(data)

    async def get_user_orders(
        self,
        user: UserType | None = None,
        *,
        page: int | None = None,
        limit: int | None = None,
        sub_account: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        side: str | None = None,
        status: str | None = None,
    ) -> UserOrdersPage:
        """
        Orders for `user`, newest first; empty unless the user's data is exported to MDS.

        `start_time`/`end_time` are inclusive nanosecond Unix timestamps; `side` is
        `"buy"` or `"sell"`; `status` is one of `pending`, `open`, `partial`, `cancelled`, `closed`,
        `completed`. All are case-insensitive.
        """
        return await self._get_user_orders(
            user=user,
            page=page,
            limit=limit,
            sub_account=sub_account,
            start_time=start_time,
            end_time=end_time,
            side=side,
            status=status,
        )

    async def get_user_orders_for_asset(
        self,
        asset_id: AssetIdentifier,
        user: UserType | None = None,
        *,
        page: int | None = None,
        limit: int | None = None,
        sub_account: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        side: str | None = None,
        status: str | None = None,
    ) -> UserOrdersPage:
        """
        Orders for `user` on `asset_id`, newest first.

        `start_time`/`end_time` are inclusive nanosecond Unix timestamps; `side` is
        `"buy"` or `"sell"`; `status` is one of `pending`, `open`, `partial`, `cancelled`, `closed`,
        `completed`. All are case-insensitive.
        """
        return await self._get_user_orders(
            asset_id=asset_id,
            user=user,
            page=page,
            limit=limit,
            sub_account=sub_account,
            start_time=start_time,
            end_time=end_time,
            side=side,
            status=status,
        )

    async def _get_user_orders(
        self,
        *,
        asset_id: AssetIdentifier | None = None,
        page: int | None = None,
        limit: int | None = None,
        sub_account: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        side: str | None = None,
        status: str | None = None,
        user: UserType | None = None,
    ) -> UserOrdersPage:
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/orders/user/{public_key}"
        if asset_id is not None:
            endpoint = f"{endpoint}/{asset_id}"

        params = page_params(
            page,
            limit,
            sub_account=sub_account,
            start_time=start_time,
            end_time=end_time,
            side=side,
            status=status,
        )
        try:
            data = await self._get(endpoint, params=params, requires_auth=True, user=user)
        except NotFoundError:
            return parse_user_orders_page([])

        return parse_user_orders_page(data)

    async def get_user_position_basis(
        self,
        user: UserType | None = None,
        *,
        sub_account: int | None = None,
    ) -> list[PositionBasisResponse]:
        """Trade-derived position-basis estimates for `user`.

        This is not authoritative inventory state: non-trade flows, fees, and
        both self-trade legs are not preserved by the current MDS history.
        """
        return await self._get_user_position_basis(user=user, sub_account=sub_account)

    async def get_user_position_basis_for_asset(
        self,
        asset_id: AssetIdentifier,
        user: UserType | None = None,
        *,
        sub_account: int | None = None,
    ) -> list[PositionBasisResponse]:
        """Trade-derived position-basis estimates for `user` on `asset_id`.

        This has the same coverage limitations as :meth:`get_user_position_basis`.
        """
        return await self._get_user_position_basis(
            asset_id=asset_id,
            user=user,
            sub_account=sub_account,
        )

    async def _get_user_position_basis(
        self,
        *,
        asset_id: AssetIdentifier | None = None,
        sub_account: int | None = None,
        user: UserType | None = None,
    ) -> list[PositionBasisResponse]:
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/positions/user/{public_key}/basis"
        if asset_id is not None:
            endpoint = f"{endpoint}/{asset_id}"

        try:
            data = await self._get(
                endpoint,
                params=page_params(None, None, sub_account=sub_account),
                requires_auth=True,
                user=user,
            )
        except NotFoundError:
            return []

        if not isinstance(data, list):
            raise ValueError(f"Invalid response from get_user_position_basis: {data}")

        return parse_position_basis(data)

    async def get_sub_account_names(self, user: UserType | None = None) -> SubAccountNamesResponse:
        """Names `user` gave their sub-accounts, lowest index first.

        Unnamed sub-accounts are absent, as is every sub-account of a user who has
        opted out of market-data export. Names are set on the OMS and reach MDS
        shortly after, so a name read back immediately may still be the previous one.
        """
        public_key = self._validate_user_public_key(user=user)
        data = await self._get(f"/sub-accounts/user/{public_key}", requires_auth=True, user=user)
        return SubAccountNamesResponse.model_validate(data)

    async def clear_db(self) -> None:
        """Wipe the persistence store. Test/debug only (`debug-admin-endpoint` feature);
        raises `ServerError` (503) until the store has connected."""
        await self._post("/debug/clear-db", requires_auth=False)

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

    async def stream_klines(self, asset_id: AssetIdentifier) -> AsyncIterator[Timebar]:
        """Candlestick (kline) updates for `asset_id`."""
        async for kline in self._stream_ws(
            f"/klines/diff/{asset_id}", parse_timebars, requires_auth=False
        ):
            yield kline
