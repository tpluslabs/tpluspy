# For generating order_ids
import asyncio
import base64
import contextlib
import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any

import httpx

from tplus.client.base import BaseClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.klines import KlineUpdate, parse_kline_update
from tplus.model.limit_order import GTD, GTC, IOC
from tplus.model.market import Market, parse_market
from tplus.model.market_order import (
    MarketBaseQuantity,
    MarketQuoteQuantity,
)
from tplus.model.order import (
    OrderEvent,
    OrderOperationResponse,
    OrderResponse,
    TradeTarget,
    parse_order_event,
    parse_orders,
)
from tplus.model.orderbook import OrderBook, OrderBookDiff
from tplus.model.trades import (
    Trade,
    TradeEvent,
    UserTrade,
    parse_single_trade,
    parse_single_user_trade,
    parse_trade_event,
    parse_trades,
)
from tplus.model.user_solvency import (
    UserSolvency,
    parse_user_solvency,
)
from tplus.utils.limit_order import (
    create_limit_order_ob_request_payload,
)
from tplus.utils.market_order import (
    create_market_order_ob_request_payload,
)
from tplus.utils.replace_order import (
    create_replace_order_ob_request_payload,
)
from tplus.utils.signing import (
    create_cancel_order_ob_request_payload,
)

if TYPE_CHECKING:
    import websockets
    from tplus.utils.user import User


def compute_remaining(order: OrderResponse) -> int:
    # Deprecated: server-side open filtering is now supported; retained for backward compatibility.
    confirmed = int(order.confirmed_filled_quantity or 0)
    pending = int(order.pending_filled_quantity or 0)
    total_qty = int(order.quantity or 0)
    return max(0, total_qty - confirmed - pending)


