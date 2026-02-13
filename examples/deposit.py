import asyncio
import time

from ape import networks
from ape.cli import select_account
from ape_tokens.testing import MockERC20

from tplus.client import ClearingEngineClient
from tplus.evm.contracts import vault
from tplus.utils.user import load_user

USERNAME = "az"
CLEARING_ENGINE_HOST = "http://127.0.0.1:3032"
CHAIN_ID = 42161
TOKEN = "0x62622E77D1349Face943C6e7D5c01C61465FE1dc"


def deposit_to_chain(blockchain_user, tplus_user):
    with networks.ethereum.sepolia.use_provider("alchemy"):
        amount = 100
        token = MockERC20.at(TOKEN)

        # Ensure we have enough balance.
        balance = token.balanceOf(blockchain_user)
        if balance < amount:
            token.mint(blockchain_user, amount, sender=blockchain_user)

        token.approve(vault.contract, amount, sender=blockchain_user)

        vault.deposit(
            tplus_user.public_key,
            TOKEN,
            amount,
            sender=blockchain_user,
        )

    # Wait a bit before trying to sync.
    time.sleep(10)


async def deposit_to_ce(tplus_user, client):
    # Tell the CE to update deposit to ingest your new deposit.
    await client.deposits.update_nonce(tplus_user.public_key, CHAIN_ID)


async def main():
    # Load your accounts.
    tplus_user = load_user(USERNAME)
    blockchain_user = select_account(
        f"Select your ETH account (chain={CHAIN_ID}) use to deposit to the vault contract"
    )

    # Connect to the t+ clearing engine.
    client = ClearingEngineClient(tplus_user, CLEARING_ENGINE_HOST)

    deposit_to_chain(blockchain_user, tplus_user)
    await deposit_to_ce(tplus_user, client)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
