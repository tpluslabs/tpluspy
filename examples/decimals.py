"""
Trigger and read back the CE-cached decimals for an on-chain ERC20 asset.
"""

import asyncio
import time
from pprint import pprint

from tplus.client import OrderBookClient
from tplus.model.asset_identifier import AssetAddress
from tplus.utils.user import User

OMS_HOST = "http://127.0.0.1:8000"

# Arbitrum Sepolia testnet ERC20.
TOKEN_ADDRESS = "0xf3c3351d6bd0098eeb33ca8f830faf2a141ea2e1"
CHAIN_ID = 421614

# Build the t+ asset address (`address@<9-byte-hex-chain-id>`) via the
# helper -- see docs/userguides/asset-identifiers.md.
ASSET = AssetAddress.from_evm_address(TOKEN_ADDRESS, chain_id=CHAIN_ID)


async def main() -> None:
    client = OrderBookClient(OMS_HOST, default_user=User())

    await client.assets.update_asset_decimals([ASSET])

    # The CE polls the chain asynchronously; wait briefly before reading.
    time.sleep(4)

    decimals = await client.assets.get_asset_decimals([ASSET])
    pprint(decimals)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
