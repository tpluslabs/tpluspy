import pytest

from tplus.client import BlockchainClient

# Same operator secret used by ce.toml / the CE admin-auth test.
OPERATOR_SECRET = "afa3fd40eafd3703780358990983f75930c87744455bf18a472012a04ae521ff"


@pytest.fixture
def operator_secret():
    return OPERATOR_SECRET


@pytest.fixture
def blockchain_client(mocker):
    """A BlockchainClient with its HTTP ``_post`` mocked out."""
    client = BlockchainClient(base_url="http://127.0.0.1:8080")
    mocker.patch.object(client, "_post", new=mocker.AsyncMock(return_value={}))
    return client
