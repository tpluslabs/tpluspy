import asyncio

from ape.cli import select_account

from tplus.client import ClearingEngineClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.utils.user import load_user

USERNAME = "az"
CLEARING_ENGINE_HOST = "http://127.0.0.1:3032"
CHAIN_ID = 42161
ASSET_IN = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"
ASSET_OUT = "0x58372ab62269A52fA636aD7F200d93999595DCAF"


async def init_settlement(client, tplus_user):
    settlement = {
        "inner": {
            "tplus_user": tplus_user.public_key,
            "asset_in": AssetIdentifier(f"{ASSET_IN}@{CHAIN_ID}"),
            "amount_in": 100,
            "asset_out": AssetIdentifier(f"{ASSET_OUT}@{CHAIN_ID}"),
            "amount_out": 100,
            "chain_id": CHAIN_ID,
        },
        "signature": [],
    }
    await client.settlements.init_settlement(settlement)


def settle_on_chain(blockchain_user):
    raise NotImplementedError("TODO!")


async def main():
    tplus_user = load_user(USERNAME)
    blockchain_user = select_account(
        f"Select your ETH account (chain={CHAIN_ID}) use to settle on-chain"
    )

    client = ClearingEngineClient(tplus_user, CLEARING_ENGINE_HOST)

    await init_settlement(client, tplus_user)

    settle_on_chain(blockchain_user)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
