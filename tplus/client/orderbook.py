import json
import time  # Added for timestamps
import uuid  # Added for generating order_ids
from collections.abc import AsyncIterator
from typing import Any, Optional, Union
from urllib.parse import urlunparse

import httpx
import websockets
from pydantic import ValidationError

from tplus.client.base import BaseClient
from tplus.logger import logger
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.klines import KlineUpdate, parse_kline_update
from tplus.model.limit_order import GTC, GTD, IOC
from tplus.model.market import Market, parse_market
from tplus.model.order import OrderEvent, OrderResponse, parse_order_event, parse_orders
from tplus.model.orderbook import (
    OrderBook,
    OrderBookDiff,
)
from tplus.model.trades import Trade, TradeEvent, parse_trade_event, parse_trades

# Updated imports for refactored utils
from tplus.utils.limit_order import create_limit_order_ob_request_payload
from tplus.utils.market_order import create_market_order_ob_request_payload
from tplus.utils.replace_order import create_replace_order_ob_request_payload
from tplus.utils.signing import build_signed_message, create_cancel_order_ob_request_payload


class OrderBookClient(BaseClient):
    # --- Async Market Creation Methods ---
    async def create_market(self, asset_id: Union[AssetIdentifier, str]) -> dict[str, Any]:
        """
        Create and send a market (async).

        Args:
            asset_id: asset for which the market must be created. Can be an AssetIdentifier object or string.

        Returns:
            The API response dictionary.
        """
        # Convert string to AssetIdentifier if needed
        if isinstance(asset_id, str):
            asset_id = AssetIdentifier(asset_id)

        message_dict = {"asset_id": asset_id.model_dump()}

        logger.debug(f"Creating Market for Asset {asset_id}")
        # Use await for the async request
        return await self._request("POST", "/market/create", json_data=message_dict)

    # --- Async Get Market Methods ---
    async def get_market(self, asset_id: AssetIdentifier) -> Market:
        """
        Get a market (async).

        Args:
            asset_id: asset for which we get the market

        Returns:
            The API response dictionary.
        """
        # Use await for the async request
        response = await self._request("GET", f"/market/{asset_id}")
        market = parse_market(response)
        return market

    # --- Async Order Creation Methods ---
    async def create_market_order(
        self,
        quantity: int,
        side: str,
        fill_or_kill: bool = False,
        asset_id: Optional[AssetIdentifier] = None,
    ) -> dict[str, Any]:
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
        # Use the new helper to create the specific cancel request payload
        cancel_ob_request_payload = create_cancel_order_ob_request_payload(order_id=order_id)

        signed_message = build_signed_message(
            order_id=order_id,  # order_id is also part of CancelOrderDataToSign
            asset_identifier=asset_id,  # asset_identifier is used here for the broader message
            operation_specific_payload=cancel_ob_request_payload,
            signer=self.user,
        )
        signed_message.post_sign_timestamp = int(time.time() * 1_000_000_000)  # Add timestamp

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

        Args:
            original_order_id: The ID of the order to be replaced.
            asset_id: The asset identifier for the order.
            new_quantity: Optional new quantity for the order.
            new_price: Optional new price for the order.

        Returns:
            The API response dictionary.
        """
        # This ID is for the replace operation itself, if needed for the ObRequest wrapper.
        # The actual order ID being replaced is inside ReplaceOrderDetails.
        replace_operation_id = str(uuid.uuid4())
        market = await self.get_market(asset_id)  # Fetch market details for decimals

        # Use the new create_replace_order_ob_request_payload from replace_order.py
        # This payload will be of type ReplaceOrderRequestPayload
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
            order_id=replace_operation_id,  # ID for this specific replace operation/request
            asset_identifier=asset_id,  # Asset ID also part of ReplaceOrderRequestPayload
            operation_specific_payload=operation_specific_payload,
            signer=self.user,
        )
        signed_message.post_sign_timestamp = int(time.time() * 1_000_000_000)  # Add timestamp

        logger.debug(
            f"Sending Replace Order for original OrderID {original_order_id} (Asset {asset_id}): "
            f"New Qty={new_quantity}, New Price={new_price}, ReplaceOpID={replace_operation_id}"
        )
        # The Rust endpoint uses PATCH for replace
        return await self._request(
            "PATCH", "/orders/replace", json_data=signed_message.model_dump(exclude_none=True)
        )

    # --- Parsing Methods (remain synchronous utility functions) ---
    def parse_trades(self, trades_data: list[dict[str, Any]]) -> list[Trade]:
        """
        Parse trade data into Trade objects.

        Args:
            trades_data: List of trade dictionaries from the API

        Returns:
            List of Trade objects
        """
        return parse_trades(trades_data)

    # --- Async GET Methods ---
    async def get_orderbook_snapshot(self, asset_id: AssetIdentifier) -> OrderBook:
        """
        Get a snapshot of the order book for a given asset (async).

        Args:
            asset_id: The asset identifier (AssetIdentifier).

        Returns:
            An OrderBook object representing the snapshot.
        """
        endpoint = f"/marketdepth/{asset_id}"
        logger.debug(f"Getting Order Book Snapshot for asset {asset_id}")
        # Use await for the async request
        response = await self._request("GET", endpoint)

        # Check if the response is a valid dictionary before unpacking
        if not isinstance(response, dict):
            logger.error(f"Received non-dictionary response for order book snapshot: {response}")
            raise ValueError(
                f"Invalid API response for order book snapshot: expected a dictionary, got {type(response).__name__}"
            )

        # Assuming the response dict structure matches OrderBook constructor
        # Example: {'asks': [[price, qty], ...], 'bids': [[price, qty], ...], 'sequence_number': num}
        # If the API response structure is different, adjust parsing accordingly.
        try:
            return OrderBook(**response)
        except TypeError as e:
            # This catch might still be useful for other potential TypeError scenarios
            logger.error(
                f"Failed to parse order book snapshot response dict into OrderBook object: {e}. Response dict: {response}"
            )
            raise ValueError(
                f"Could not parse API response dictionary for order book snapshot: {response}"
            ) from e

    async def get_klines(self, asset_id: AssetIdentifier) -> dict[str, Any]:
        """
        Get K-line (candlestick) data for a given asset (async).

        Args:
            asset_id: The asset identifier (AssetIdentifier).

        Returns:
            The K-line data dictionary from the API.
        """
        endpoint = f"/klines/{asset_id}"
        logger.debug(f"Getting Klines for asset {asset_id}")
        # Use await for the async request
        return await self._request("GET", endpoint)

    async def get_user_trades(self) -> list[Trade]:
        """
        Get all trades for the authenticated user (async).

        Returns:
            A list of Trade objects.
        """
        endpoint = f"/trades/user/{self.user.public_key}"
        logger.debug(f"Getting Trades for user {self.user.public_key}")
        # Use await for the async request
        response_data = await self._request("GET", endpoint)
        # Parsing remains synchronous
        return self.parse_trades(response_data)

    async def get_user_trades_for_asset(self, asset_id: AssetIdentifier) -> list[Trade]:
        """
        Get trades for a specific asset for the authenticated user (async).

        Args:
            asset_id: The asset identifier (AssetIdentifier).

        Returns:
            A list of Trade objects.
        """
        endpoint = f"/trades/user/{self.user.public_key}/{asset_id}"
        logger.debug(f"Getting Trades for user {self.user.public_key}, asset {asset_id}")
        # Use await for the async request
        response_data = await self._request("GET", endpoint)
        # Parsing remains synchronous
        return self.parse_trades(response_data)

    async def get_user_orders(self) -> tuple[list[OrderResponse], dict[str, Any]]:
        """
        Get all orders for the authenticated user (async).

        Returns:
            A tuple containing the list of parsed OrderResponse objects and the raw API response dictionary.
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

        Args:
            asset_id: The asset identifier (AssetIdentifier).

        Returns:
            A tuple containing the list of parsed OrderResponse objects and the raw API response dictionary.
        """
        endpoint = f"/orders/user/{self.user.public_key}/{asset_id}"
        logger.debug(f"Getting Orders for user {self.user.public_key}, asset {asset_id}")
        try:
            response_data = await self._request("GET", endpoint)
        except httpx.HTTPStatusError as e:
            # Check if it's a 404 specifically for this endpoint
            if e.response.status_code == 404 and e.request.url.path == endpoint:
                try:
                    content = e.response.json()
                    # If the response is an empty list, it means no orders were found, which is a valid scenario.
                    if isinstance(content, list) and not content:
                        logger.debug(
                            f"Received 404 with empty list for {endpoint} (User: {self.user.public_key}, Asset: {asset_id}). "
                            f"This is expected if the user has no orders for this asset yet. Treating as success with no orders."
                        )
                        return [], {}  # Return empty list of orders and empty raw response
                    else:
                        # Log that it was a 404 for the right endpoint, but content wasn't an empty list
                        logger.warning(
                            f"Received 404 for {endpoint} (User: {self.user.public_key}, Asset: {asset_id}), "
                            f"but response body was not an empty list as expected for 'no orders'. Body: {e.response.text[:200]}"
                        )
                except json.JSONDecodeError:
                    # Log that it was a 404 for the right endpoint, but content wasn't JSON
                    logger.warning(
                        f"Received 404 for {endpoint} (User: {self.user.public_key}, Asset: {asset_id}), "
                        f"but response body was not valid JSON. Body: {e.response.text[:200]}"
                    )

            # If it's not the specific 404 we're handling (e.g. different status, different endpoint, or unexpected body for the 404), re-raise.
            raise e

        parsed_orders = parse_orders(response_data)
        return parsed_orders, response_data

    async def get_user_inventory(self) -> dict[str, Any]:
        """
        Get inventory for the authenticated user (async).

        Returns:
            The inventory data dictionary from the API.
            (Consider creating an Inventory model for parsing)
        """
        endpoint = f"/inventory/user/{self.user.public_key}"
        logger.debug(f"Getting Inventory for user {self.user.public_key}")
        # Use await for the async request
        return await self._request("GET", endpoint)

    # --- WebSocket URL Construction ---
    def _get_websocket_url(self, path: str) -> str:
        """Constructs the WebSocket URL from the base HTTP URL."""
        scheme = "wss" if self._parsed_base_url.scheme == "https" else "ws"
        # Use the netloc (host:port) from the original base URL
        netloc = self._parsed_base_url.netloc
        # Ensure the path starts with a '/'
        ws_path = path if path.startswith("/") else f"/{path}"
        # Reconstruct the URL with ws/wss scheme
        return urlunparse((scheme, netloc, ws_path, "", "", ""))

    # --- WebSocket Streaming Methods ---
    async def stream_orders(self) -> AsyncIterator[OrderEvent]:
        """Stream all order events (creations, updates, cancellations)."""
        ws_url = self._get_websocket_url("/orders")
        logger.debug(f"Connecting to orders stream: {ws_url}")
        async with websockets.connect(ws_url) as websocket:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # Add parsing logic here, assuming parse_order_event exists
                    yield parse_order_event(data)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received non-JSON message on orders stream: {message[:100]}..."
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing message from orders stream: {e}. Message: {message[:100]}..."
                    )
                    # Decide whether to continue or break/raise

    async def stream_finalized_trades(self) -> AsyncIterator[Trade]:
        """Stream only confirmed/finalized trades."""
        ws_url = self._get_websocket_url("/trades")
        logger.debug(f"Connecting to finalized trades stream: {ws_url}")
        async with websockets.connect(ws_url) as websocket:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # Reuse the single Trade parser
                    yield Trade(**data)  # Assuming direct mapping
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received non-JSON message on finalized trades stream: {message[:100]}..."
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing message from finalized trades stream: {e}. Message: {message[:100]}..."
                    )

    async def stream_all_trades(self) -> AsyncIterator[TradeEvent]:
        """Stream all trade events (e.g., Pending, Confirmed)."""
        ws_url = self._get_websocket_url("/trades/events")
        logger.debug(f"Connecting to all trades stream: {ws_url}")
        async with websockets.connect(ws_url) as websocket:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # Add parsing logic here, assuming parse_trade_event exists
                    yield parse_trade_event(data)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received non-JSON message on all trades stream: {message[:100]}..."
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing message from all trades stream: {e}. Message: {message[:100]}..."
                    )

    async def stream_depth(self, asset_id: AssetIdentifier) -> AsyncIterator[OrderBookDiff]:
        """Stream order book diff updates for a specific asset."""
        ws_url = self._get_websocket_url(f"/marketdepth/diff/{asset_id}")
        logger.debug(f"Connecting to depth stream for asset {asset_id}: {ws_url}")
        async with websockets.connect(ws_url) as websocket:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # Parse directly into the new OrderBookDiff model
                    diff = OrderBookDiff(**data)
                    yield diff
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received non-JSON message on depth stream ({asset_id}): {message[:100]}..."
                    )
                except ValidationError as e:  # Catch Pydantic validation errors
                    logger.error(
                        f"Failed to validate OrderBookDiff data: {e}. Message: {message[:100]}..."
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing message from depth stream ({asset_id}): {e}. Message: {message[:100]}..."
                    )

    async def stream_klines(self, asset_id: AssetIdentifier) -> AsyncIterator[KlineUpdate]:
        """Stream K-line (candlestick) updates for a specific asset."""
        ws_url = self._get_websocket_url(f"/klines/diff/{asset_id}")
        logger.debug(f"Connecting to klines stream for asset {asset_id}: {ws_url}")
        async with websockets.connect(ws_url) as websocket:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # Add parsing logic here, assuming parse_kline_update exists
                    yield parse_kline_update(data)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received non-JSON message on klines stream ({asset_id}): {message[:100]}..."
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing message from klines stream ({asset_id}): {e}. Message: {message[:100]}..."
                    )

    # --- Async Context Management ---
    async def close(self) -> None:
        """Closes the underlying httpx async client."""
        logger.debug("Closing async HTTP client.")
        await self._client.aclose()  # Use aclose for AsyncClient

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
