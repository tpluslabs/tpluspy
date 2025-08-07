from tplus.utils.user.manager import UserManager
from tplus.utils.user.model import User


def load_user(name: str | None = None, password: str | None = None) -> User:
    manager = UserManager()
    return manager.load_default() if name is None else manager.load(name, password=password)


__all__ = ("User", "UserManager")
