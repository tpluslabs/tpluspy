from typing import TYPE_CHECKING

try:
    from ape.utils.basemodel import ManagerAccessMixin
except ImportError:
    raise ImportError("Must have [evm] extras to use this manager.")

from tplus.managers.base import BaseManager
from tplus.utils.user import is_ape_account, is_evm_account, to_user

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ape.api.accounts import AccountAPI

    from tplus.client.base import BaseClient
    from tplus.types import UserLike
    from tplus.utils.user import EvmAccount, User


class ChainConnectedManager(BaseManager, ManagerAccessMixin):
    """
    A base manager with access to Ape managers.
    """


class ChainSigningManager(ChainConnectedManager):
    """
    A chain-connected manager that signs T+ requests as ``default_user`` and on-chain
    transactions as ``ape_account``.

    Pass an Ape account as ``default_user`` to use it for both. ``default_user`` then starts
    as the identity derived from that account, which is a guess at which T+ account the
    wallet uses; :meth:`resolve_default_user` replaces it with the real one.
    """

    default_user: "User"
    ape_account: "AccountAPI"
    _derived_from: "EvmAccount | None" = None
    """The wallet ``default_user`` was derived from, and so the one to resolve against.

    Not necessarily ``ape_account``: that one may only be paying gas.
    """

    def __init__(self, default_user: "UserLike", ape_account: "AccountAPI | None" = None):
        if ape_account is None:
            if not is_ape_account(default_user):
                raise ValueError(
                    "`ape_account` is required unless `default_user` is an Ape account."
                )

            ape_account = default_user

        self.default_user = to_user(default_user)
        self.ape_account = ape_account
        self._derived_from = default_user if is_evm_account(default_user) else None

    def _user_clients(self) -> "Iterable[BaseClient]":
        """Clients whose own default user has to follow this manager's; the first resolves it."""
        return ()

    async def resolve_default_user(self) -> "User":
        """The T+ account this manager acts for, looked up rather than assumed.

        Given a wallet instead of a user, ``default_user`` starts as the identity derived
        from that wallet, which is not the account the wallet already controls. Resolving
        swaps in the real one before anything is credited to it or signed for it, and is a
        no-op once the account is known.

        Returns:
            User: The account this manager acts for.

        Raises:
            ValueError: If the account was derived from a wallet and no client can look the
                real one up.
        """
        wallet = self._derived_from
        if wallet is None:
            return self.default_user

        clients = tuple(self._user_clients())
        if not clients:
            raise ValueError(
                f"Cannot tell which T+ account {wallet.address} uses. Give this manager a "
                "service client to look it up, or pass an explicit `default_user`."
            )

        self.default_user = await clients[0].resolve_evm_user(wallet)
        self._derived_from = None
        for client in clients:
            client.set_default_user(self.default_user)

        return self.default_user
