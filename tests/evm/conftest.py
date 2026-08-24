from importlib.util import find_spec

import pytest

# Every module here needs the `evm` extra, the `accounts` fixture below included. Skip the
# directory rather than let each one fail to import.
if find_spec("ape") is None:
    collect_ignore_glob = ["*.py"]


@pytest.fixture
def signer(accounts):
    return accounts[0]
