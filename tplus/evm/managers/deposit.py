import asyncio
from typing import TYPE_CHECKING, Any

from tplus.evm.contracts import DepositVault
from tplus.evm.managers.evm import ChainSigningManager
from tplus.model.types import ChainID
from tplus.utils.user import to_user_public_key

if TYPE_CHECKING:
    from collections.abc import Iterable

    from tplus.client.base import BaseClient
    from tplus.client.clearingengine import ClearingEngineClient
    from tplus.evm.backends.base import AccountLike, EVMBackend
    from tplus.types import UserLike, UserType


class DepositManager(ChainSigningManager):
    def __init__(
        self,
        account: "AccountLike",
        default_user: "UserLike | None" = None,
        vault: DepositVault | None = None,
        chain_id: ChainID | None = None,
        clearing_engine: "ClearingEngineClient | None" = None,
        *,
        backend: "EVMBackend | None" = None,
    ):
        super().__init__(default_user if default_user is not None else account, account, backend)
        self.chain_id = chain_id or ChainID.evm(self.backend.chain_id)
        self.ce = clearing_engine
        self.vault = vault if vault else DepositVault(chain_id=self.chain_id, backend=self.backend)

    def _user_clients(self) -> "Iterable[BaseClient]":
        return (self.ce,) if self.ce is not None else ()

    async def deposit(
        self,
        token: Any,
        amount: int,
        wait: bool = False,
        user: "UserType | None" = None,
    ):
        """Deposit ``amount`` of ``token`` into the vault, credited to a T+ account.

        Credits the resolved :meth:`~tplus.evm.managers.evm.ChainSigningManager.resolve_default_user`
        unless ``user`` names another account, so a wallet's own T+ account is credited
        rather than an identity derived from it.
        """
        if user is not None:
            pubkey = to_user_public_key(user)
        else:
            pubkey = (await self.resolve_default_user()).public_key

        self.vault.deposit(pubkey, token, amount, sender=self.account)

        if wait:
            # The CE ingests the deposit via vault-event subscriptions; just give
            # it a moment since there is no "get deposit" API to poll.
            await asyncio.sleep(3)
