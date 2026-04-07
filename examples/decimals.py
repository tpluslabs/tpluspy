import asyncio
import time
from pprint import pprint

from tplus.client import ClearingEngineClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.utils.user import User

CLEARING_ENGINE_HOST = "http://127.0.0.1:3032"


async def main():
    client = ClearingEngineClient(CLEARING_ENGINE_HOST, default_user=User())
    assets: list[AssetIdentifier | str] = [
        AssetIdentifier("0xf3c3351d6bd0098eeb33ca8f830faf2a141ea2e1@421614")
    ]

    await client.decimals.update(assets)

    # Wait a bit.
    time.sleep(4)

    decimals = await client.decimals.get(assets)
    pprint(decimals)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
