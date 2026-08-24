from typing import TYPE_CHECKING, cast

from tplus.model.types import UserPublicKey
from tplus.utils.user.evm import EvmDelegatedUser
from tplus.utils.user.manager import UserManager, user_manager
from tplus.utils.user.model import (
    DelegatedUser,
    EvmAccount,
    LocalUser,
    User,
    coerce_account_public_key,
    is_ape_account,
    is_evm_account,
)

if TYPE_CHECKING:
    from tplus.types import UserLike, UserType


def load_user(name: str | None = None, password: str | None = None) -> User:
    """Load a locally stored T+ user.

    Args:
        name (str | None): Name of the user to load. If ``None``, the default
            user is loaded: either the one configured via
            :meth:`UserManager.set_default`, or the only stored user if exactly
            one exists.
        password (str | None): Password used to decrypt the keyfile. If ``None``
            and a decrypt is required, the caller is prompted.

    Returns:
        User: The loaded user.

    Raises:
        ValueError: If ``name`` is ``None`` and no users are stored locally.
    """
    if name:
        return user_manager.load(name, password=password)
    elif default_user := user_manager.load_default(password=password):
        # NOTE: If there is only 1 user, it is automatically 'the default'.
        return default_user

    raise ValueError("No default user; please add a user.")


def load_user_from_ape_account(account: "str | EvmAccount", sub_account: int | None = None) -> User:
    """Load the T+ user backed by an Ape account. Requires the ``[evm]`` extra.

    The account signs a fixed message once and the T+ identity is derived from that
    signature, so the same EVM key always resolves to the same T+ user. This is a local
    derivation; to reach the account a wallet already controls, use
    :meth:`tplus.client.base.BaseClient.resolve_evm_user`.

    Args:
        account (str | EvmAccount): An Ape account alias, or a loaded ``AccountAPI``.
        sub_account (int | None): Optional sub-account index.

    Returns:
        User: The user backed by ``account``.
    """
    return user_manager.load_from_ape_account(account, sub_account=sub_account)


def to_user(user: "UserLike") -> User:
    """Coerce a user-like value into a :class:`User`.

    An EVM account, meaning an Ape ``AccountAPI`` or an ``eth_account`` account, is
    resolved via :meth:`UserManager.load_from_evm_account`; any other signer is returned
    as-is. Every ``user`` / ``default_user`` / ``signer`` argument in the library passes
    through here, which is what lets an EVM account be used anywhere a :class:`User` is.

    Args:
        user (UserLike): A user, or an EVM account backing one.

    Returns:
        User: The T+ user to sign with.

    Raises:
        TypeError: If ``user`` cannot sign (a bare public key).
    """
    if isinstance(user, str):
        raise TypeError(
            "Cannot sign with a public key: pass a `User`, an Ape account, or an "
            "`eth_account` account."
        )

    elif is_evm_account(user):
        return user_manager.load_from_evm_account(user)

    return cast(User, user)


def to_user_public_key(user: "UserType") -> UserPublicKey:
    """Resolve a user-like value, or a bare public key, to its public key.

    A bare key is normalized to the canonical form T+ compares against: lowercase 64-hex,
    no ``0x`` prefix.

    Args:
        user (UserType): A user, an EVM account backing one, or a hex public key.

    Returns:
        UserPublicKey: The user's public key.

    Raises:
        ValueError: If a bare key is not a 32-byte hex public key.
    """
    if isinstance(user, str):
        return coerce_account_public_key(user)

    return to_user(user).public_key


__all__ = (
    "DelegatedUser",
    "EvmAccount",
    "EvmDelegatedUser",
    "LocalUser",
    "User",
    "UserManager",
    "is_ape_account",
    "is_evm_account",
    "load_user",
    "load_user_from_ape_account",
    "to_user",
    "to_user_public_key",
    "user_manager",
)
