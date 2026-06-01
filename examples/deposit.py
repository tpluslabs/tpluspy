import asyncio
import time

from ape import networks
from ape.cli import select_account
from ape_tokens.testing import MockERC20

from tplus.evm.contracts import vault
from tplus.utils.user import load_user

USERNAME = "az"
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


async def main():
    # Load your accounts.
    tplus_user = load_user(USERNAME)
    blockchain_user = select_account(
        f"Select your ETH account (chain={CHAIN_ID}) use to deposit to the vault contract"
    )

    # The CE ingests the on-chain deposit via vault-event subscriptions.
    deposit_to_chain(blockchain_user, tplus_user)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
