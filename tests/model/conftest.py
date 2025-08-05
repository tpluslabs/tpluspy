import pytest

from tplus.utils.user import User


@pytest.fixture(scope="session")
def user():
    return User()
