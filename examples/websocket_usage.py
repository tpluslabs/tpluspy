import asyncio
import logging
import signal  # To handle graceful shutdown

import websockets  # Import websocket exceptions

# Adjust the import path based on your project structure
# Assumes 'tplus' is a package in your PYTHONPATH or installed
from tplus.client import OrderBookClient
from tplus.model.asset_identifier import IndexAsset
from tplus.model.orderbook import PriceLevelUpdate  # Import specific model
from tplus.model.trades import Trade  # Import specific model
from tplus.utils.user import User

# Configure basic logging for the example
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s')
logger = logging.getLogger("WebSocketExample")

# --- IMPORTANT: Replace with your actual API endpoint URL ---
# Use the correct URL for your running tplus-core instance
API_BASE_URL = "http://127.0.0.1:8000/" # Example URL

# Example Asset ID to use
example_asset = IndexAsset(200) # Assuming asset index 200 for the example

# --- Stream Handler Functions ---

async def listen_depth(client: OrderBookClient, asset: IndexAsset, max_messages: int = 5):
    """Connects to the depth stream and logs received messages."""
    logger.info(f"Connecting to Depth stream for asset {asset.Index}...")
    msg_count = 0
    try:
        async for update in client.stream_depth(asset):
            if isinstance(update, PriceLevelUpdate):
                logger.info(f"[Depth-{asset.Index}] Received: Side={update.side}, Price={update.price_level}, Qty={update.quantity}")
            else:
                logger.warning(f"[Depth-{asset.Index}] Received unexpected data type: {type(update)} - {update}")

            msg_count += 1
            if msg_count >= max_messages:
                logger.info(f"[Depth-{asset.Index}] Received {max_messages} messages, stopping listener.")
                break
    except websockets.exceptions.ConnectionClosedError as e:
        logger.error(f"[Depth-{asset.Index}] Connection closed unexpectedly: {e}")
    except Exception as e:
        logger.error(f"[Depth-{asset.Index}] Error in stream: {e}", exc_info=True)
    finally:
        logger.info(f"[Depth-{asset.Index}] Listener finished.")

async def listen_finalized_trades(client: OrderBookClient, max_messages: int = 5):
    """Connects to the finalized trades stream and logs received messages."""
    logger.info("Connecting to Finalized Trades stream...")
    msg_count = 0
    try:
        async for trade in client.stream_finalized_trades():
            if isinstance(trade, Trade):
                # Use trade.to_dict() for cleaner logging if needed
                logger.info(f"[Trades-Finalized] Received Trade ID: {trade.trade_id}, Price: {trade.price}, Qty: {trade.quantity}, Buyer: {trade.is_buyer}")
            else:
                 logger.warning(f"[Trades-Finalized] Received unexpected data type: {type(trade)} - {trade}")

            msg_count += 1
            if msg_count >= max_messages:
                logger.info(f"[Trades-Finalized] Received {max_messages} messages, stopping listener.")
                break
    except websockets.exceptions.ConnectionClosedError as e:
        logger.error(f"[Trades-Finalized] Connection closed unexpectedly: {e}")
    except Exception as e:
        logger.error(f"[Trades-Finalized] Error in stream: {e}", exc_info=True)
    finally:
        logger.info("[Trades-Finalized] Listener finished.")

# --- Main Execution ---

async def main():
    user = User() # Create a user for potential future authenticated streams
    logger.info(f"Using API Base URL: {API_BASE_URL}")
    logger.info(f"Example Asset Index: {example_asset.Index}")

    # Graceful shutdown handling
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGINT, stop.set_result, None)
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    try:
        async with OrderBookClient(user, base_url=API_BASE_URL) as client:
            logger.info("Client initialized.")

            # Create tasks for the stream listeners
            depth_task = asyncio.create_task(listen_depth(client, example_asset, max_messages=10))
            trades_task = asyncio.create_task(listen_finalized_trades(client, max_messages=5))

            # Wait for either the tasks to complete or for a shutdown signal
            done, pending = await asyncio.wait(
                [depth_task, trades_task, stop],
                return_when=asyncio.FIRST_COMPLETED
            )

            logger.info("First task or stop signal completed. Cleaning up...")

            # If stop signal received, cancel pending tasks
            if stop.done():
                logger.info("Shutdown signal received, cancelling tasks.")
                for task in pending:
                    task.cancel()
                # Wait for cancellations to complete
                await asyncio.gather(*pending, return_exceptions=True)
            else:
                 # Check tasks that completed for errors
                for task in done:
                    if task.exception():
                        logger.error(f"Task raised an exception: {task.exception()}")

    except Exception as e:
        logger.critical(f"An unexpected error occurred in main: {e}", exc_info=True)
    finally:
        logger.info("WebSocket example finished.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")
