import asyncio
import json
import logging

import httpx

# Adjust the import path based on your project structure
# Assumes 'tplus' is a package in your PYTHONPATH or installed
from tplus.client import OrderBookClient
from tplus.model.asset_identifier import IndexAsset
from tplus.utils.user import User

# Configure basic logging for the example
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s"
)
logger = logging.getLogger("RestExample")

# --- IMPORTANT: Replace with your actual API endpoint URL ---
# Use the correct URL for your running tplus-core instance
API_BASE_URL = "http://127.0.0.1:8000/"  # Example URL

# Example Asset ID to use
example_asset = IndexAsset(Index=200)  # Changed to keyword argument


async def main():
    user = User()
    logger.info(f"Using API Base URL: {API_BASE_URL}")
    logger.info(f"Example Asset Index: {example_asset.Index}")

    # Initialize client with the API base URL
    # Using async context manager ensures the client connection is closed properly
    try:
        async with OrderBookClient(user, base_url=API_BASE_URL) as client:
            logger.info("Client initialized.")

            # --- Simple GET Test First ---
            logger.info("=" * 20 + " Simple GET Test " + "=" * 20)
            logger.info(f"--- Getting Order Book Snapshot for asset {example_asset.Index} ---")
            try:
                orderbook = await client.get_orderbook_snapshot(example_asset)
                logger.info(
                    f"Order Book Snapshot ({example_asset.Index}): Sequence={orderbook.sequence_number}, Asks={len(orderbook.asks)}, Bids={len(orderbook.bids)}"
                )
                logger.info("Simple GET test SUCCEEDED.")
            except httpx.RequestError as e:
                logger.error(f"Simple GET test FAILED (Connection Error): {e}", exc_info=True)
                logger.warning("Skipping further tests as basic GET failed.")
                return
            except Exception as e:
                logger.error(f"Simple GET test FAILED: {e}", exc_info=True)
                logger.warning("Skipping further tests as basic GET failed.")
                return

            logger.info("\n" + "=" * 20 + " POST Endpoints " + "=" * 20)
            await asyncio.sleep(1)

            # --- Create Orders (POST) ---
            logger.info("--- Attempting Market Order ---")
            try:
                market_order_response = await client.create_market_order(
                    quantity=10, side="Buy", fill_or_kill=False
                )
                logger.info(f"Market Order Response: {json.dumps(market_order_response, indent=2)}")
            except Exception as e:
                logger.error(f"Market Order Failed: {e}", exc_info=True)

            await asyncio.sleep(0.5)

            logger.info("--- Attempting Limit Order ---")
            try:
                limit_order_response = await client.create_limit_order(
                    quantity=5,
                    price=1000,  # Example price, adjust as needed
                    side="Sell",
                    post_only=True,
                )
                logger.info(f"Limit Order Response: {json.dumps(limit_order_response, indent=2)}")
            except Exception as e:
                logger.error(f"Limit Order Failed: {e}", exc_info=True)

            logger.info("\n" + "=" * 20 + " GET Endpoints " + "=" * 20)
            await asyncio.sleep(1)

            user_id = user.pubkey()

            # --- Get Orders (GET) ---
            logger.info(f"--- Getting Orders for user {user_id} ---")
            try:
                # Unpack tuple
                user_orders, raw_orders_response = await client.get_user_orders(user_id)
                # Log raw response
                logger.info(
                    f"Raw User Orders Response ({user_id}): {json.dumps(raw_orders_response, indent=2)}"
                )
                # Log parsed orders (which might be empty due to parsing issues)
                logger.info(
                    f"Parsed User Orders ({user_id}): {json.dumps([o.model_dump() for o in user_orders], indent=2)}"
                )
            except Exception as e:
                logger.error(f"Get User Orders Failed: {e}", exc_info=True)

            await asyncio.sleep(0.5)

            logger.info(f"--- Getting Orders for user {user_id}, asset {example_asset.Index} ---")
            try:
                # Unpack tuple
                (
                    user_asset_orders,
                    raw_asset_orders_response,
                ) = await client.get_user_orders_for_book(user_id, example_asset)
                # Log raw response
                logger.info(
                    f"Raw User Asset Orders Response ({user_id}, {example_asset.Index}): {json.dumps(raw_asset_orders_response, indent=2)}"
                )
                # Log parsed orders
                logger.info(
                    f"Parsed User Asset Orders ({user_id}, {example_asset.Index}): {json.dumps([o.model_dump() for o in user_asset_orders], indent=2)}"
                )
            except Exception as e:
                logger.error(f"Get User Asset Orders Failed: {e}", exc_info=True)

            # --- Get Trades (GET) ---
            await asyncio.sleep(0.5)
            logger.info(f"--- Getting Trades for user {user_id} ---")
            try:
                user_trades = await client.get_user_trades(user_id)
                logger.info(
                    f"User Trades ({user_id}): {json.dumps([t.model_dump() for t in user_trades], indent=2)}"
                )
            except Exception as e:
                logger.error(f"Get User Trades Failed: {e}", exc_info=True)

            await asyncio.sleep(0.5)

            logger.info(f"--- Getting Trades for user {user_id}, asset {example_asset.Index} ---")
            try:
                user_asset_trades = await client.get_user_trades_for_asset(user_id, example_asset)
                logger.info(
                    f"User Asset Trades ({user_id}, {example_asset.Index}): {json.dumps([t.model_dump() for t in user_asset_trades], indent=2)}"
                )
            except Exception as e:
                logger.error(f"Get User Asset Trades Failed: {e}", exc_info=True)

            # --- Get Inventory (GET) ---
            await asyncio.sleep(0.5)
            logger.info(f"--- Getting Inventory for user {user_id} ---")
            try:
                inventory = await client.get_user_inventory(user_id)
                logger.info(f"User Inventory ({user_id}): {json.dumps(inventory, indent=2)}")
            except Exception as e:
                logger.error(f"Get User Inventory Failed: {e}", exc_info=True)

            # --- Get Market Data (GET) ---
            await asyncio.sleep(0.5)
            logger.info(f"--- Getting Klines for asset {example_asset.Index} ---")
            try:
                klines = await client.get_klines(example_asset)
                logger.info(f"Klines ({example_asset.Index}): {json.dumps(klines, indent=2)}")
            except Exception as e:
                logger.error(f"Get Klines Failed: {e}", exc_info=True)

    except httpx.RequestError as e:
        logger.critical(f"HTTP connection error during client setup: {e}", exc_info=True)
    except Exception as e:
        logger.critical(f"Failed to initialize or run client: {e}", exc_info=True)
    finally:
        logger.info("Example script finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")
