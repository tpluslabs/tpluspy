import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import httpx
import websockets
from pydantic import ValidationError

from tplus.model.asset_identifier import IndexAsset  # Assuming relative import
from tplus.model.klines import KlineUpdate, parse_kline_update
from tplus.model.order import OrderEvent, OrderResponse, parse_order_event, parse_orders
from tplus.model.orderbook import (
    OrderBook,
    OrderBookDiff,
)
from tplus.model.trades import Trade, TradeEvent, parse_trade_event, parse_trades
from tplus.utils.limit_order import create_limit_order
from tplus.utils.market_order import create_market_order
from tplus.utils.user import User

# Configure basic logging #TODO: make a separate tplus.logging module
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OrderBookClient:
    DEFAULT_TIMEOUT = 10.0  # Default request timeout

    def __init__(
        self, user: User, base_url: str, asset_index: int = 200, timeout: float = DEFAULT_TIMEOUT
    ):
        self.user = user
        self.asset_index = asset_index
        self.base_url = base_url.rstrip("/")
        # Store original base_url parts for WS construction
        self._parsed_base_url = urlparse(self.base_url)
        # Use AsyncClient now
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )

    # --- Async HTTP Request Handling ---
    async def _request(
        self, method: str, endpoint: str, json_data: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Internal method to handle asynchronous REST API requests."""
        relative_url = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        try:
            # Use await for the async client request
            response = await self._client.request(
                method=method,
                url=relative_url,
                json=json_data,
            )
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            # Handle cases where the response might be empty (e.g., 204 No Content)
            if response.status_code == 204:
                return {}
            # Response body might be empty even on 200 OK for some APIs
            if not response.content:
                return {}

            # Parse JSON and handle if the result is None (e.g., API returned "null")
            json_response = response.json()
            if json_response is None:
                logger.warning(
                    f"API endpoint {response.request.url!r} returned JSON null. Treating as empty dictionary."
                )
                return {}
            return json_response
        except httpx.TimeoutException as e:
            logger.error(f"Request timed out to {e.request.url!r}: {e}")
            raise
        except httpx.RequestError as e:
            logger.error(
                f"An error occurred while requesting {e.request.url!r}: {type(e).__name__} - {e}"
            )
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error {e.response.status_code} while requesting {e.request.url!r}: {e.response.text}"
            )
            raise
        except json.JSONDecodeError as e:
            logger.error(
                f"Failed to decode JSON response from {response.request.url!r}. Status: {response.status_code}. Content: {response.text[:100]}..."
            )
            raise ValueError(f"Invalid JSON received from API: {e}") from e

    # --- Async Order Creation Methods ---
    async def create_market_order(
        self, quantity: int, side: str, fill_or_kill: bool = False
    ) -> dict[str, Any]:
        """
        Create and send a market order using the default asset index (async).

        Args:
            quantity: Amount to buy/sell
            side: "Buy" or "Sell"
            fill_or_kill: Whether the order must be filled immediately or cancelled

        Returns:
            The API response dictionary.
        """
        message = create_market_order(
            quantity=quantity,
            side=side,
            signer=self.user,
            fill_or_kill=fill_or_kill,
            asset_index=self.asset_index,
        )
        signed_message_dict = message.model_dump()
        logger.info(
            f"Sending Market Order (Asset {self.asset_index}): Qty={quantity}, Side={side}, FOK={fill_or_kill}"
        )
        # Use await for the async request
        return await self._request("POST", "/orders/create", json_data=signed_message_dict)

    async def create_limit_order(
        self, quantity: int, price: int, side: str, post_only: bool = True
    ) -> dict[str, Any]:
        """
        Create and send a limit order using the default asset index (async).

        Args:
            quantity: Amount to buy/sell
            price: Limit price
            side: "Buy" or "Sell"
            post_only: Whether the order should only be posted to the order book (via GTC time_in_force)

        Returns:
            The API response dictionary.
        """
        message = create_limit_order(
            quantity=quantity,
            price=price,
            side=side,
            signer=self.user,
            asset_index=self.asset_index,
            # Assuming create_limit_order handles post_only logic internally
        )
        signed_message_dict = message.model_dump()
        logger.info(
            f"Sending Limit Order (Asset {self.asset_index}): Qty={quantity}, Price={price}, Side={side}, PostOnly={post_only}"
        )
        # Use await for the async request
        return await self._request("POST", "/orders/create", json_data=signed_message_dict)

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
    async def get_orderbook_snapshot(self, asset_id: IndexAsset) -> OrderBook:
        """
        Get a snapshot of the order book for a given asset (async).

        Args:
            asset_id: The asset identifier (IndexAsset).

        Returns:
            An OrderBook object representing the snapshot.
        """
        asset_index = asset_id.Index
        endpoint = f"/marketdepth/{asset_index}"
        logger.info(f"Getting Order Book Snapshot for asset {asset_index}")
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

    async def get_klines(self, asset_id: IndexAsset) -> dict[str, Any]:
        """
        Get K-line (candlestick) data for a given asset (async).

        Args:
            asset_id: The asset identifier (IndexAsset).

        Returns:
            The K-line data dictionary from the API.
        """
        asset_index = asset_id.Index
        endpoint = f"/klines/{asset_index}"
        logger.info(f"Getting Klines for asset {asset_index}")
        # Use await for the async request
        return await self._request("GET", endpoint)

    async def get_user_trades(self, user_id: str) -> list[Trade]:
        """
        Get all trades for a specific user (async).

        Args:
            user_id: The user's public key hex string.

        Returns:
            A list of Trade objects.
        """
        endpoint = f"/trades/user/{user_id}"
        logger.info(f"Getting Trades for user {user_id}")
        # Use await for the async request
        response_data = await self._request("GET", endpoint)
        # Parsing remains synchronous
        return self.parse_trades(response_data)

    async def get_user_trades_for_asset(self, user_id: str, asset_id: IndexAsset) -> list[Trade]:
        """
        Get trades for a specific user and asset (async).

        Args:
            user_id: The user's public key hex string.
            asset_id: The asset identifier (IndexAsset).

        Returns:
            A list of Trade objects.
        """
        asset_index = asset_id.Index
        endpoint = f"/trades/user/{user_id}/{asset_index}"
        logger.info(f"Getting Trades for user {user_id}, asset {asset_index}")
        # Use await for the async request
        response_data = await self._request("GET", endpoint)
        # Parsing remains synchronous
        return self.parse_trades(response_data)

    async def get_user_orders(self, user_id: str) -> tuple[list[OrderResponse], dict[str, Any]]:
        """
        Get all orders for a specific user (async).

        Args:
            user_id: The user's public key hex string.

        Returns:
            A tuple containing the list of parsed OrderResponse objects and the raw API response dictionary.
        """
        endpoint = f"/orders/user/{user_id}"
        logger.info(f"Getting Orders for user {user_id}")
        response_data = await self._request("GET", endpoint)
        parsed_orders = parse_orders(response_data)
        return parsed_orders, response_data

    async def get_user_orders_for_book(
        self, user_id: str, asset_id: IndexAsset
    ) -> tuple[list[OrderResponse], dict[str, Any]]:
        """
        Get orders for a specific user and asset (async).

        Args:
            user_id: The user's public key hex string.
            asset_id: The asset identifier (IndexAsset).

        Returns:
            A tuple containing the list of parsed OrderResponse objects and the raw API response dictionary.
        """
        asset_index = asset_id.Index
        endpoint = f"/orders/user/{user_id}/{asset_index}"
        logger.info(f"Getting Orders for user {user_id}, asset {asset_index}")
        response_data = await self._request("GET", endpoint)
        parsed_orders = parse_orders(response_data)
        return parsed_orders, response_data

    async def get_user_inventory(self, user_id: str) -> dict[str, Any]:
        """
        Get inventory for a specific user (async).

        Args:
            user_id: The user's public key hex string.

        Returns:
            The inventory data dictionary from the API.
            (Consider creating an Inventory model for parsing)
        """
        endpoint = f"/inventory/user/{user_id}"
        logger.info(f"Getting Inventory for user {user_id}")
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
        logger.info(f"Connecting to orders stream: {ws_url}")
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
        logger.info(f"Connecting to finalized trades stream: {ws_url}")
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
        logger.info(f"Connecting to all trades stream: {ws_url}")
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

    async def stream_depth(self, asset_id: IndexAsset) -> AsyncIterator[OrderBookDiff]:
        """Stream order book diff updates for a specific asset."""
        asset_index = asset_id.Index
        ws_url = self._get_websocket_url(f"/marketdepth/diff/{asset_index}")
        logger.info(f"Connecting to depth stream for asset {asset_index}: {ws_url}")
        async with websockets.connect(ws_url) as websocket:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # Parse directly into the new OrderBookDiff model
                    diff = OrderBookDiff(**data)
                    yield diff
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received non-JSON message on depth stream ({asset_index}): {message[:100]}..."
                    )
                except ValidationError as e:  # Catch Pydantic validation errors
                    logger.error(
                        f"Failed to validate OrderBookDiff data: {e}. Message: {message[:100]}..."
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing message from depth stream ({asset_index}): {e}. Message: {message[:100]}..."
                    )

    async def stream_klines(self, asset_id: IndexAsset) -> AsyncIterator[KlineUpdate]:
        """Stream K-line (candlestick) updates for a specific asset."""
        asset_index = asset_id.Index
        ws_url = self._get_websocket_url(f"/klines/diff/{asset_index}")
        logger.info(f"Connecting to klines stream for asset {asset_index}: {ws_url}")
        async with websockets.connect(ws_url) as websocket:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    # Add parsing logic here, assuming parse_kline_update exists
                    yield parse_kline_update(data)
                except json.JSONDecodeError:
                    logger.warning(
                        f"Received non-JSON message on klines stream ({asset_index}): {message[:100]}..."
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing message from klines stream ({asset_index}): {e}. Message: {message[:100]}..."
                    )

    # --- Async Context Management ---
    async def close(self) -> None:
        """Closes the underlying httpx async client."""
        logger.info("Closing async HTTP client.")
        await self._client.aclose()  # Use aclose for AsyncClient

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
