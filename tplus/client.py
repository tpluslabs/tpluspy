import json
import time
from typing import Optional, List, Dict, Any
import httpx

# Assuming models and utils will be accessible from this path
# Adjust imports based on actual project structure
from tplus.model.asset_identifier import IndexAsset # Assuming relative import
from tplus.model.limit_order import LimitOrderDetails, GTC
from tplus.model.market_order import MarketOrderDetails
from tplus.model.order import Order, CreateOrderRequest # Keep Order import
from tplus.model.orderbook import OrderBook
from tplus.model.signed_message import ObRequest, SignedMessage
from tplus.model.trades import Trade, parse_trades
from tplus.utils.user import User
from tplus.utils.limit_order import create_limit_order
from tplus.utils.market_order import create_market_order

# Implementation for parse_order based on the provided example structure
def parse_order(data: dict) -> Optional[Order]:
    """Parses a single order dictionary from the API into an Order object."""
    if not isinstance(data, dict):
        print(f"Warning: parse_order expected a dict, got {type(data)}")
        return None
    try:
        # Extract base_asset information
        base_asset_data = data.get('base_asset')
        if not isinstance(base_asset_data, dict) or 'Index' not in base_asset_data:
            print(f"Warning: Invalid or missing 'base_asset' structure in order data: {data}")
            return None
        base_asset = IndexAsset(index=base_asset_data['Index'])

        # Construct the Order object
        # Ensure all required fields are present, handle optionals and defaults
        order = Order(
            order_id=data['order_id'], # Assuming order_id is always present
            base_asset=base_asset,
            side=data['side'], # Assuming side is always present
            limit_price=data.get('limit_price'), # Optional
            quantity=data['quantity'], # Assuming quantity is always present
            confirmed_filled_quantity=data.get('confirmed_filled_quantity', 0), # Default to 0 if missing
            pending_filled_quantity=data.get('pending_filled_quantity', 0),   # Default to 0 if missing
            good_until_timestamp_ns=data.get('good_until_timestamp_ns'), # Optional
            timestamp_ns=data['timestamp_ns'] # Assuming timestamp_ns is always present
        )
        return order
    except KeyError as e:
        print(f"Error parsing order data: Missing key {e}, data was: {data}")
        return None
    except Exception as e:
        print(f"Error parsing order data: {type(e).__name__} - {e}, data was: {data}")
        return None

# Updated parse_orders to use the implemented parse_order
def parse_orders(data: List[dict]) -> List[Order]:
    """Parses a list of order dictionaries into Order objects using parse_order."""
    if not isinstance(data, list):
        print(f"Warning: parse_orders expected a list, got {type(data)}. Returning empty list.")
        return []
    parsed = [parse_order(item) for item in data if isinstance(item, dict)]
    # Filter out None results from failed parsing in parse_order
    valid_orders = [order for order in parsed if order is not None]
    if len(valid_orders) != len(data):
        print(f"Warning: parse_orders filtered out {len(data) - len(valid_orders)} invalid/unparseable order entries.")
    return valid_orders


