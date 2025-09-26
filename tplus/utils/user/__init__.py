from tplus.utils.user.manager import UserManager
from tplus.utils.user.model import User


def load_user(name: str | None = None, password: str | None = None) -> User:
    manager = UserManager()
    if name:
        return manager.load(name, password=password)
    elif default_user := manager.load_default(password=password):
        # NOTE: If there is only 1 user, it is automatically 'the default'.
        return default_user

    raise ValueError("No default user; please add a user.")


__all__ = ("User", "UserManager", "load_user")
