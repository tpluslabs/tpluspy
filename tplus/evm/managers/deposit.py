import asyncio
from typing import TYPE_CHECKING

from tplus.evm.contracts import DepositVault
from tplus.evm.managers.evm import ChainConnectedManager

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.contracts.base import ContractInstance
    from ape.types.address import AddressType

    from tplus.client.clearingengine import ClearingEngineClient
    from tplus.utils.user import User


class DepositManager(ChainConnectedManager):
    def __init__(
        self,
        account: "AccountAPI",
        tplus_user: "User",
        vault: DepositVault | None = None,
        chain_id: int | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
    ):
        self.account = account
        self.tplus_user = tplus_user
        self.chain_id = chain_id or self.chain_manager.chain_id
        self.ce = clearing_engine
        self.vault = vault if vault else DepositVault(chain_id=self.chain_id)

    async def deposit(
        self, token: "str | AddressType | ContractInstance", amount: int, wait: bool = False
    ):
        self.vault.deposit(self.tplus_user.public_key, token, amount, sender=self.account)

        if wait:
            if not (ce := self.ce):
                raise ValueError("Must have clearing_engine to wait for deposit ingestion.")

            # There actually isn't a way to really wait for deposits since there isn't an API
            # to "get" them. Instead, just wait 3 seconds.
            await asyncio.sleep(3)
            await ce.deposits.update(self.tplus_user.public_key, self.chain_id)
