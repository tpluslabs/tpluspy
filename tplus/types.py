from tplus.model.types import UserPublicKey
from tplus.utils.user import EvmAccount, User

UserLike = User | EvmAccount
"""Anything that can sign as a T+ user: a :class:`~tplus.utils.user.User`, or an EVM account
(an Ape ``AccountAPI`` or an ``eth_account`` account) the T+ user is derived from."""

UserType = UserPublicKey | UserLike
"""A :data:`UserLike` signer, or a bare public key identifying a user in read-only calls."""
