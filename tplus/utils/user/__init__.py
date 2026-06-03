from tplus.utils.user.manager import UserManager
from tplus.utils.user.model import LocalUser, User


def load_user(name: str | None = None, password: str | None = None) -> User:
    """Load a locally stored T+ user.

    Args:
        name: Name of the user to load. If ``None``, the default user is
            loaded -- either the one configured via
            :meth:`UserManager.set_default`, or the only stored user if
            exactly one exists.
        password: Password used to decrypt the keyfile. If ``None`` and a
            decrypt is required, the caller is prompted.

    Returns:
        The loaded :class:`User`.

    Raises:
        ValueError: If ``name`` is ``None`` and no users are stored locally.
    """
    manager = UserManager()
    if name:
        return manager.load(name, password=password)
    elif default_user := manager.load_default(password=password):
        # NOTE: If there is only 1 user, it is automatically 'the default'.
        return default_user

    raise ValueError("No default user; please add a user.")


__all__ = ("LocalUser", "User", "UserManager", "load_user")
