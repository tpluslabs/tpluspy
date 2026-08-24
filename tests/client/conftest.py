import pytest

from tplus.client import BlockchainClient


@pytest.fixture
def blockchain_client(mocker):
    """A BlockchainClient with its HTTP ``_post`` mocked out."""
    client = BlockchainClient(base_url="http://127.0.0.1:8080")
    mocker.patch.object(client, "_post", new=mocker.AsyncMock(return_value={}))
    return client
