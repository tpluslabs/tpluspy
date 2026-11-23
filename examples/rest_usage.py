"""
End-to-end REST walkthrough for tpluspy.

Connects to one gateway URL, places orders through the owning OMS, and reads
private history from its paired MDS without configuring either backend address.
"""

import asyncio
import logging
import os

import httpx

from tplus.client import TplusApiClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.limit_order import GTC
from tplus.utils.user import User

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(name)s] %(message)s"
)
logger = logging.getLogger("RestExample")

# Point this at your gateway. The local e2e runner uses port 8085.
API_BASE_URL = os.getenv("TPLUS_API_BASE_URL", "http://127.0.0.1:8085")

# Asset to trade. Either a registry index (e.g. 200) or an `address@chain_id`
# string in the t+ 9-byte chain form -- see docs/userguides/asset-identifiers.md.
EXAMPLE_ASSET = AssetIdentifier(200)


async def main() -> None:
    user = User()
    logger.info("Using API base URL: %s", API_BASE_URL)
    logger.info("Trading asset: %s", EXAMPLE_ASSET)
    logger.info("Public key: %s", user.public_key)

    async with TplusApiClient(API_BASE_URL, default_user=user) as client:
        md_client = client.mds
        # ---------------- read-only sanity check ----------------
        try:
            book = await md_client.get_orderbook_snapshot(EXAMPLE_ASSET)
        except httpx.RequestError as err:
            logger.error("Cannot reach market data through %s: %s", API_BASE_URL, err)
            return

        logger.info(
            "Order book: seq=%s asks=%d bids=%d",
            book.sequence_number,
            len(book.asks),
            len(book.bids),
        )

        # Cache market metadata (decimals etc.) so subsequent calls don't refetch.
        market = await client.get_market(EXAMPLE_ASSET)
        logger.info(
            "Market: price_decimals=%s qty_decimals=%s",
            market.book_price_decimals,
            market.book_quantity_decimals,
        )

        # ---------------- create orders ----------------
        market_order = await client.create_market_order(
            asset_id=EXAMPLE_ASSET,
            side="Buy",
            base_quantity=10,
            fill_or_kill=False,
        )
        logger.info("Market order: %s", market_order.model_dump())

        limit_order = await client.create_limit_order(
            asset_id=EXAMPLE_ASSET,
            quantity=5,
            price=1_000,
            side="Sell",
            time_in_force=GTC(),
        )
        logger.info("Limit order: %s", limit_order.model_dump())

        # ---------------- read back state ----------------
        # Each of these uses the authenticated user's public key implicitly.
        orders, _raw = await client.get_user_orders()
        logger.info("User has %d orders", len(orders))

        open_orders = await client.get_open_orders_for_book(EXAMPLE_ASSET)
        logger.info("Open orders for %s: %d", EXAMPLE_ASSET, len(open_orders))

        trades = await md_client.get_user_trades_for_asset(EXAMPLE_ASSET, user=user)
        logger.info("User has %d trades on %s", len(trades), EXAMPLE_ASSET)

        inventory = await client.get_user_inventory()
        logger.info("Inventory keys: %s", list(inventory.keys()) if inventory else "<empty>")

        klines = await md_client.get_klines(EXAMPLE_ASSET, limit=20)
        logger.info(
            "Got %d klines%s",
            len(klines.items),
            " with another page" if klines.has_next_page else "",
        )

        # ---------------- cancel the resting limit order ----------------
        if limit_order.order_id:
            cancel_resp = await client.cancel_order(
                order_id=limit_order.order_id,
                asset_id=EXAMPLE_ASSET,
            )
            logger.info("Cancel response: %s", cancel_resp.model_dump())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
