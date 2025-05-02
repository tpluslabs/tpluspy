import pytest


@pytest.fixture
def signer(accounts):
    return accounts[0]
