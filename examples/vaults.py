import asyncio
from pprint import pprint

from tplus.client import ClearingEngineClient
from tplus.utils.user import load_user

USERNAME = "az"
CLEARING_ENGINE_HOST = "http://127.0.0.1:3032"


async def main():
    tplus_user = load_user(USERNAME)
    client = ClearingEngineClient(CLEARING_ENGINE_HOST, default_user=tplus_user)
    vault_addresses = await client.vaults.get()
    pprint(vault_addresses)

    await client.vaults.update()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
