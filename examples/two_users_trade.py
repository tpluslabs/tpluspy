import asyncio
import logging
import os

from tplus.client import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.utils.user import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("TwoUsersTradeExample")

# ---------------------------------------------------------------------------
# Configuration – adjust to match your running OMS instance
# ---------------------------------------------------------------------------
API_BASE_URL = os.getenv("TPLUS_API", "http://127.0.0.1:8000")

# Use a simple index-based asset. 200 is the default that ships with the
# docker-compose setup. Replace it with your own if necessary.
ASSET_ID_STR = os.getenv("ASSET_ID", "200")


async def main() -> None:
    # -----------------------------------------------------------------------
    # Bootstrap – create two independent users & corresponding API clients
    # -----------------------------------------------------------------------
    asset_id = AssetIdentifier(ASSET_ID_STR)

    user_a = User()
    user_b = User()

    logger.info("User A pk=%s", user_a.public_key)
    logger.info("User B pk=%s", user_b.public_key)
    logger.info("Connecting to OMS at %s", API_BASE_URL)

    async with (
        OrderBookClient(user_a, base_url=API_BASE_URL) as client_a,
        OrderBookClient(user_b, base_url=API_BASE_URL) as client_b,
    ):
        # -------------------------------------------------------------------
        # Ensure the market exists (idempotent – returns 409 if already there)
        # -------------------------------------------------------------------
        try:
            await client_a.create_market(asset_id)
            logger.info("Market %s created (or already existed)", asset_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("create_market failed (likely already exists): %s", exc)

        # Fetch market details to understand the decimal scaling factors
        market = await client_a.get_market(asset_id)
        qty_decimals = market.book_quantity_decimals
        price_decimals = market.book_price_decimals
        logger.info(
            "Market config – qty_decimals=%s price_decimals=%s", qty_decimals, price_decimals
        )

        # Helper lambdas to convert human-readable amounts to on-chain integers
        to_qty_units = lambda qty: int(qty * (10**qty_decimals))  # noqa: E731
        to_price_units = lambda price: int(price * (10**price_decimals))  # noqa: E731

        # -------------------------------------------------------------------
        # 1) USER A places a LIMIT SELL at a fixed price
        # -------------------------------------------------------------------
        human_qty = 0.01  # e.g. 0.01 ETH
        human_price = 3400.0  # e.g. 3 400 USDC
        limit_response = await client_a.create_limit_order(
            quantity=to_qty_units(human_qty),
            price=to_price_units(human_price),
            side="Sell",
            asset_id=asset_id,
        )
        logger.info("Limit order response (User A): %s", limit_response)

        # -------------------------------------------------------------------
        # 2) USER B places a MARKET BUY for the same base quantity
        # -------------------------------------------------------------------
        market_response = await client_b.create_market_order(
            side="Buy",
            base_quantity=to_qty_units(human_qty),
            asset_id=asset_id,
        )
        logger.info("Market order response (User B): %s", market_response)

        # -------------------------------------------------------------------
        # Optionally query each user's trades/orders afterwards
        # -------------------------------------------------------------------
        user_a_orders, _ = await client_a.get_user_orders()
        logger.info("User A now has %d orders", len(user_a_orders))
        logger.info("User A orders: %s", user_a_orders)
        user_b_orders, _ = await client_b.get_user_orders()
        logger.info("User B now has %d orders", len(user_b_orders))
        logger.info("User B orders: %s", user_b_orders)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user – exiting.")
