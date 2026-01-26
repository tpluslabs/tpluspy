import pytest

from tplus.client import ClearingEngineClient
from tplus.model.types import ChainID
from tplus.utils.user import User


@pytest.fixture(scope="module")
def user() -> User:
    return User()


@pytest.fixture(scope="module")
def clearing_engine(user):
    return ClearingEngineClient(user, "http://127.0.0.1:3032")


@pytest.fixture(scope="module")
def chain_id(user):
    """
    Default Anvil chain ID.
    """
    return ChainID.evm(31337)


@pytest.fixture(scope="module")
def vault_address():
    return "0x7a9eAA74eF31ed3eca5447252b443651Ad250916"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_approved_settlers(clearing_engine, chain_id, vault_address):
    """
    Ensure we get a 200 response when requesting an update of approved settlers.
    """
    await clearing_engine.settlements.update_approved_settlers(chain_id, vault_address)
    # ^ Happy path is that the test does not fail.
    with pytest.raises(ValueError):
        # However, it does fail if using integer based chain ID as the routing ID isn't present.
        await clearing_engine.settlements.update_approved_settlers(31337, vault_address)
