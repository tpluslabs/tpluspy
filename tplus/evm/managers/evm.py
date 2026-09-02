from typing import TYPE_CHECKING, Any

from tplus.evm.backends import resolve_backend
from tplus.managers.base import BaseManager
from tplus.utils.user import is_evm_account, to_user

if TYPE_CHECKING:
    from collections.abc import Iterable

    from tplus.client.base import BaseClient
    from tplus.evm.backends.base import AccountLike, EVMBackend
    from tplus.types import UserLike
    from tplus.utils.user import EvmAccount, User


class ChainConnectedManager(BaseManager):
    """A base manager with access to the active EVM backend (``self.backend``)."""

    def _set_backend(self, backend: "EVMBackend | None" = None) -> None:
        self._backend_arg = backend
        self._resolved_backend: EVMBackend | None = None

    @property
    def backend(self) -> "EVMBackend":
        resolved = getattr(self, "_resolved_backend", None)
        if resolved is None:
            resolved = resolve_backend(getattr(self, "_backend_arg", None))
            self._resolved_backend = resolved

        return resolved


class ChainSigningManager(ChainConnectedManager):
    """
    A chain-connected manager that signs T+ requests as ``default_user`` and on-chain
    transactions as ``account``.

    Pass a signer as ``default_user`` to use it for both. ``default_user`` then starts
    as the identity derived from that account, which is a guess at which T+ account the
    wallet uses; :meth:`resolve_default_user` replaces it with the real one.
    """

    default_user: "User"
    account: Any
    _derived_from: "EvmAccount | None" = None
    """The wallet ``default_user`` was derived from, and so the one to resolve against.

    Not necessarily ``account``: that one may only be paying gas.
    """

    def __init__(
        self,
        default_user: "UserLike",
        account: "AccountLike | None" = None,
        backend: "EVMBackend | None" = None,
    ):
        self._set_backend(backend)
        if account is None:
            if not is_evm_account(default_user):
                raise ValueError("`account` is required unless `default_user` can sign.")

            account = default_user

        self.default_user = to_user(default_user)
        self.account = self.backend.get_account(account)
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