class OrderBookClient:
    DEFAULT_TIMEOUT = 10.0 # Default request timeout

    def __init__(self, user: User, base_url: str, asset_index: int = 200, timeout: float = DEFAULT_TIMEOUT):
        self.user = user
        self.asset_index = asset_index
        self.base_url = base_url.rstrip('/')
        self.orderbook = OrderBook()
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )

    def _request(self, method: str, endpoint: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
            print(f"Request timed out to {e.request.url!r}: {e}")
            raise
        except httpx.RequestError as e:
            # Includes connection errors, read errors, etc.
            print(f"An error occurred while requesting {e.request.url!r}: {type(e).__name__} - {e}")
            raise
        except httpx.HTTPStatusError as e:
            # Specific HTTP error status codes (4xx, 5xx)
            print(f"HTTP error {e.response.status_code} while requesting {e.request.url!r}: {e.response.text}")
            # Potentially parse error details from e.response.json() if available
            raise

    def create_market_order(self, quantity: int, side: str, fill_or_kill: bool = False) -> Dict[str, Any]:
        """
        Create and send a market order.

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
        print(f"Sending Market Order: {json.dumps(signed_message_dict, indent=2)}")
        # Assuming a standard /orders endpoint for creating orders
        return self._request("POST", "/orders/create", json_data=signed_message_dict)

    def create_limit_order(self, quantity: int, price: int, side: str, post_only: bool = True) -> Dict[str, Any]:
        """
        Create and send a limit order.

        Args:
            quantity: Amount to buy/sell
            price: Limit price
            side: "Buy" or "Sell"
            post_only: Whether the order should only be posted to the order book

        Returns:
            The API response dictionary.
        """
        message = create_limit_order(
            quantity=quantity,
            price=price,
            side=side,
            signer=self.user,
            asset_index=self.asset_index
            # Note: post_only is part of GTC time_in_force in create_limit_order utility
        )
        signed_message_dict = message.to_dict()
        print(f"Sending Limit Order: {json.dumps(signed_message_dict, indent=2)}")
        # Assuming a standard /orders endpoint for creating orders
        return self._request("POST", "/orders/create", json_data=signed_message_dict)

    def update_orderbook(self, asks: List[List[int]], bids: List[List[int]], sequence_number: int):
        """
        Update the local orderbook state.

        Args:
            asks: List of [price, quantity] for asks
            bids: List of [price, quantity] for bids
            sequence_number: The sequence number of this update
        """
        self.orderbook = OrderBook(asks=asks, bids=bids, sequence_number=sequence_number)

    def get_orderbook(self) -> OrderBook:
        """
        Get the current orderbook state.

        Returns:
            The current OrderBook instance
        """
        return self.orderbook

    def parse_trades(self, trades_data: List[Dict[str, Any]]) -> List[Trade]:
        """
        Parse trade data into Trade objects.

        Args:
            trades_data: List of trade dictionaries

        Returns:
            List of Trade objects
        """
        return parse_trades(trades_data)

    def get_orderbook_snapshot(self, asset_id: IndexAsset) -> Dict[str, Any]:
        """
        Get a snapshot of the order book for a given asset.

        Args:
            asset_id: The asset identifier (IndexAsset).

        Returns:
            The order book data dictionary from the API.
            (Could be parsed into OrderBook object if structure matches)
        """
        asset_index = asset_id.Index
        endpoint = f"/marketdepth/{asset_index}"
        print(f"Getting Order Book Snapshot for asset {asset_index}")
        response = self._request("GET", endpoint)
        # Potentially parse into OrderBook object here if response format is known
        # e.g., return OrderBook(**response)
        return response

    def get_klines(self, asset_id: IndexAsset) -> Dict[str, Any]:
        """
        Get K-line (candlestick) data for a given asset.

        Args:
            asset_id: The asset identifier (IndexAsset).

        Returns:
            The K-line data dictionary from the API.
        """
        asset_index = asset_id.Index
        endpoint = f"/klines/{asset_index}"
        print(f"Getting Klines for asset {asset_index}")
        return self._request("GET", endpoint)

    def get_user_trades(self, user_id: str) -> List[Trade]:
        """
        Get all trades for a specific user.

        Args:
            user_id: The user's public key hex string.

        Returns:
            A list of Trade objects.
        """
        endpoint = f"/trades/user/{user_id}"
        print(f"Getting Trades for user {user_id}")
        response_data = self._request("GET", endpoint)
        # Assuming the response is a list of trade dictionaries
        return parse_trades(response_data)

    def get_user_trades_for_asset(self, user_id: str, asset_id: IndexAsset) -> List[Trade]:
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
        print(f"Getting Trades for user {user_id}, asset {asset_index}")
        response_data = self._request("GET", endpoint)
        # Assuming the response is a list of trade dictionaries
        return parse_trades(response_data)

    def get_user_orders(self, user_id: str) -> List[Order]:
        """
        Get all orders for a specific user.

        Args:
            user_id: The user's public key hex string.

        Returns:
            A list of Order objects (parsing needed).
        """
        endpoint = f"/orders/user/{user_id}"
        print(f"Getting Orders for user {user_id}")
        response_data = self._request("GET", endpoint)
        # Needs proper parsing based on API response structure
        return parse_orders(response_data)

    def get_user_orders_for_book(self, user_id: str, asset_id: IndexAsset) -> List[Order]:
        """
        Get orders for a specific user and asset.

        Args:
            user_id: The user's public key hex string.
            asset_id: The asset identifier (IndexAsset).

        Returns:
            A list of Order objects (parsing needed).
        """
        asset_index = asset_id.Index
        endpoint = f"/orders/user/{user_id}/{asset_index}"
        print(f"Getting Orders for user {user_id}, asset {asset_index}")
        response_data = self._request("GET", endpoint)
        # Needs proper parsing based on API response structure
        return parse_orders(response_data)

    def get_user_inventory(self, user_id: str) -> Dict[str, Any]:
        """
        Get inventory for a specific user.

        Args:
            user_id: The user's public key hex string.

        Returns:
            The inventory data dictionary from the API.
        """
        endpoint = f"/inventory/user/{user_id}"
        print(f"Getting Inventory for user {user_id}")
        return self._request("GET", endpoint)

    # --- Context Management ---
    def close(self) -> None:
        """Closes the underlying httpx client."""
        self._client.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Example usage (potentially move to a separate script or tests)
if __name__ == "__main__":
    # Create a new user
    user = User()

    # --- IMPORTANT: Replace with your actual API endpoint URL ---
    API_BASE_URL = "http://127.0.0.1:8000/" # Example URL

    # Example Asset ID to use
    example_asset = IndexAsset(200) # Assuming asset index 200

    # Initialize client with the API base URL
    # Using context manager ensures the client connection is closed properly
    with OrderBookClient(user, base_url=API_BASE_URL) as client:

        # --- Simple GET Test First ---
        print("="*20 + " Simple GET Test " + "="*20)
        try:
            print(f"\n--- Getting Order Book Snapshot for asset {example_asset.Index} ---")
            orderbook_snapshot = client.get_orderbook_snapshot(example_asset)
            print(f"Order Book Snapshot ({example_asset.Index}):", json.dumps(orderbook_snapshot, indent=2))
            print("Simple GET test SUCCEEDED.")
        except Exception as e:
            print(f"Simple GET test FAILED: {e}")
            print("Skipping further tests as basic GET failed.")
            # Optionally exit here if needed
            # exit()

        print("\n" + "="*20 + " POST Endpoints " + "="*20)
        time.sleep(1) # Pause before POST attempts

        # --- Create Orders (POST) ---
        try:
            print("--- Attempting Market Order ---")
            market_order_response = client.create_market_order(
                quantity=10,
                side="Buy",
                fill_or_kill=False
            )
            print("Market Order Response:", json.dumps(market_order_response, indent=2))
        except Exception as e:
            print(f"Market Order Failed: {e}")

        time.sleep(0.5) # Brief pause

        try:
            print("\n--- Attempting Limit Order ---")
            limit_order_response = client.create_limit_order(
                quantity=5,
                price=1000,
                side="Sell",
                post_only=True
            )
            print("Limit Order Response:", json.dumps(limit_order_response, indent=2))
        except Exception as e:
            print(f"Limit Order Failed: {e}")

        print("\n" + "="*20 + " GET Endpoints " + "="*20)
        time.sleep(1) # Longer pause before reads

        user_id = user.pubkey()

        # --- Get Orders (GET) ---
        try:
            print(f"\n--- Getting Orders for user {user_id} ---")
            user_orders = client.get_user_orders(user_id)
            print(f"User Orders ({user_id}):", json.dumps(user_orders, indent=2))
        except Exception as e:
            print(f"Get User Orders Failed: {e}")

        time.sleep(0.5)

        try:
            print(f"\n--- Getting Orders for user {user_id}, asset {example_asset.Index} ---")
            user_asset_orders = client.get_user_orders_for_book(user_id, example_asset)
            print(f"User Asset Orders ({user_id}, {example_asset.Index}):", json.dumps(user_asset_orders, indent=2))
        except Exception as e:
            print(f"Get User Asset Orders Failed: {e}")

        # --- Get Trades (GET) ---
        time.sleep(0.5)
        try:
            print(f"\n--- Getting Trades for user {user_id} ---")
            user_trades = client.get_user_trades(user_id)
            print(f"User Trades ({user_id}):", json.dumps([t.to_dict() for t in user_trades], indent=2) if user_trades else "[]")
        except Exception as e:
            print(f"Get User Trades Failed: {e}")

        time.sleep(0.5)

        try:
            print(f"\n--- Getting Trades for user {user_id}, asset {example_asset.Index} ---")
            user_asset_trades = client.get_user_trades_for_asset(user_id, example_asset)
            print(f"User Asset Trades ({user_id}, {example_asset.Index}):", json.dumps([t.to_dict() for t in user_asset_trades], indent=2) if user_asset_trades else "[]")
        except Exception as e:
            print(f"Get User Asset Trades Failed: {e}")

        # --- Get Inventory (GET) ---
        time.sleep(0.5)
        try:
            print(f"\n--- Getting Inventory for user {user_id} ---")
            inventory = client.get_user_inventory(user_id)
            print(f"User Inventory ({user_id}):", json.dumps(inventory, indent=2))
        except Exception as e:
            print(f"Get User Inventory Failed: {e}")

        # --- Get Market Data (GET) ---
        time.sleep(0.5)
        try:
            print(f"\n--- Getting Klines for asset {example_asset.Index} ---")
            klines = client.get_klines(example_asset)
            print(f"Klines ({example_asset.Index}):", json.dumps(klines, indent=2))
        except Exception as e:
            print(f"Get Klines Failed: {e}")

    print("\nClient closed.") 