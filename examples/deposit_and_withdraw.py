import asyncio

from tplus.client import ClearingEngineClient
from tplus.utils.user import load_user

USERNAME = "az"
CLEARING_ENGINE_HOST = "http://127.0.0.1:3032"


async def main():
    user = load_user(USERNAME)
    client = ClearingEngineClient(user, CLEARING_ENGINE_HOST)

    # Deposit into vault and update it in the clearing engine.
    await client.deposits.update(user.public_key, chain_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
