# For generating order_ids
import asyncio
import base64
import contextlib
import json
import uuid
from collections.abc import AsyncIterator, Callable
from functools import cached_property
from typing import TYPE_CHECKING, Any

import httpx

from tplus.client.auth import AuthenticatedClient
from tplus.client.oms.assetregistry import AssetRegistryClient
from tplus.exceptions import NotFoundError
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.batch_order import BatchCreateOrderRequest, parse_batch_order_response
from tplus.model.close_all_positions_preview import (
    CloseAllPreviewResponse,
    parse_close_all_preview,
)
from tplus.model.limit_order import GTC, GTD, IOC
from tplus.model.market import Market, parse_market
from tplus.model.market_order import (
    MarketBaseQuantity,
    MarketQuoteQuantity,
)
from tplus.model.order import (
    CreateOrderRequest,
    OrderEvent,
    OrderOperationResponse,
    OrderResponse,
    TradeTarget,
    parse_order_event,
    parse_orders,
)
from tplus.model.order_trigger import OrderTrigger
from tplus.model.position import (
    PositionResponse,
    UserPositionsPage,
    parse_positions_page,
)
from tplus.model.settlement import TxSettlementRequest
from tplus.model.trades import (
    UserTrade,
    UserTradesPage,
    parse_single_user_trade,
    parse_user_trades,
    parse_user_trades_page,
)
from tplus.model.user_event import UserActivityEvent, parse_user_event
from tplus.model.user_margin import (
    UserMarginInfo,
    parse_user_margin_info,
)
from tplus.model.user_solvency import (
    UserSolvency,
    parse_user_solvency,
)
from tplus.types import UserType
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


def _page_params(page: int | None, limit: int | None, **extra: Any) -> dict[str, Any] | None:
    params: dict[str, Any] = {k: v for k, v in extra.items() if v is not None}
    if page is not None:
        params["page"] = int(page)
    if limit is not None:
        params["limit"] = int(limit)
    return params or None


