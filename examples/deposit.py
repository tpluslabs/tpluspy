import asyncio
import time

from ape import networks
from ape.cli import select_account
from ape_tokens.testing import MockERC20
from hexbytes import HexBytes

from tplus.client import ClearingEngineClient
from tplus.evm.contracts import vault
from tplus.utils.user import load_user

USERNAME = "az"
CLEARING_ENGINE_HOST = "http://127.0.0.1:3032"
CHAIN_ID = 11155111


async def deposit(blockchain_user, tplus_user, token, client):
    # Deposit into vault and update it in the clearing engine.
    with networks.ethereum.sepolia.use_provider("alchemy"):
        amount = 100
        balance = token.balanceOf(blockchain_user)
        if balance < amount:
            token.mint(blockchain_user, amount, sender=blockchain_user)

        token.approve(vault.contract, amount, sender=blockchain_user)

        vault.deposit(
            HexBytes(tplus_user.public_key),
            blockchain_user,
            "0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
            amount,
            sender=blockchain_user,
        )

    # Wait a bit before trying to sync.
    time.sleep(10)

    # Tell the CE to update deposit to ingest your new deposit.
    await client.deposits.update(tplus_user.public_key, CHAIN_ID)


async def withdraw(blockchain_user, tplus_user, client, token):
    with networks.ethereum.sepolia.use_provider("alchemy"):
        vault.withdraw(
            {"tokenAddress": token.address, "amount": 100},
        )


async def main():
    # Load your accounts.
    tplus_user = load_user(USERNAME)
    blockchain_user = select_account(
        f"Select your ETH account (chain={CHAIN_ID}) use to deposit to the vault contract"
    )

    token = MockERC20.at("0x62622E77D1349Face943C6e7D5c01C61465FE1dc")

    # Connect to the t+ clearing engine.
    client = ClearingEngineClient(tplus_user, CLEARING_ENGINE_HOST)

    await deposit(blockchain_user, tplus_user, token, client)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
