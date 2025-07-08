import json
import time  # For timestamps on signed messages
import uuid  # For generating order_ids
from collections.abc import AsyncIterator
from typing import Any, Callable, Optional, Union
from urllib.parse import urlunparse

import httpx
import websockets

from tplus.client.base import BaseClient
from tplus.logger import logger
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.klines import KlineUpdate, parse_kline_update
from tplus.model.limit_order import GTC, GTD, IOC
from tplus.model.market import Market, parse_market
from tplus.model.order import OrderEvent, OrderResponse, parse_order_event, parse_orders
from tplus.model.orderbook import OrderBook, OrderBookDiff
from tplus.model.trades import Trade, TradeEvent, UserTrade, parse_trade_event, parse_trades, parse_single_trade, parse_single_user_trade
from tplus.utils.limit_order import create_limit_order_ob_request_payload
from tplus.utils.market_order import create_market_order_ob_request_payload
from tplus.utils.replace_order import create_replace_order_ob_request_payload
from tplus.utils.signing import build_signed_message, create_cancel_order_ob_request_payload


class OrderBookClient(BaseClient):
    async def create_market(self, asset_id: Union[AssetIdentifier, str]) -> dict[str, Any]:
        """
        Create and send a market (async).
        """
        if isinstance(asset_id, str):
            asset_id = AssetIdentifier(asset_id)
        message_dict = {"asset_id": asset_id.model_dump()}
        logger.debug(f"Creating Market for Asset {asset_id}")
        return await self._request("POST", "/market/create", json_data=message_dict)

    async def get_market(self, asset_id: AssetIdentifier) -> Market:
        """
        Get a market (async).
        """
        response = await self._request("GET", f"/market/{asset_id}")
        market = parse_market(response)
        return market

    async def create_market_order(
        self,
        quantity: int,
        side: str,
        fill_or_kill: bool = False,
        asset_id: Optional[AssetIdentifier] = None,
    ) -> dict[str, Any]:
        """
        Create a market order (async).
        """
        order_id = str(uuid.uuid4())
        market = await self.get_market(asset_id)
        ob_request_payload = create_market_order_ob_request_payload(
            quantity=quantity,
            side=side,
            signer=self.user,
            book_quantity_decimals=market.book_quantity_decimals,
            asset_identifier=asset_id,
            order_id=order_id,
            fill_or_kill=fill_or_kill,
        )
        signed_message = build_signed_message(
            order_id=order_id,
            asset_identifier=asset_id,
            operation_specific_payload=ob_request_payload,
            signer=self.user,
        )
        logger.debug(
            f"Sending Market Order (Asset {asset_id}): Qty={quantity}, Side={side}, FOK={fill_or_kill}, OrderID={order_id}"
        )
        return await self._request("POST", "/orders/create", json_data=signed_message.model_dump())

    async def create_limit_order(
        self,
        quantity: int,
        price: int,
        side: str,
        time_in_force: Optional[GTC | GTD | IOC] = None,
        asset_id: Optional[AssetIdentifier] = None,
    ) -> dict[str, Any]:
        """
        Create a limit order (async).
        """
        order_id = str(uuid.uuid4())
        market = await self.get_market(asset_id)
        ob_request_payload = create_limit_order_ob_request_payload(
            quantity=quantity,
            price=price,
            side=side,
            signer=self.user,
            book_quantity_decimals=market.book_quantity_decimals,
            book_price_decimals=market.book_price_decimals,
            asset_identifier=asset_id,
            order_id=order_id,
            time_in_force=time_in_force,
        )
        signed_message = build_signed_message(
            order_id=order_id,
            asset_identifier=asset_id,
            operation_specific_payload=ob_request_payload,
            signer=self.user,
        )
        logger.debug(
            f"Sending Limit Order (Asset {asset_id}): Qty={quantity}, Price={price}, Side={side}, OrderID={order_id}"
        )
        return await self._request("POST", "/orders/create", json_data=signed_message.model_dump())

    async def cancel_order(
        self, order_id: str, asset_id: Optional[AssetIdentifier] = None
    ) -> dict[str, Any]:
        """
        Cancel an order (async).
        """
        cancel_ob_request_payload = create_cancel_order_ob_request_payload(order_id=order_id)
        signed_message = build_signed_message(
            order_id=order_id,
            asset_identifier=asset_id,
            operation_specific_payload=cancel_ob_request_payload,
            signer=self.user,
        )
        signed_message.post_sign_timestamp = int(time.time() * 1_000_000_000)
        logger.debug(f"Sending Cancel Order Request: OrderID={order_id}, Asset={asset_id}")
        return await self._request(
            "DELETE", "/orders/cancel", json_data=signed_message.model_dump()
        )

    async def replace_order(
        self,
        original_order_id: str,
        asset_id: AssetIdentifier,
        new_quantity: Optional[int] = None,
        new_price: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Replace an existing order with new parameters (async).
        """
        replace_operation_id = str(uuid.uuid4())
        market = await self.get_market(asset_id)
        operation_specific_payload = create_replace_order_ob_request_payload(
            original_order_id=original_order_id,
            asset_identifier=asset_id,
            signer=self.user,
            new_price=new_price,
            new_quantity=new_quantity,
            book_price_decimals=market.book_price_decimals,
            book_quantity_decimals=market.book_quantity_decimals,
        )
        signed_message = build_signed_message(
            order_id=replace_operation_id,
            asset_identifier=asset_id,
            operation_specific_payload=operation_specific_payload,
            signer=self.user,
        )
        signed_message.post_sign_timestamp = int(time.time() * 1_000_000_000)
        logger.debug(
            f"Sending Replace Order for original OrderID {original_order_id} (Asset {asset_id}): "
            f"New Qty={new_quantity}, New Price={new_price}, ReplaceOpID={replace_operation_id}"
        )
        return await self._request(
            "PATCH", "/orders/replace", json_data=signed_message.model_dump(exclude_none=True)
        )

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
        logger.debug(f"Getting Order Book Snapshot for asset {asset_id}")
        response = await self._request("GET", endpoint)
        if not isinstance(response, dict):
            logger.error(f"Received non-dictionary response for order book snapshot: {response}")
            raise ValueError(
                f"Invalid API response for order book snapshot: expected a dictionary, got {type(response).__name__}"
            )
        try:
            return OrderBook(**response)
        except TypeError as e:
            logger.error(
                f"Failed to parse order book snapshot response dict into OrderBook object: {e}. Response dict: {response}"
            )
            raise ValueError(
                f"Could not parse API response dictionary for order book snapshot: {response}"
            ) from e

    async def get_klines(self, asset_id: AssetIdentifier) -> dict[str, Any]:
        """
        Get K-line (candlestick) data for a given asset (async).
        """
        endpoint = f"/klines/{asset_id}"
        logger.debug(f"Getting Klines for asset {asset_id}")
        return await self._request("GET", endpoint)

    async def get_user_trades(self) -> list[UserTrade]:
        """
        Get all trades for the authenticated user (async).
        """
        endpoint = f"/trades/user/{self.user.public_key}"
        logger.debug(f"Getting Trades for user {self.user.public_key}")
        response_data = await self._request("GET", endpoint)
        return self.parse_user_trades(response_data)

    async def get_user_trades_for_asset(self, asset_id: AssetIdentifier) -> list[UserTrade]:
        """
        Get trades for a specific asset for the authenticated user (async).
        """
        endpoint = f"/trades/user/{self.user.public_key}/{asset_id}"
        logger.debug(f"Getting Trades for user {self.user.public_key}, asset {asset_id}")
        response_data = await self._request("GET", endpoint)
        return self.parse_user_trades(response_data)

    async def get_user_orders(self) -> tuple[list[OrderResponse], dict[str, Any]]:
        """
        Get all orders for the authenticated user (async).
        """
        endpoint = f"/orders/user/{self.user.public_key}"
        logger.debug(f"Getting Orders for user {self.user.public_key}")
        response_data = await self._request("GET", endpoint)
        parsed_orders = parse_orders(response_data)
        return parsed_orders, response_data

    async def get_user_orders_for_book(
        self, asset_id: AssetIdentifier
    ) -> tuple[list[OrderResponse], dict[str, Any]]:
        """
        Get orders for a specific asset for the authenticated user (async).
        Handles 404 with empty list as "no orders" gracefully.
        """
        endpoint = f"/orders/user/{self.user.public_key}/{asset_id}"
        logger.debug(f"Getting Orders for user {self.user.public_key}, asset {asset_id}")
        try:
            response_data = await self._request("GET", endpoint)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404 and e.request.url.path == endpoint:
                try:
                    content = e.response.json()
                    if isinstance(content, list) and not content:
                        logger.debug(
                            f"Received 404 with empty list for {endpoint} (User: {self.user.public_key}, Asset: {asset_id}). "
                            f"This is expected if the user has no orders for this asset yet. Treating as success with no orders."
                        )
                        return [], {}
                    else:
                        logger.warning(
                            f"Received 404 for {endpoint} (User: {self.user.public_key}, Asset: {asset_id}), "
                            f"but response body was not an empty list as expected for 'no orders'. Body: {e.response.text[:200]}"
                        )
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received 404 for {endpoint} (User: {self.user.public_key}, Asset: {asset_id}), "
                        f"but response body was not valid JSON. Body: {e.response.text[:200]}"
                    )
            raise e
        parsed_orders = parse_orders(response_data)
        return parsed_orders, response_data

    async def get_user_inventory(self) -> dict[str, Any]:
        """
        Get inventory for the authenticated user (async).
        """
        endpoint = f"/inventory/user/{self.user.public_key}"
        logger.debug(f"Getting Inventory for user {self.user.public_key}")
        return await self._request("GET", endpoint)

    def _get_websocket_url(self, path: str) -> str:
        """
        Constructs the WebSocket URL from the base HTTP URL.
        """
        scheme = "wss" if self._parsed_base_url.scheme == "https" else "ws"
        netloc = self._parsed_base_url.netloc
        ws_path = path if path.startswith("/") else f"/{path}"
        return urlunparse((scheme, netloc, ws_path, "", "", ""))

    # WebSocket control-message types recognized across all streams.
    CONTROL_MESSAGE_TYPES: set[str] = {
        "subscriptions",
        "ping",
        "pong",
    }

    async def _stream_ws(
        self,
        path: str,
        parser: Callable[[Any], Any],
        *,
        control_handler: Callable[[dict[str, Any]], None] | None = None,
    ) -> AsyncIterator[Any]:
        """
        Connects to a WebSocket path, filters out control messages, and yields parsed payloads.
        """
        ws_url = self._get_websocket_url(path)
        logger.debug("Connecting to %s stream: %s", path, ws_url)
        async with websockets.connect(ws_url) as websocket:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if isinstance(data, dict) and data.get("type") in self.CONTROL_MESSAGE_TYPES:
                        logger.debug(
                            "Control message on %s stream: type=%s, payload=%s",
                            path,
                            data.get("type"),
                            data,
                        )
                        if control_handler is not None:
                            try:
                                control_handler(data)
                            except Exception as handler_err:
                                logger.warning(
                                    "Control-handler for %s raised %s – ignoring.",
                                    path,
                                    handler_err,
                                )
                        continue
                    yield parser(data)
                except json.JSONDecodeError:
                    logger.warning(
                        "Received non-JSON message on %s stream: %s…", path, message[:100]
                    )
                except Exception as e:
                    logger.error(
                        "Error processing message from %s stream: %s. Message: %s…",
                        path,
                        e,
                        message[:100],
                    )

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

    async def stream_user_trades(self, user_id: Optional[str] = None) -> AsyncIterator[UserTrade]:
        """
        Stream trade events for a specific user.
        Returns UserTrade objects containing order_id, side, maker/taker info, and other trade details.
        
        Args:
            user_id: User identifier. If None, uses the authenticated user's public key.
        """
        if user_id is None:
            user_id = self.user.public_key
        path = f"/trades/user/{user_id}"
        async for trade in self._stream_ws(path, parse_single_user_trade):
            yield trade

    async def close(self) -> None:
        """
        Closes the underlying httpx async client.
        """
        logger.debug("Closing async HTTP client.")
        await self._client.aclose()

    async def __aenter__(self):
        """
        Async context manager entry.
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.
        """
        await self.close()
