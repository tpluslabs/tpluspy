import importlib.util

import pytest
from eth_account import Account

from tplus.client.orderbook import OrderBookClient
from tplus.model.types import UserPublicKey
from tplus.utils.user import User

# Parametrize ``@pytest.mark.anyio`` tests over the backends that are actually
# installed. Without this override, pytest-anyio's default fixture also runs
# the ``trio`` variant -- which fails with ``ModuleNotFoundError: trio`` when
# trio isn't on the path (e.g. running tests without the ``[test]`` extra).
_BACKENDS = ["asyncio"]
if importlib.util.find_spec("trio") is not None:
    _BACKENDS.append("trio")

# Signature vector cross-checked against the T+ frontend (viem `signMessage`) for this key.
# The frontend does not turn it into a user_id, so ETH_USER_ID pins tpluspy's own derivation.
ETH_KEY = "0x" + "11" * 32
ETH_USER_ID = "d8fdbbe4236696e7dc81a6872ccb94515839c5bc49b99eeeef46f52202cd3af7"

# Ed25519 vector: PRIVATE_KEY_HEX signing SIGNED_MESSAGE yields EXPECTED_SIG_HEX.
PRIVATE_KEY_HEX = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
PUBLIC_KEY_HEX = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
SIGNED_MESSAGE = "testmessage"
EXPECTED_SIG_HEX = (
    "8ac3a00dd2fd15fc8d15da0c9d6be551402a252e3bf3e7cb96898a33a431cca"
    "26028f5fc0593d9d36909fce914bacb9c0d845146274f74a99f558cac5a4ffc02"
)
PASSWORD = "hunter2"

# Matches the operator secret in the CE's ce.toml config.
OPERATOR_SECRET = "afa3fd40eafd3703780358990983f75930c87744455bf18a472012a04ae521ff"
CE_URL = "http://127.0.0.1:3032"
OMS_URL = "https://127.0.0.1:8000"


@pytest.fixture
def eth_account():
    return Account.from_key(ETH_KEY)


@pytest.fixture
def eth_user(eth_account) -> User:
    """The T+ user derived from :func:`eth_account`."""
    return User.from_eth_account(eth_account)


@pytest.fixture
def expected_user_id() -> UserPublicKey:
    return UserPublicKey(ETH_USER_ID)


@pytest.fixture
def private_key_hex() -> str:
    return PRIVATE_KEY_HEX


@pytest.fixture
def public_key_hex() -> str:
    return PUBLIC_KEY_HEX


@pytest.fixture
def signed_message() -> str:
    return SIGNED_MESSAGE


@pytest.fixture
def expected_sig_hex() -> str:
    return EXPECTED_SIG_HEX


@pytest.fixture
def password() -> str:
    return PASSWORD


@pytest.fixture
def operator_secret() -> str:
    return OPERATOR_SECRET


@pytest.fixture
def ce_url() -> str:
    return CE_URL


@pytest.fixture
def build_client(mocker):
    """Build an ``OrderBookClient`` with its transport mocked out.

    Returns a factory yielding ``(client, request)``, where ``request`` is the mock
    standing in for :meth:`BaseClient._request`. Calls arrive as
    ``(method, endpoint)`` positionally with the body in the ``json_data`` keyword.
    """

    def build(**kwargs):
        client = OrderBookClient("http://example.com", **kwargs)
        request = mocker.patch.object(
            client,
            "_request",
            new=mocker.AsyncMock(return_value={"order_id": "oid", "status": "Received"}),
        )
        return client, request

    return build


@pytest.fixture
def client_build(build_client):
    """The default ``(client, request)`` pair, for tests needing no client kwargs."""
    return build_client()


@pytest.fixture
def client(client_build):
    """The default client, for tests that never inspect the request."""
    return client_build[0]


@pytest.fixture(params=_BACKENDS)
def anyio_backend(request):
    return request.param