class OrderBookClient(BaseClient):
    """Client for HTTP + WebSocket interactions with the OMS.

    Extra keyword-arguments for the underlying ``websockets.connect`` call can
    be supplied via *websocket_kwargs*; this lets tests tweak
    ``close_timeout`` (and other knobs) without modifying global defaults.
    """

    def __init__(
        self,
        user: "User",
        *,
        base_url: str,
        websocket_kwargs: dict[str, Any] | None = None,
        log_level: int = logging.INFO,
        use_ws_control: bool = False,
        insecure_ssl: bool = False,
    ) -> None:
        super().__init__(
            user,
            base_url=base_url,
            websocket_kwargs=websocket_kwargs,
            log_level=log_level,
            insecure_ssl=insecure_ssl,
        )
        # Cache Market details per asset to avoid repeated GET /market calls
        self._market_cache: dict[str, Market] = {}
        # When True, create/replace/cancel are sent via WS /control instead of HTTP
        if not isinstance(use_ws_control, bool):
            raise TypeError("use_ws_control must be a bool")
        self._use_ws_control: bool = use_ws_control
        # WS control connection state
        self._control_ws: websockets.WebSocketClientProtocol | None = None
        self._control_ws_task: asyncio.Task | None = None
        self._control_ws_lock: asyncio.Lock = asyncio.Lock()
        self._pending_control: dict[str, asyncio.Future] = {}
        # Optional user callback for control channel state updates
        self._on_control_state: Callable[[str], None] | None = None

    async def create_market(self, asset_id: AssetIdentifier | str) -> dict[str, Any]:
        """
        Create and send a market (async).
        """
        if isinstance(asset_id, str):
            asset_id = AssetIdentifier(asset_id)
        message_dict = {"asset_id": asset_id.model_dump()}
        self.logger.debug(f"Creating Market for Asset {asset_id}")
        return await self._request("POST", "/market/create", json_data=message_dict)

    async def get_market(self, asset_id: AssetIdentifier) -> Market:
        """Get a market (async) with simple per-asset caching."""
        key = str(asset_id)
        if (cached := self._market_cache.get(key)) is not None:
            return cached

        response = await self._request("GET", f"/market/{asset_id}")

        if "asset_id" not in response:
            raise ValueError(f"Invalid market data: {response}")

        market = parse_market(response)
        self._market_cache[key] = market
        return market

    async def create_market_order(
        self,
        side: str,
        base_quantity: int | None = None,
        quote_quantity: int | None = None,
        fill_or_kill: bool = False,
        asset_id: AssetIdentifier | None = None,
        target: TradeTarget | None = None,
    ) -> OrderOperationResponse:
        """
        Create a market order (async). Uses WS /control if enabled.
        """
        # TODO: Fix the signature of this method so that `asset_id` is required.
        asset_id_unwrapped: AssetIdentifier = asset_id  # type: ignore

        order_id = str(base64.b64encode(uuid.uuid4().bytes).decode("ascii"))
        market = await self.get_market(asset_id_unwrapped)
        base_qty_model = (
            MarketBaseQuantity(quantity=base_quantity, max_sellable_amount=None)
            if base_quantity is not None
            else None
        )
        quote_qty_model = (
            MarketQuoteQuantity(quantity=quote_quantity, max_sellable_quantity=None)
            if quote_quantity is not None
            else None
        )

        ob_request_payload = create_market_order_ob_request_payload(
            side=side,
            signer=self.user,
            book_quantity_decimals=market.book_quantity_decimals,
            book_price_decimals=market.book_price_decimals,
            asset_identifier=asset_id_unwrapped,
            order_id=order_id,
            base_quantity=base_qty_model,
            quote_quantity=quote_qty_model,
            fill_or_kill=fill_or_kill,
            target=target,
        )
        self.logger.debug(
            f"Sending Market Order (Asset {asset_id}): BaseQty={base_quantity}, QuoteQty={quote_quantity}, Side={side}, FOK={fill_or_kill}, OrderID={order_id}"
        )
        if self._use_ws_control:
            payload = {"CreateOrderRequest": ob_request_payload.model_dump()}
            ws_resp = await self._control_ws_send(payload, expected_order_id=order_id, timeout=15.0)
            return self._extract_operation_response(ws_resp)
        resp = await self._request(
            "POST", "/orders/create", json_data=ob_request_payload.model_dump()
        )
        return OrderOperationResponse.model_validate(resp)

    async def create_limit_order(
        self,
        quantity: int,
        price: int,
        side: str,
        time_in_force: GTC | GTD | IOC | None = None,
        asset_id: AssetIdentifier | None = None,
        target: TradeTarget | None = None,
    ) -> OrderOperationResponse:
        """
        Create a limit order (async). Uses WS /control if enabled.
        """
        # TODO: Fix the signature if this method such that `asset_id` is required.
        asset_id_unwrapped: AssetIdentifier = asset_id  # type: ignore

        order_id = str(base64.b64encode(uuid.uuid4().bytes).decode("ascii"))
        market = await self.get_market(asset_id_unwrapped)
        signed_message = create_limit_order_ob_request_payload(
            quantity=quantity,
            price=price,
            side=side,
            signer=self.user,
            book_quantity_decimals=market.book_quantity_decimals,
            book_price_decimals=market.book_price_decimals,
            asset_identifier=asset_id_unwrapped,
            order_id=order_id,
            time_in_force=time_in_force,
            target=target,
        )
        self.logger.debug(
            f"Sending Limit Order (Asset {asset_id}): Qty={quantity}, Price={price}, Side={side}, OrderID={order_id}"
        )
        if self._use_ws_control:
            payload = {"CreateOrderRequest": signed_message.model_dump()}
            ws_resp = await self._control_ws_send(payload, expected_order_id=order_id, timeout=15.0)
            return self._extract_operation_response(ws_resp)
        resp = await self._request("POST", "/orders/create", json_data=signed_message.model_dump())
        return OrderOperationResponse.model_validate(resp)

    async def cancel_order(
        self, order_id: str, asset_id: AssetIdentifier
    ) -> OrderOperationResponse:
        """
        Cancel an order (async). Uses WS /control if enabled.
        """
        signed_message = create_cancel_order_ob_request_payload(
            order_id=order_id, asset_identifier=asset_id, signer=self.user
        )
        self.logger.debug(f"Sending Cancel Order Request: OrderID={order_id}, Asset={asset_id}")
        if self._use_ws_control:
            payload = {"CancelOrderRequest": signed_message.model_dump()}
            ws_resp = await self._control_ws_send(payload, expected_order_id=order_id, timeout=10.0)
            return self._extract_operation_response(ws_resp)
        resp = await self._request(
            "DELETE", "/orders/cancel", json_data=signed_message.model_dump()
        )
        return OrderOperationResponse.model_validate(resp)

    async def replace_order(
        self,
        original_order_id: str,
        asset_id: AssetIdentifier,
        new_quantity: int | None = None,
        new_price: int | None = None,
    ) -> OrderOperationResponse:
        """
        Replace an existing order with new parameters (async). Uses WS /control if enabled.
        """
        market = await self.get_market(asset_id)
        signed_message = create_replace_order_ob_request_payload(
            original_order_id=original_order_id,
            asset_identifier=asset_id,
            signer=self.user,
            new_price=new_price,
            new_quantity=new_quantity,
            book_price_decimals=market.book_price_decimals,
            book_quantity_decimals=market.book_quantity_decimals,
        )
        self.logger.debug(
            f"Sending Replace Order for original OrderID {original_order_id} (Asset {asset_id}): "
            f"New Qty={new_quantity}, New Price={new_price}"
        )
        if self._use_ws_control:
            payload = {"ReplaceOrderRequest": signed_message.model_dump(exclude_none=True)}
            ws_resp = await self._control_ws_send(
                payload, expected_order_id=original_order_id, timeout=15.0
            )
            return self._extract_operation_response(ws_resp)
        resp = await self._request(
            "PATCH", "/orders/replace", json_data=signed_message.model_dump(exclude_none=True)
        )
        return OrderOperationResponse.model_validate(resp)

    def parse_trades(self, trades_data: list[dict[str, Any]]) -> list[Trade]:
        """
        Parse trade data into Trade objects.
        """
        return parse_trades(trades_data)

    def parse_user_trades(self, trades_data: list[dict[str, Any]]) -> list[UserTrade]:
        """
        Parse user trade data into UserTrade objects.
        """
        from tplus.model.trades import parse_user_trades

        return parse_user_trades(trades_data)

    async def get_orderbook_snapshot(self, asset_id: AssetIdentifier) -> OrderBook:
        """
        Get a snapshot of the order book for a given asset (async).
        """
        endpoint = f"/marketdepth/{asset_id}"
        self.logger.debug(f"Getting Order Book Snapshot for asset {asset_id}")
        response = await self._request("GET", endpoint)
        if not isinstance(response, dict):
            self.logger.error(
                f"Received non-dictionary response for order book snapshot: {response}"
            )
            raise ValueError(
                f"Invalid API response for order book snapshot: expected a dictionary, got {type(response).__name__}"
            )
        try:
            return OrderBook(**response)
        except TypeError as e:
            self.logger.error(
                f"Failed to parse order book snapshot response dict into OrderBook object: {e}. Response dict: {response}"
            )
            raise ValueError(
                f"Could not parse API response dictionary for order book snapshot: {response}"
            ) from e

    async def get_klines(
        self,
        asset_id: AssetIdentifier,
        page: int | None = None,
        limit: int | None = None,
        end_timestamp_ns: int | None = None,
    ) -> list[KlineUpdate]:
        """
        Get K-line (candlestick) data for a given asset (async).
        """
        endpoint = f"/klines/{asset_id}"
        params_dict = {}
        if page:
            params_dict["page"] = page
        if limit:
            params_dict["limit"] = limit
        if end_timestamp_ns:
            params_dict["end_timestamp_ns"] = end_timestamp_ns

        self.logger.debug(f"Getting Klines for asset {asset_id}")
        response_data = await self._request("GET", endpoint, params=params_dict)

        if not isinstance(response_data, list):
            raise Exception("Invalide response from get_klines.")

        parsed_data = parse_kline_update(response_data)
        return parsed_data

    async def get_user_trades(self) -> list[UserTrade]:
        """
        Get all trades for the authenticated user (async).
        """
        endpoint = f"/trades/user/{self.user.public_key}"
        self.logger.debug(f"Getting Trades for user {self.user.public_key}")
        response_data = await self._request("GET", endpoint)
        return self.parse_user_trades(response_data)  # type: ignore

    async def get_user_trades_for_asset(self, asset_id: AssetIdentifier) -> list[UserTrade]:
        """
        Get trades for a specific asset for the authenticated user (async).
        """
        endpoint = f"/trades/user/{self.user.public_key}/{asset_id}"
        self.logger.debug(f"Getting Trades for user {self.user.public_key}, asset {asset_id}")
        response_data = await self._request("GET", endpoint)
        return self.parse_user_trades(response_data)  # type: ignore

    async def get_user_orders(self) -> tuple[list[OrderResponse], dict[str, Any]]:
        """
        Get all orders for the authenticated user (async).
        """
        endpoint = f"/orders/user/{self.user.public_key}"
        self.logger.debug(f"Getting Orders for user {self.user.public_key}")
        response_data = await self._request("GET", endpoint)

        if isinstance(response_data, dict) and "error" in response_data:
            self.logger.error(
                f"Received error when fetching user orders: {response_data['error']}. Check authentication."
            )
            return [], {}
        if not isinstance(response_data, list):
            self.logger.error(
                f"Unexpected response type when fetching user orders. Expected list, got {type(response_data).__name__}. Data: {response_data}"
            )
            return [], {}

        parsed_orders = parse_orders(response_data)
        return parsed_orders, response_data

    async def get_user_orders_for_book(
        self,
        asset_id: AssetIdentifier,
        *,
        page: int | None = None,
        limit: int | None = None,
        open_only: bool | None = None,
    ) -> list[OrderResponse]:
        """
        Get orders for a specific asset for the authenticated user (async).
        Handles 404 with empty list as "no orders" gracefully.
        """
        endpoint = f"/orders/user/{self.user.public_key}/{asset_id}"
        params_dict: dict[str, Any] | None = None
        if page is not None or limit is not None or open_only is not None:
            params_dict = {
                "page": 0 if page is None else int(page),
                "limit": 1000 if limit is None else int(limit),
            }
            if open_only is not None:
                params_dict["open_only"] = bool(open_only)
        self.logger.debug(f"Getting Orders for user {self.user.public_key}, asset {asset_id}")
        try:
            response_data = await self._request("GET", endpoint, params=params_dict)

            if isinstance(response_data, dict) and "error" in response_data:
                self.logger.error(
                    f"Received error when fetching orders for book {asset_id}: {response_data['error']}"
                )
                return []
            if not isinstance(response_data, list):
                self.logger.error(
                    f"Unexpected response type for book orders {asset_id}. Expected list, got {type(response_data).__name__}."
                )
                return []

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404 and e.request.url.path == endpoint:
                try:
                    content = e.response.json()
                    if isinstance(content, list) and not content:
                        self.logger.debug(
                            f"Received 404 with empty list for {endpoint} (User: {self.user.public_key}, Asset: {asset_id}). "
                            f"This is expected if the user has no orders for this asset yet. Treating as success with no orders."
                        )
                        return []
                    else:
                        self.logger.warning(
                            f"Received 404 for {endpoint} (User: {self.user.public_key}, Asset: {asset_id}), "
                            f"but response body was not an empty list as expected for 'no orders'. Body: {e.response.text[:200]}"
                        )
                except json.JSONDecodeError:
                    self.logger.warning(
                        f"Received 404 for {endpoint} (User: {self.user.public_key}, Asset: {asset_id}), "
                        f"but response body was not valid JSON. Body: {e.response.text[:200]}"
                    )
            raise e

        parsed_orders = parse_orders(response_data)
        return parsed_orders

    async def get_open_orders_for_book(
        self, asset_id: AssetIdentifier, *, limit: int = 1000, max_pages: int = 50
    ) -> list[OrderResponse]:
        """Return open orders directly from server (source of truth)."""
        page = 0
        open_orders: list[OrderResponse] = []
        while page < max_pages:
            parsed = await self.get_user_orders_for_book(
                asset_id, page=page, limit=limit, open_only=True
            )
            open_orders.extend(parsed)
            if len(parsed) < limit:
                break
            page += 1
        return open_orders

    # ------------------------------------------------------------------
    # Optional persistent WebSocket control channel for create/replace/cancel
    # ------------------------------------------------------------------
    async def _ensure_control_ws(self) -> None:
        if not self._use_ws_control:
            return
        if self._control_ws and not getattr(self._control_ws, "closed", False):
            return
        async with self._control_ws_lock:
            if self._control_ws and not getattr(self._control_ws, "closed", False):
                return
            attempt = 0
            delay = 0.5
            while True:
                try:
                    websocket_cm = await self._open_ws("/control")
                    self._control_ws = await websocket_cm.__aenter__()  # type: ignore[attr-defined]
                    callback = self._on_control_state
                    if callback is not None:
                        try:
                            callback("connected")
                        except Exception:
                            pass
                    self._control_ws_task = asyncio.create_task(self._control_ws_reader())
                    break
                except Exception:
                    attempt += 1
                    if attempt >= 5:
                        raise
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 5.0)

    async def _control_ws_reader(self) -> None:
        try:
            ws = self._control_ws
            if ws is None:
                return
            async for message in ws:
                try:
                    data = json.loads(message)
                    if isinstance(data, dict) and data.get("type") in {
                        "subscriptions",
                        "ping",
                        "pong",
                    }:
                        continue
                    key_parts = self._control_response_order_id(data)
                    if key_parts is None:
                        continue
                    variant, asset_id, order_id = key_parts
                    composite_key = f"{variant}:{asset_id}:{order_id}"
                    fut = self._pending_control.pop(composite_key, None)
                    if fut and not fut.done():
                        fut.set_result(data)
                except Exception as e:
                    # Ignore malformed messages; futures will timeout
                    self.logger.debug(f"Control WS reader parse error: {e}")
        except Exception as e:
            # Fail all pending futures on connection drop
            for _, fut in list(self._pending_control.items()):
                if not fut.done():
                    fut.set_exception(e)
            self._pending_control.clear()
        finally:
            try:
                if self._control_ws and not getattr(self._control_ws, "closed", False):
                    await self._control_ws.close()
            except Exception:
                pass
            self._control_ws = None
            self._control_ws_task = None
            callback = self._on_control_state
            if callback is not None:
                try:
                    callback("disconnected")
                except Exception:
                    pass

    def _control_response_order_id(self, data: dict[str, Any]) -> tuple[str, str, str] | None:
        if not isinstance(data, dict) or len(data) != 1:
            return None
        variant, content = next(iter(data.items()))
        if not isinstance(content, dict):
            return None
        response = content.get("response")
        if not isinstance(response, dict):
            return None
        oid = response.get("order_id")
        asset_id = (
            data.get("asset_id")
            if isinstance(data.get("asset_id"), str)
            else content.get("asset_id")
        )
        if oid is None or asset_id is None:
            return None
        return str(variant), str(asset_id), str(oid)

    async def _control_ws_send(
        self, payload: dict[str, Any], *, expected_order_id: str, timeout: float = 5.0
    ) -> dict[str, Any]:
        await self._ensure_control_ws()
        # If connection couldn't be established, fallback
        if not self._control_ws:
            raise RuntimeError("WS control not connected")
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        # Determine expected response variant and asset_id from payload to build key
        if len(payload) != 1:
            raise ValueError("Invalid WS control payload shape")
        request_variant, content = next(iter(payload.items()))
        # Map request variant to response variant names sent by server
        response_variant_map = {
            "CreateOrderRequest": "CreateOrderResponse",
            "CancelOrderRequest": "CancelOrderResponse",
            "ReplaceOrderRequest": "ReplaceOrderResponse",
        }
        response_variant = response_variant_map.get(request_variant, request_variant)
        asset_id: str | None = None
        if isinstance(content, dict):
            if isinstance(content.get("asset_id"), str):
                asset_id = content["asset_id"]
            elif isinstance(content.get("cancel"), dict) and isinstance(
                content["cancel"].get("asset_id"), str
            ):
                asset_id = content["cancel"]["asset_id"]
            elif isinstance(content.get("order"), dict) and isinstance(
                content["order"].get("base_asset"), str
            ):
                asset_id = content["order"]["base_asset"]
        if asset_id is None:
            raise ValueError("WS control payload missing asset_id")
        key = f"{response_variant}:{asset_id}:{expected_order_id}"
        self._pending_control[key] = fut
        await self._control_ws.send(json.dumps(payload))
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            # Ensure cleanup if timed out
            self._pending_control.pop(key, None)

    def _extract_operation_response(self, data: dict[str, Any]) -> OrderOperationResponse:
        if not isinstance(data, dict) or len(data) != 1:
            raise ValueError(f"Unexpected WS control response shape: {data}")
        variant, content = next(iter(data.items()))
        if not isinstance(content, dict):
            raise ValueError(f"Unexpected WS control response content: {content}")
        response = content.get("response")
        if not isinstance(response, dict):
            raise ValueError(f"Missing 'response' in WS control payload: {content}")
        return OrderOperationResponse.model_validate(response)

    async def close(self) -> None:
        # Close control WS first
        try:
            if self._control_ws_task:
                self._control_ws_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await self._control_ws_task
            if self._control_ws and not getattr(self._control_ws, "closed", False):
                with contextlib.suppress(Exception):
                    await self._control_ws.close()
        finally:
            self._control_ws = None
            self._control_ws_task = None
        await super().close()

    async def get_user_inventory(self) -> dict[str, Any]:
        """
        Get inventory for the authenticated user (async).
        """
        endpoint = f"/inventory/user/{self.user.public_key}"
        self.logger.debug(f"Getting Inventory for user {self.user.public_key}")
        return await self._request("GET", endpoint)

    async def stream_orders(self) -> AsyncIterator[OrderEvent]:
        """
        Stream all order events (creations, updates, cancellations).
        """
        async for event in self._stream_ws("/orders", parse_order_event):
            yield event

    async def stream_finalized_trades(self) -> AsyncIterator[Trade]:
        """
        Stream only confirmed/finalized trades.
        """
        async for trade in self._stream_ws("/trades", parse_single_trade):
            yield trade

    async def stream_all_trades(self) -> AsyncIterator[TradeEvent]:
        """
        Stream all trade events (e.g., Pending, Confirmed).
        """
        async for event in self._stream_ws("/trades/events", parse_trade_event):
            yield event

    async def stream_depth(self, asset_id: AssetIdentifier) -> AsyncIterator[OrderBookDiff]:
        """
        Stream order book diff updates for a specific asset.
        """
        path = f"/marketdepth/diff/{asset_id}"
        async for diff in self._stream_ws(path, lambda d: OrderBookDiff(**d)):
            yield diff

    async def stream_klines(self, asset_id: AssetIdentifier) -> AsyncIterator[KlineUpdate]:
        """
        Stream K-line (candlestick) updates for a specific asset.
        """
        path = f"/klines/diff/{asset_id}"
        async for kline in self._stream_ws(path, parse_kline_update):
            yield kline

    async def stream_user_trade_events(
        self, user_id: str | None = None
    ) -> AsyncIterator[UserTrade]:
        """
        Stream **all** trade events (``Pending``, ``Confirmed``, ``Rollbacked``) for a specific user.

        Args:
            user_id: Optional explicit user identifier.  If not provided, the authenticated user's
                public key is used.
        Yields:
            :class:`tplus.model.trades.UserTrade` objects with detailed order-side information.
        """
        if user_id is None:
            user_id = self.user.public_key
        path = f"/trades/user/events/{user_id}"
        async for trade in self._stream_ws(path, parse_single_user_trade):
            yield trade

    async def stream_user_finalized_trades(
        self, user_id: str | None = None
    ) -> AsyncIterator[UserTrade]:
        """
        Stream **finalized** (confirmed) trades for a specific user.

        Args:
            user_id: Optional explicit user identifier.  If not provided, the authenticated user's
                public key is used.
        Yields:
            :class:`tplus.model.trades.UserTrade` instances containing only confirmed trades.
        """
        if user_id is None:
            user_id = self.user.public_key
        path = f"/trades/user/{user_id}"
        async for trade in self._stream_ws(path, parse_single_user_trade):
            yield trade

    async def stream_user_trades(self, user_id: str | None = None) -> AsyncIterator[UserTrade]:
        """
        [DEPRECATED] Use stream_user_trade_events or stream_user_finalized_trades instead.
        This method streams finalized (confirmed) trades for a specific user.
        """
        async for trade in self.stream_user_finalized_trades(user_id=user_id):
            yield trade


    async def get_user_solvency(self) -> UserSolvency:
        """
        Get solvency for the authenticated user (async).
        """
        endpoint = f"/solvency/user/{self.user.public_key}"

        self.logger.debug(f"Getting Solvency for user {self.user.public_key}")
        response_data = await self._request("GET", endpoint)

        if not isinstance(response_data, dict):
            raise Exception("Invalid response from get_user_solvency.")

        parsed__data:UserSolvency = parse_user_solvency(response_data)
        return parsed__data
