import json
import time
import logging

# Adjust the import path based on your project structure
# Assumes 'tplus' is a package in your PYTHONPATH or installed
from tplus.client import OrderBookClient
from tplus.model.asset_identifier import IndexAsset
from tplus.utils.user import User

# Configure basic logging for the example
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Create a new user for the example
user = User()

# --- IMPORTANT: Replace with your actual API endpoint URL ---
# Use the correct URL for your running tplus-core instance
API_BASE_URL = "http://127.0.0.1:8000/" # Example URL

# Example Asset ID to use
example_asset = IndexAsset(200) # Assuming asset index 200 for the example

# Initialize client with the API base URL
# Using context manager ensures the client connection is closed properly
try:
    with OrderBookClient(user, base_url=API_BASE_URL) as client:

        # --- Simple GET Test First ---
        logging.info("="*20 + " Simple GET Test " + "="*20)
        try:
            logging.info(f"--- Getting Order Book Snapshot for asset {example_asset.Index} ---")
            # Now expects an OrderBook object
            orderbook = client.get_orderbook_snapshot(example_asset)
            # You might want to log orderbook.to_dict() or specific attributes
            logging.info(f"Order Book Snapshot ({example_asset.Index}): Sequence={orderbook.sequence_number}, Asks={len(orderbook.asks)}, Bids={len(orderbook.bids)}")
            logging.info("Simple GET test SUCCEEDED.")
        except Exception as e:
            logging.error(f"Simple GET test FAILED: {e}", exc_info=True)
            logging.warning("Skipping further tests as basic GET failed.")
            exit() # Exit if the basic connection/snapshot fails

        logging.info("\n" + "="*20 + " POST Endpoints " + "="*20)
        time.sleep(1) # Pause before POST attempts

        # --- Create Orders (POST) ---
        # Note: The client now uses its default asset_index (200) for these
        try:
            logging.info("--- Attempting Market Order ---")
            market_order_response = client.create_market_order(
                quantity=10,
                side="Buy",
                fill_or_kill=False
            )
            logging.info(f"Market Order Response: {json.dumps(market_order_response, indent=2)}")
        except Exception as e:
            logging.error(f"Market Order Failed: {e}", exc_info=True)

        time.sleep(0.5) # Brief pause

        try:
            logging.info("--- Attempting Limit Order ---")
            limit_order_response = client.create_limit_order(
                quantity=5,
                price=1000, # Example price, adjust as needed
                side="Sell",
                post_only=True
            )
            logging.info(f"Limit Order Response: {json.dumps(limit_order_response, indent=2)}")
        except Exception as e:
            logging.error(f"Limit Order Failed: {e}", exc_info=True)

        logging.info("\n" + "="*20 + " GET Endpoints " + "="*20)
        time.sleep(1) # Longer pause before reads

        user_id = user.pubkey() # Get the user's public key hex string

        # --- Get Orders (GET) ---
        # These methods now use parse_orders and return List[Order]
        try:
            logging.info(f"--- Getting Orders for user {user_id} ---")
            user_orders = client.get_user_orders(user_id)
            # Convert orders to dicts for logging if needed
            logging.info(f"User Orders ({user_id}): {json.dumps([o.to_dict() for o in user_orders], indent=2)}")
        except Exception as e:
            logging.error(f"Get User Orders Failed: {e}", exc_info=True)

        time.sleep(0.5)

        try:
            logging.info(f"--- Getting Orders for user {user_id}, asset {example_asset.Index} ---")
            user_asset_orders = client.get_user_orders_for_book(user_id, example_asset)
            logging.info(f"User Asset Orders ({user_id}, {example_asset.Index}): {json.dumps([o.to_dict() for o in user_asset_orders], indent=2)}")
        except Exception as e:
            logging.error(f"Get User Asset Orders Failed: {e}", exc_info=True)

        # --- Get Trades (GET) ---
        # These methods now use parse_trades and return List[Trade]
        time.sleep(0.5)
        try:
            logging.info(f"--- Getting Trades for user {user_id} ---")
            user_trades = client.get_user_trades(user_id)
            logging.info(f"User Trades ({user_id}): {json.dumps([t.to_dict() for t in user_trades], indent=2)}")
        except Exception as e:
            logging.error(f"Get User Trades Failed: {e}", exc_info=True)

        time.sleep(0.5)

        try:
            logging.info(f"--- Getting Trades for user {user_id}, asset {example_asset.Index} ---")
            user_asset_trades = client.get_user_trades_for_asset(user_id, example_asset)
            logging.info(f"User Asset Trades ({user_id}, {example_asset.Index}): {json.dumps([t.to_dict() for t in user_asset_trades], indent=2)}")
        except Exception as e:
            logging.error(f"Get User Asset Trades Failed: {e}", exc_info=True)

        # --- Get Inventory (GET) ---
        time.sleep(0.5)
        try:
            logging.info(f"--- Getting Inventory for user {user_id} ---")
            inventory = client.get_user_inventory(user_id) # Returns raw dict
            logging.info(f"User Inventory ({user_id}): {json.dumps(inventory, indent=2)}")
        except Exception as e:
            logging.error(f"Get User Inventory Failed: {e}", exc_info=True)

        # --- Get Market Data (GET) ---
        time.sleep(0.5)
        try:
            logging.info(f"--- Getting Klines for asset {example_asset.Index} ---")
            klines = client.get_klines(example_asset) # Returns raw dict
            logging.info(f"Klines ({example_asset.Index}): {json.dumps(klines, indent=2)}")
        except Exception as e:
            logging.error(f"Get Klines Failed: {e}", exc_info=True)

except Exception as e:
    logging.critical(f"Failed to initialize or run client: {e}", exc_info=True)

logging.info("Example script finished.") 