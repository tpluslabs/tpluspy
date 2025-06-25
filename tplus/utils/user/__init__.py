from tplus.utils.user.manager import UserManager
from tplus.utils.user.model import User


def load_user(name: str, password: str | None = None) -> User:
    return UserManager().load(name, password=password)


__all__ = ("User", "UserManager")
