import logging
from typing import Any, Optional

import httpx

# Assuming models and utils will be accessible from this path
# Adjust imports based on actual project structure
from tplus.model.asset_identifier import IndexAsset  # Assuming relative import
from tplus.model.order import Order, parse_orders
from tplus.model.orderbook import OrderBook
from tplus.model.trades import Trade, parse_trades
from tplus.utils.limit_order import create_limit_order
from tplus.utils.market_order import create_market_order
from tplus.utils.user import User

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class OrderBookClient:
    DEFAULT_TIMEOUT = 10.0 # Default request timeout

    def __init__(self, user: User, base_url: str, asset_index: int = 200, timeout: float = DEFAULT_TIMEOUT):
        self.user = user
        self.asset_index = asset_index
        self.base_url = base_url.rstrip('/')
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )

    def _request(self, method: str, endpoint: str, json_data: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Internal method to handle REST API requests."""
        relative_url = endpoint if endpoint.startswith('/') else f"/{endpoint}"
        try:
            response = self._client.request(
                method=method,
                url=relative_url,
                json=json_data,
            )
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            # Handle cases where the response might be empty (e.g., 204 No Content)
            if response.status_code == 204:
                return {}
            return response.json()
        except httpx.TimeoutException as e:
            # Re-raise or handle specific exceptions as needed
            logger.error(f"Request timed out to {e.request.url!r}: {e}")
            raise
        except httpx.RequestError as e:
            # Includes connection errors, read errors, etc.
            logger.error(f"An error occurred while requesting {e.request.url!r}: {type(e).__name__} - {e}")
            raise
        except httpx.HTTPStatusError as e:
            # Specific HTTP error status codes (4xx, 5xx)
            logger.error(f"HTTP error {e.response.status_code} while requesting {e.request.url!r}: {e.response.text}")
            # Potentially parse error details from e.response.json() if available
            raise

    def create_market_order(self, quantity: int, side: str, fill_or_kill: bool = False) -> dict[str, Any]:
        """
        Create and send a market order using the default asset index.

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
            asset_index=self.asset_index
        )
        signed_message_dict = message.to_dict()
        logger.info(f"Sending Market Order (Asset {self.asset_index}): Qty={quantity}, Side={side}, FOK={fill_or_kill}")
        return self._request("POST", "/orders/create", json_data=signed_message_dict)

    def create_limit_order(self, quantity: int, price: int, side: str, post_only: bool = True) -> dict[str, Any]:
        """
        Create and send a limit order using the default asset index.

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
        signed_message_dict = message.to_dict()
        logger.info(f"Sending Limit Order (Asset {self.asset_index}): Qty={quantity}, Price={price}, Side={side}, PostOnly={post_only}")
        return self._request("POST", "/orders/create", json_data=signed_message_dict)

    def parse_trades(self, trades_data: list[dict[str, Any]]) -> list[Trade]:
        """
        Parse trade data into Trade objects.

        Args:
            trades_data: List of trade dictionaries from the API

        Returns:
            List of Trade objects
        """
        return parse_trades(trades_data)

    def get_orderbook_snapshot(self, asset_id: IndexAsset) -> OrderBook:
        """
        Get a snapshot of the order book for a given asset.

        Args:
            asset_id: The asset identifier (IndexAsset).

        Returns:
            An OrderBook object representing the snapshot.
        """
        asset_index = asset_id.Index
        endpoint = f"/marketdepth/{asset_index}"
        logger.info(f"Getting Order Book Snapshot for asset {asset_index}")
        response = self._request("GET", endpoint)
        # Assuming the response dict structure matches OrderBook constructor
        # Example: {'asks': [[price, qty], ...], 'bids': [[price, qty], ...], 'sequence_number': num}
        # If the API response structure is different, adjust parsing accordingly.
        try:
            return OrderBook(**response)
        except TypeError as e:
            logger.error(f"Failed to parse order book snapshot response into OrderBook object: {e}. Response: {response}")
            raise ValueError(f"Could not parse API response for order book snapshot: {response}") from e

    def get_klines(self, asset_id: IndexAsset) -> dict[str, Any]:
        """
        Get K-line (candlestick) data for a given asset.

        Args:
            asset_id: The asset identifier (IndexAsset).

        Returns:
            The K-line data dictionary from the API.
        """
        asset_index = asset_id.Index
        endpoint = f"/klines/{asset_index}"
        logger.info(f"Getting Klines for asset {asset_index}")
        return self._request("GET", endpoint)

    def get_user_trades(self, user_id: str) -> list[Trade]:
        """
        Get all trades for a specific user.

        Args:
            user_id: The user's public key hex string.

        Returns:
            A list of Trade objects.
        """
        endpoint = f"/trades/user/{user_id}"
        logger.info(f"Getting Trades for user {user_id}")
        response_data = self._request("GET", endpoint)
        return self.parse_trades(response_data)

    def get_user_trades_for_asset(self, user_id: str, asset_id: IndexAsset) -> list[Trade]:
        """
        Get trades for a specific user and asset.

        Args:
            user_id: The user's public key hex string.
            asset_id: The asset identifier (IndexAsset).

        Returns:
            A list of Trade objects.
        """
        asset_index = asset_id.Index
        endpoint = f"/trades/user/{user_id}/{asset_index}"
        logger.info(f"Getting Trades for user {user_id}, asset {asset_index}")
        response_data = self._request("GET", endpoint)
        return self.parse_trades(response_data)

    def get_user_orders(self, user_id: str) -> list[Order]:
        """
        Get all orders for a specific user.

        Args:
            user_id: The user's public key hex string.

        Returns:
            A list of Order objects.
        """
        endpoint = f"/orders/user/{user_id}"
        logger.info(f"Getting Orders for user {user_id}")
        response_data = self._request("GET", endpoint)
        # Assuming parse_orders exists and handles the API response structure
        return parse_orders(response_data)

    def get_user_orders_for_book(self, user_id: str, asset_id: IndexAsset) -> list[Order]:
        """
        Get orders for a specific user and asset.

        Args:
            user_id: The user's public key hex string.
            asset_id: The asset identifier (IndexAsset).

        Returns:
            A list of Order objects.
        """
        asset_index = asset_id.Index
        endpoint = f"/orders/user/{user_id}/{asset_index}"
        logger.info(f"Getting Orders for user {user_id}, asset {asset_index}")
        response_data = self._request("GET", endpoint)
        # Assuming parse_orders exists and handles the API response structure
        return parse_orders(response_data)

    def get_user_inventory(self, user_id: str) -> dict[str, Any]:
        """
        Get inventory for a specific user.

        Args:
            user_id: The user's public key hex string.

        Returns:
            The inventory data dictionary from the API.
            (Consider creating an Inventory model for parsing)
        """
        endpoint = f"/inventory/user/{user_id}"
        logger.info(f"Getting Inventory for user {user_id}")
        return self._request("GET", endpoint)

    # --- Context Management ---
    def close(self) -> None:
        """Closes the underlying httpx client."""
        logger.info("Closing HTTP client.")
        self._client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