class OrderBookClient(AuthenticatedClient):
    """Client for HTTP + WebSocket interactions with the OMS.

    Extra keyword-arguments for the underlying ``websockets.connect`` call can
    be supplied via *websocket_kwargs*; this lets tests tweak
    ``close_timeout`` (and other knobs) without modifying global defaults.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:3032",
        *,
        use_ws_control: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(base_url, **kwargs)
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

    @cached_property
    def assets(self) -> AssetRegistryClient:
        """
        Public registry snapshot APIs served by OMS.
        """
        return AssetRegistryClient.from_client(self)

    async def create_market(self, asset_id: AssetIdentifier | str) -> dict[str, Any]:
        """Create a market for ``asset_id``.

        The endpoint is idempotent -- calling it for an already-existing
        market simply returns the current configuration.

        Args:
            asset_id: Asset to create the market for. Strings are coerced
                to :class:`AssetIdentifier`.

        Returns:
            The OMS response describing the (possibly pre-existing) market.
        """
        if isinstance(asset_id, str):
            asset_id = AssetIdentifier(asset_id)
        message_dict = {"asset_id": asset_id.model_dump()}
        self.logger.debug(f"Creating Market for Asset {asset_id}")
        return await self._request(
            "POST", "/market/create", json_data=message_dict, requires_auth=False
        )

    async def get_market(self, asset_id: AssetIdentifier) -> Market:
        """Fetch a market description with simple per-asset caching.

        Args:
            asset_id: Asset whose market to fetch.

        Returns:
            The :class:`Market` describing the book's price/quantity decimals.

        Raises:
            ValueError: If the OMS response is missing required fields.
        """
        key = str(asset_id)
        if (cached := self._market_cache.get(key)) is not None:
            return cached

        response = await self._request("GET", f"/market/{asset_id}", requires_auth=False)

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
        order_id: str | None = None,
        target: TradeTarget | None = None,
        max_trading_fees_rate: int | None = None,
        trigger: OrderTrigger | None = None,
        max_sellable_amount: int | None = None,
        max_sellable_quantity: int | None = None,
        user: "User | None" = None,
    ) -> OrderOperationResponse:
        """Create a market order.

        Either ``base_quantity`` or ``quote_quantity`` should be supplied
        (not both). Quantities are integers in the book's native units.

        Args:
            side: ``"Buy"`` or ``"Sell"``.
            base_quantity: Quantity expressed in base-asset units.
            quote_quantity: Quantity expressed in quote-asset units.
            fill_or_kill: If True, the entire order must fill or be cancelled.
            asset_id: Asset to trade.
            order_id: Optional caller-supplied order id. When omitted, tpluspy
                preserves its legacy generated id behavior.
            target: Optional sub-account / collateral target for the trade.
            max_trading_fees_rate: Optional maximum trading fee rate the
                caller is willing to pay (basis points; book-specific).
            trigger: Optional :class:`OrderTrigger` for conditional activation.
            max_sellable_amount: Slippage cap on quote spent. Pairs with
                ``base_quantity``.
            max_sellable_quantity: Slippage cap on base sold. Pairs with
                ``quote_quantity``.
        Returns:
            The :class:`OrderOperationResponse` from the OMS.

        Note:
            When ``use_ws_control=True`` was passed to the constructor, the
            request is sent over a persistent ``/control`` WebSocket; otherwise
            it is sent as ``POST /orders/create``.
        """
        user = self._resolve_user(user=user)
        # TODO: Fix the signature of this method so that `asset_id` is required.
        asset_id_unwrapped: AssetIdentifier = asset_id  # type: ignore

        if max_sellable_amount is not None and base_quantity is None:
            raise ValueError("max_sellable_amount requires base_quantity")
        if max_sellable_quantity is not None and quote_quantity is None:
            raise ValueError("max_sellable_quantity requires quote_quantity")

        order_id = order_id or str(base64.b64encode(uuid.uuid4().bytes).decode("ascii"))
        market = await self.get_market(asset_id_unwrapped)
        base_qty_model = (
            MarketBaseQuantity(quantity=base_quantity, max_sellable_amount=max_sellable_amount)
            if base_quantity is not None
            else None
        )
        quote_qty_model = (
            MarketQuoteQuantity(
                quantity=quote_quantity, max_sellable_quantity=max_sellable_quantity
            )
            if quote_quantity is not None
            else None
        )

        ob_request_payload = create_market_order_ob_request_payload(
            side=side,
            signer=user,
            book_quantity_decimals=market.book_quantity_decimals,
            book_price_decimals=market.book_price_decimals,
            asset_identifier=asset_id_unwrapped,
            order_id=order_id,
            base_quantity=base_qty_model,
            quote_quantity=quote_qty_model,
            fill_or_kill=fill_or_kill,
            trigger=trigger,
            target=target,
            max_trading_fees_rate=max_trading_fees_rate,
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
        order_id: str | None = None,
        target: TradeTarget | None = None,
        max_trading_fees_rate: int | None = None,
        trigger: OrderTrigger | None = None,
        user: "User | None" = None,
    ) -> OrderOperationResponse:
        """Create a limit order.

        Args:
            quantity: Order quantity in the book's base-asset units.
            price: Limit price in the book's quote-asset units.
            side: ``"Buy"`` or ``"Sell"``.
            time_in_force: One of :class:`GTC`, :class:`IOC`, or :class:`GTD`.
                Defaults to GTC if omitted.
            asset_id: Asset to trade.
            order_id: Optional caller-supplied order id. When omitted, tpluspy
                preserves its legacy generated id behavior.
            target: Optional sub-account / collateral target for the trade.
            max_trading_fees_rate: Optional maximum trading fee rate the
                caller is willing to pay.
            trigger: Optional :class:`OrderTrigger` for conditional activation.
        Returns:
            The :class:`OrderOperationResponse` from the OMS.

        Note:
            When ``use_ws_control=True`` was passed to the constructor, the
            request is sent over a persistent ``/control`` WebSocket; otherwise
            it is sent as ``POST /orders/create``.
        """
        user = self._resolve_user(user=user)
        # TODO: Fix the signature if this method such that `asset_id` is required.
        order_id, signed_message = await self.prepare_limit_order_request(
            asset_id,
            price,
            quantity,
            side,
            target,
            time_in_force,
            order_id=order_id,
            max_trading_fees_rate=max_trading_fees_rate,
            trigger=trigger,
            user=user,
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

    async def prepare_limit_order_request(
        self,
        asset_id,
        price,
        quantity,
        side,
        target,
        time_in_force,
        max_trading_fees_rate: int | None = None,
        trigger: OrderTrigger | None = None,
        order_id: str | None = None,
        user: "User | None" = None,
    ):
        user = self._resolve_user(user=user)
        asset_id_unwrapped: AssetIdentifier = asset_id  # type: ignore
        order_id = order_id or str(base64.b64encode(uuid.uuid4().bytes).decode("ascii"))
        market = await self.get_market(asset_id_unwrapped)
        signed_message = create_limit_order_ob_request_payload(
            quantity=quantity,
            price=price,
            side=side,
            signer=user,
            book_quantity_decimals=market.book_quantity_decimals,
            book_price_decimals=market.book_price_decimals,
            asset_identifier=asset_id_unwrapped,
            order_id=order_id,
            time_in_force=time_in_force,
            target=target,
            max_trading_fees_rate=max_trading_fees_rate,
            trigger=trigger,
        )
        return order_id, signed_message

    async def send_multiple_orders(self, create_order_requests: list[CreateOrderRequest]):
        request = BatchCreateOrderRequest(orders=create_order_requests)
        batch_order_response_data = await self._request(
            "POST", "/orders/batch-create", json_data=request.model_dump()
        )
        parsed_batch_order_response = parse_batch_order_response(batch_order_response_data)
        return parsed_batch_order_response

    async def cancel_order(
        self, order_id: str, asset_id: AssetIdentifier, user: "User | None" = None
    ) -> OrderOperationResponse:
        """Cancel a previously submitted order.

        Args:
            order_id: ID returned by the original create call.
            asset_id: Asset the order belongs to.

        Returns:
            The :class:`OrderOperationResponse` from the OMS.
        """
        user = self._resolve_user(user=user)
        signed_message = create_cancel_order_ob_request_payload(
            order_id=order_id, asset_identifier=asset_id, signer=user
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
        user: "User | None" = None,
    ) -> OrderOperationResponse:
        """Replace an existing open order with new parameters.

        Args:
            original_order_id: ID of the order to replace. Must still be open.
            asset_id: Asset the order belongs to.
            new_quantity: New quantity in base-asset units. Optional.
            new_price: New limit price in quote-asset units. Optional.

        Returns:
            The :class:`OrderOperationResponse` from the OMS.
        """
        user = self._resolve_user(user=user)
        market = await self.get_market(asset_id)
        signed_message = create_replace_order_ob_request_payload(
            original_order_id=original_order_id,
            asset_identifier=asset_id,
            signer=user,
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

    def parse_user_trades(self, trades_data: list[dict[str, Any]]) -> list[UserTrade]:
        """Parse user trade data into UserTrade objects."""
        return parse_user_trades(trades_data)

    # Public market data (klines, depth, public trades, tickers) → MarketDataClient.

    async def get_user_trades(
        self, user: UserType | None = None, *, page: int | None = None, limit: int | None = None
    ) -> list[UserTrade]:
        """
        Get trades for the authenticated user, newest first.
        Returns empty list if user is not yet known to the OMS.
        """
        page_result = await self.get_user_trades_page(user=user, page=page, limit=limit)
        return page_result.trades

    async def get_user_trades_for_asset(
        self,
        asset_id: AssetIdentifier,
        user: UserType | None = None,
        *,
        page: int | None = None,
        limit: int | None = None,
    ) -> list[UserTrade]:
        """
        Get trades for a specific asset for the authenticated user, newest first.
        Returns empty list if user is not yet known to the OMS.
        """
        page_result = await self.get_user_trades_page(
            asset_id=asset_id, user=user, page=page, limit=limit
        )
        return page_result.trades

    async def get_user_trades_page(
        self,
        *,
        asset_id: AssetIdentifier | None = None,
        page: int | None = None,
        limit: int | None = None,
        user: UserType | None = None,
    ) -> UserTradesPage:
        """Fetch one page of user trades with pagination metadata (`has_next_page`, etc.)."""
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/trades/user/{public_key}"
        if asset_id is not None:
            endpoint = f"{endpoint}/{asset_id}"
        try:
            data = await self._request("GET", endpoint, params=_page_params(page, limit))
        except NotFoundError:
            return parse_user_trades_page([])
        return parse_user_trades_page(data)

    async def get_user_positions(
        self,
        user: UserType | None = None,
        *,
        sub_account: int | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> list[PositionResponse]:
        """
        Get open positions for the authenticated user.
        Returns empty list if user is not yet known to the OMS.
        """
        page_result = await self.get_user_positions_page(
            sub_account=sub_account, page=page, limit=limit, user=user
        )
        return page_result.positions

    async def get_user_positions_page(
        self,
        *,
        sub_account: int | None = None,
        page: int | None = None,
        limit: int | None = None,
        user: UserType | None = None,
    ) -> UserPositionsPage:
        """Fetch one page of user positions with pagination metadata (`has_next_page`, etc.)."""
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/positions/{public_key}"
        params = _page_params(page, limit, sub_account=sub_account)
        try:
            data = await self._request("GET", endpoint, params=params)
        except NotFoundError:
            return parse_positions_page([])
        return parse_positions_page(data)

    async def get_user_orders(
        self, user: UserType | None = None, *, page: int | None = None, limit: int | None = None
    ) -> tuple[list[OrderResponse], dict[str, Any]]:
        """
        Get orders for the authenticated user, newest first.
        Returns `(orders, raw_page)` where `raw_page` carries pagination metadata.
        Returns empty results if user is not yet known to the OMS.
        """
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/orders/user/{public_key}"
        self.logger.debug(f"Getting Orders for user {public_key}")
        try:
            response_data = await self._request("GET", endpoint, params=_page_params(page, limit))
        except NotFoundError:
            return [], {}

        if isinstance(response_data, dict) and "error" in response_data:
            self.logger.error(
                f"Received error when fetching user orders: {response_data['error']}. Check authentication."
            )
            return [], {}

        if isinstance(response_data, dict):
            return parse_orders(response_data.get("orders", [])), response_data
        if isinstance(response_data, list):
            return parse_orders(response_data), {"orders": response_data}

        self.logger.error(
            f"Unexpected response type when fetching user orders: {type(response_data).__name__}."
        )
        return [], {}

    async def get_user_orders_for_book(
        self,
        asset_id: AssetIdentifier,
        *,
        page: int | None = None,
        limit: int | None = None,
        open_only: bool | None = None,
        user: UserType | None = None,
    ) -> list[OrderResponse]:
        """
        Get orders for a specific asset for the authenticated user (async).
        Handles 404 with empty list as "no orders" gracefully.
        """
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/orders/user/{public_key}/{asset_id}"
        params_dict: dict[str, Any] | None = None
        if page is not None or limit is not None or open_only is not None:
            params_dict = {
                "page": 0 if page is None else int(page),
                "limit": 1000 if limit is None else int(limit),
            }
            if open_only is not None:
                params_dict["open_only"] = bool(open_only)
        self.logger.debug(f"Getting Orders for user {public_key}, asset {asset_id}")
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

        except NotFoundError:
            # Structured 404 from the new error format -- treat as "no orders".
            self.logger.debug(
                f"Received NotFoundError for {endpoint} (User: {public_key}, Asset: {asset_id}). "
                f"Treating as empty order list."
            )
            return []

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404 and e.request.url.path == endpoint:
                try:
                    content = e.response.json()
                    if isinstance(content, list) and not content:
                        self.logger.debug(
                            f"Received 404 with empty list for {endpoint} (User: {public_key}, Asset: {asset_id}). "
                            f"This is expected if the user has no orders for this asset yet. Treating as success with no orders."
                        )
                        return []
                    else:
                        self.logger.warning(
                            f"Received 404 for {endpoint} (User: {public_key}, Asset: {asset_id}), "
                            f"but response body was not an empty list as expected for 'no orders'. Body: {e.response.text[:200]}"
                        )
                except json.JSONDecodeError:
                    self.logger.warning(
                        f"Received 404 for {endpoint} (User: {public_key}, Asset: {asset_id}), "
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

    async def get_user_inventory(self, user: UserType | None = None) -> dict[str, Any]:
        """
        Get inventory for the authenticated user (async).
        Returns empty dict if user is not yet known to the OMS.
        """
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/inventory/user/{public_key}"
        self.logger.debug(f"Getting Inventory for user {public_key}")
        try:
            return await self._request("GET", endpoint)
        except NotFoundError:
            return {}

    async def get_multisig_config(self, user: UserType | None = None) -> dict[str, Any]:
        """
        Get the user's multisig config from OMS.
        Returns the default single-signer config if no explicit config is stored.
        """
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/multisig/config/{public_key}"
        self.logger.debug(f"Getting multisig config for user {public_key}")
        try:
            return await self._request("GET", endpoint, user=user)
        except NotFoundError:
            return {
                "master_weight": 1,
                "signers": [],
                "thresholds": {"low": 1, "medium": 1, "high": 1},
            }

    async def stream_orders(self, user: UserType | None = None) -> AsyncIterator[OrderEvent]:
        """Stream order events for the authenticated user.

        Args:
            user: Optional User or public key. If not provided, the default user is used.

        Yields:
            :class:`OrderEvent` records as they arrive on the WebSocket.
        """
        async for event in self._stream_ws("/orders", parse_order_event, user=user):
            yield event

    async def stream_user_trade_events(
        self, user: UserType | None = None
    ) -> AsyncIterator[UserTrade]:
        """
        Stream **all** trade events (``Pending``, ``Confirmed``, ``Rollbacked``) for a specific user.

        Args:
            user: Optional User or public key. If not provided, the default user is used.
        Yields:
            :class:`tplus.model.trades.UserTrade` objects with detailed order-side information.
        """
        user_id = self._validate_user_public_key(user=user)
        path = f"/trades/user/events/{user_id}"
        async for trade in self._stream_ws(path, parse_single_user_trade):
            yield trade

    async def stream_user_finalized_trades(
        self, user: UserType | None = None
    ) -> AsyncIterator[UserTrade]:
        """
        Stream **finalized** (confirmed) trades for a specific user.

        Args:
            user: Optional User or public key. If not provided, the default user is used.
        Yields:
            :class:`tplus.model.trades.UserTrade` instances containing only confirmed trades.
        """
        user_id = self._validate_user_public_key(user=user)
        path = f"/trades/user/{user_id}"
        async for trade in self._stream_ws(path, parse_single_user_trade):
            yield trade

    async def stream_user_trades(self, user: UserType | None = None) -> AsyncIterator[UserTrade]:
        """
        [DEPRECATED] Use stream_user_trade_events or stream_user_finalized_trades instead.
        This method streams finalized (confirmed) trades for a specific user.
        """
        async for trade in self.stream_user_finalized_trades(user=user):
            yield trade

    async def stream_user_events(
        self, user: UserType | None = None
    ) -> AsyncIterator[UserActivityEvent]:
        """Stream typed user-activity events on `/account/events/{user_id}`.

        Each event is a `DepositLanded`, `WithdrawalCompleted`,
        `PositionCleared`, or `SubAccountAssetTransferred` model carrying the
        amount/chain/asset context the FE needs to render notifications
        without diffing balance state. Liquidation fills surface as
        `is_liquidation=True` on the user-trades stream rather than here.

        Args:
            user: Optional User or public key. If not provided, the default user is used.
        """
        user_id = self._validate_user_public_key(user=user)
        path = f"/account/events/{user_id}"
        async for event in self._stream_ws(path, parse_user_event):
            yield event

    async def get_user_solvency(self, user: UserType | None = None) -> UserSolvency:
        """
        Get solvency for the authenticated user (async).
        Returns empty solvency if user is not yet known to the OMS.
        """
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/solvency/user/{public_key}"

        self.logger.debug(f"Getting Solvency for user {public_key}")
        try:
            response_data = await self._request("GET", endpoint)
        except NotFoundError:
            response_data = {"accounts": {}}

        if not isinstance(response_data, dict):
            raise Exception("Invalid response from get_user_solvency.")

        parsed_data: UserSolvency = parse_user_solvency(response_data)
        return parsed_data

    async def get_close_all_positions_preview(
        self,
        sub_account_index: int,
        user: UserType | None = None,
    ) -> CloseAllPreviewResponse:
        """
        Preview unsigned orders to close all margin positions in a sub-account.

        GET /positions/close-all/{user_id}/{sub_account_index}

        Args:
            sub_account_index: Sub-account index (e.g. 1 for cross-margin).
            user: User or hex public key; defaults to the authenticated user.

        Returns:
            CloseAllPreviewResponse with unsigned orders and any per-asset errors.
        """
        uid = self._validate_user_public_key(user=user)
        endpoint = f"/positions/close-all/{uid}/{sub_account_index}"

        self.logger.debug(
            f"Getting close-all preview for user {uid}, sub_account={sub_account_index}"
        )
        response_data = await self._request("GET", endpoint)

        if not isinstance(response_data, dict):
            raise Exception("Invalid response from get_close_all_preview.")

        return parse_close_all_preview(response_data)

    async def get_user_margin_info(
        self,
        sub_accounts: list[int] | None = None,
        include_positions: bool = False,
        user: UserType | None = None,
    ) -> UserMarginInfo:
        """
        Get detailed margin breakdown for the authenticated user (async).

        Returns margin metrics for each sub-account including:
        - Account equity: Total portfolio value at mark prices (no margin risk adjustments applied)
        - Available margin: IM surplus - how much margin is available for new positions
        - Utilized margin: Total margin currently consumed by existing positions
        - Maintenance margin surplus: Distance from liquidation (MM surplus)
        - Account leverage: total_notional / equity
        - Per-position breakdown (optional)

        The endpoint uses min(oracle, LTP) pricing for surplus calculations,
        matching the solvency check conjunction over both price types.

        Args:
            sub_accounts: Optional list of sub-account indices to include.
                If None or empty, returns info for all sub-accounts.
            include_positions: If True, includes per-position breakdown
                with size and notional value for each position.
            user: Optional User or public key. Falls back to the default user.

        Returns:
            UserMarginInfo containing margin breakdown per sub-account.

        Raises:
            Exception: If the API response is invalid.
        """
        public_key = self._validate_user_public_key(user=user)
        endpoint = f"/margin/user/{public_key}"

        params: dict[str, Any] = {}
        if sub_accounts:
            params["sub_account"] = sub_accounts
        if include_positions:
            params["include_positions"] = include_positions

        self.logger.debug(
            f"Getting Margin Info for user {public_key}, "
            f"sub_accounts={sub_accounts}, include_positions={include_positions}"
        )
        try:
            response_data = await self._request("GET", endpoint, params=params if params else None)
        except NotFoundError:
            response_data = {"accounts": {}}

        if not isinstance(response_data, dict):
            raise Exception("Invalid response from get_user_margin_info.")

        parsed_data: UserMarginInfo = parse_user_margin_info(response_data)
        return parsed_data

    async def request_transfer_to_subaccount(
        self,
        source_index: int,
        target_index: int,
        transfer_asset: AssetIdentifier,
        transfer_amount: int,
        target_account_type: None = None,
        user: "User | None" = None,
    ) -> dict[str, Any]:
        user = self._resolve_user(user=user)
        payload = self._build_transfer_to_subaccount(
            source_index,
            target_index,
            transfer_asset,
            transfer_amount,
            target_account_type,
            user=user,
        )

        response_data = await self._send_transfer_request(payload)
        return response_data

    async def _send_transfer_request(self, payload):
        self.logger.debug(f"Sending subaccount transfer request. Payload is: {payload}")
        response_data = await self._request(
            "POST", "/account/transfer/sub-account", json_data=payload
        )
        return response_data

    def _build_transfer_to_subaccount(
        self,
        source_index,
        target_index,
        transfer_asset,
        transfer_amount,
        target_account_type=None,
        user: "User | None" = None,
    ):
        user = self._resolve_user(user=user)
        inner = {
            "user": user.public_key,
            "source_index": source_index,
            "target_index": target_index,
            "transfer_asset": str(transfer_asset),
            "transfer_amount": str(transfer_amount),
            "target_account_type": target_account_type,
        }
        self.logger.debug(f"Transfer request: {inner}")
        signing_payload = json.dumps(inner, separators=(",", ":"))
        signature = list(user.sign(signing_payload))
        payload = {
            "inner": inner,
            "signature": signature,
            "additional_signers": [],
        }
        return payload

    async def request_close_position(
        self, account: int, transfer_asset: str, user: "User | None" = None
    ) -> dict[str, Any]:
        user = self._resolve_user(user=user)
        payload = self._build_close_position_request(account, transfer_asset, user=user)

        response_data = await self._send_close_position_request(payload)
        return response_data

    def _build_close_position_request(
        self, account: int, transfer_asset: str, user: "User | None" = None
    ) -> dict:
        """Same signing rules as CE: compact JSON of inner, ed25519 over UTF-8 bytes."""
        user = self._resolve_user(user=user)
        inner = {
            "user": user.public_key,
            "account": account,
            "asset_identifier": transfer_asset,
        }

        self.logger.debug(f"Preparing close position request: {inner}")
        signing_payload = json.dumps(inner, separators=(",", ":"))
        signature = list(user.sign(signing_payload))
        payload = {
            "inner": inner,
            "signature": signature,
            "additional_signers": [],
        }
        return payload

    async def _send_close_position_request(self, payload):
        self.logger.debug(f"Sending close position request. Payload is: {payload}")
        response_data = await self._request(
            "POST", "/account/transfer/close-position", json_data=payload
        )
        return response_data

    async def init_settlement(self, request: dict | TxSettlementRequest) -> dict[str, Any]:
        """Initialize a settlement via the OMS, returning the CE approval.

        Args:
            request: A signed :class:`~tplus.model.settlement.TxSettlementRequest`
                (or an equivalent dict).

        Returns:
            The approval returned by the clearing engine.
        """
        if isinstance(request, dict):
            request = TxSettlementRequest.model_validate(request)

        data = request.model_dump(mode="json", exclude_none=True)
        response = await self._post("settlement/init", json_data=data)
        if isinstance(response, dict) and response.get("success") is False:
            reason = response.get("details") or "Settlement initialization failed"
            raise RuntimeError(str(reason))

        if isinstance(response, dict):
            approval = response.get("approval")
            if isinstance(approval, dict):
                return approval

        raise RuntimeError("Settlement initialization succeeded but no approval was returned")

    async def get_settlement_signatures(self, user: str) -> list[dict]:
        """Get CE-approved settlement signatures for ``user``.

        This happens after settlement initialization.

        Args:
            user (str): The settler.

        Returns:
            A list of approval dictionaries containing signatures, nonces, and expirys.
        """
        prefix = "settlement/signatures"
        result = await self._get(f"{prefix}/{user}")
        if isinstance(result, list):
            return result

        if isinstance(result, dict) and "error" in result:
            raise RuntimeError(result["error"])

        raise RuntimeError(f"Unknown result format for {prefix} response: {result}.")
