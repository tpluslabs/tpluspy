import asyncio
import logging

import websockets  # Import websocket exceptions

# Adjust the import path based on your project structure
# Assumes 'tplus' is a package in your PYTHONPATH or installed
from tplus.client import OrderBookClient
from tplus.model.asset_identifier import IndexAsset
from tplus.model.orderbook import OrderBookDiff
from tplus.model.trades import Trade  # Import specific model
from tplus.utils.user import User

# Configure basic logging for the example
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(name)s] %(message)s')
logger = logging.getLogger("WebSocketExample")

# --- IMPORTANT: Replace with your actual API endpoint URL ---
# Use the correct URL for your running tplus-core instance
API_BASE_URL = "http://127.0.0.1:8000/" # Example URL

# Example Asset ID to use
example_asset = IndexAsset(Index=200) # Fix instantiation: Use keyword argument

# --- Stream Handler Functions ---

async def listen_depth(client: OrderBookClient, asset: IndexAsset, max_messages: int = 10):
    """Connects to the depth diff stream and logs received messages."""
    logger.info(f"Connecting to Depth stream for asset {asset.Index}...")
    msg_count = 0
    try:
        # Expect OrderBookDiff objects now
        async for diff_update in client.stream_depth(asset):
            if isinstance(diff_update, OrderBookDiff):
                # Log info from the diff object
                logger.info(f"[Depth-{asset.Index}] Received Diff: Seq={diff_update.sequence_number}, Asks Count={len(diff_update.asks)}, Bids Count={len(diff_update.bids)}")
                # Optional: Log specific asks/bids if needed for debugging
                # logger.debug(f"[Depth-{asset.Index}] Asks: {diff_update.asks}")
                # logger.debug(f"[Depth-{asset.Index}] Bids: {diff_update.bids}")
            else:
                logger.warning(f"[Depth-{asset.Index}] Received unexpected data type: {type(diff_update)} - {diff_update}")

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

    # Removed signal handling setup - Not supported on Windows default loop

    try:
        async with OrderBookClient(user, base_url=API_BASE_URL) as client:
            logger.info("Client initialized.")

            # Create tasks for the stream listeners
            depth_task = asyncio.create_task(listen_depth(client, example_asset, max_messages=10))
            trades_task = asyncio.create_task(listen_finalized_trades(client, max_messages=5))
            # Add other stream tasks here if needed

            # Wait for all stream tasks to complete (or be cancelled by KeyboardInterrupt)
            logger.info("Starting stream listeners. Press Ctrl+C to stop.")
            try:
                await asyncio.gather(depth_task, trades_task)
            except asyncio.CancelledError:
                logger.info("Stream tasks cancelled.")
            finally:
                # Ensure tasks are cancelled if gather didn't finish normally
                if not depth_task.done():
                    depth_task.cancel()
                if not trades_task.done():
                    trades_task.cancel()
                # Wait briefly for cancellation
                await asyncio.gather(depth_task, trades_task, return_exceptions=True)
                logger.info("Stream listeners finished or cancelled.")

    except websockets.exceptions.ConnectionClosedError as e:
        logger.error(f"Initial WebSocket connection failed: {e}")
    except Exception as e:
        logger.critical(f"An unexpected error occurred in main: {e}", exc_info=True)
    # Client is closed automatically by async with block
    finally:
        logger.info("WebSocket example finished.")

if __name__ == "__main__":
    try:
        # asyncio.run handles KeyboardInterrupt automatically and cancels tasks
        asyncio.run(main())
    except KeyboardInterrupt:
        # This block will now catch Ctrl+C pressed during asyncio.run
        logger.info("Process interrupted by user (KeyboardInterrupt).")
