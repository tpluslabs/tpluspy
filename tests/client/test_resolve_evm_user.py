import json

import httpx
import pytest

from tplus.client.orderbook import OrderBookClient
from tplus.utils.user import EvmDelegatedUser
from tplus.utils.user.evm import derive_legacy_signer_key, recover_signer_key
from tplus.utils.user.model import sign_master_key_message

TERMINAL_ACCOUNT = "cd" * 32
OTHER_ACCOUNT = "ef" * 32


@pytest.fixture
def signer_keys(eth_account):
    """The wallet key T+ registers today, and the derived one older frontends registered."""
    signature = sign_master_key_message(eth_account)
    return recover_signer_key(signature), derive_legacy_signer_key(signature)


@pytest.fixture
def build_signers_client():
    """Client whose ``/multisig/signers`` answers from a {compressed key: accounts} map."""

    def build(accounts_by_key: dict[bytes, list[str]]):
        looked_up: list[bytes] = []

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/multisig/signers"
            key = bytes(json.loads(request.read())["Secp256k1"])
            looked_up.append(key)
            return httpx.Response(200, json=accounts_by_key.get(key, []))

        transport = httpx.MockTransport(handler)
        httpx_client = httpx.AsyncClient(base_url="http://test", transport=transport)
        return OrderBookClient("http://test", client=httpx_client), looked_up

    return build


@pytest.mark.anyio
async def test_resolve_evm_user_adopts_the_looked_up_account(
    eth_account, eth_user, signer_keys, build_signers_client
):
    wallet_key, _ = signer_keys
    client, looked_up = build_signers_client({wallet_key: [TERMINAL_ACCOUNT]})

    user = await client.resolve_evm_user(eth_account)

    assert isinstance(user, EvmDelegatedUser)
    assert user.public_key == TERMINAL_ACCOUNT
    # The derived identity is not the account: adopting it would address the wrong user.
    assert user.public_key != eth_user.public_key
    assert looked_up == [wallet_key]

    await client.close()


@pytest.mark.anyio
async def test_resolve_evm_user_falls_back_to_the_legacy_signer_key(
    eth_account, signer_keys, build_signers_client
):
    wallet_key, legacy_key = signer_keys
    client, looked_up = build_signers_client({legacy_key: [TERMINAL_ACCOUNT]})

    user = await client.resolve_evm_user(eth_account)

    assert user.public_key == TERMINAL_ACCOUNT
    assert bytes(user.signer_key) == legacy_key
    assert looked_up == [wallet_key, legacy_key]

    await client.close()


@pytest.mark.anyio
async def test_resolve_evm_user_returns_derived_user_when_no_account_exists(
    eth_account, eth_user, build_signers_client
):
    client, _ = build_signers_client({})

    user = await client.resolve_evm_user(eth_account)

    assert not isinstance(user, EvmDelegatedUser)
    assert user.public_key == eth_user.public_key

    await client.close()


@pytest.mark.anyio
async def test_resolve_evm_user_keeps_the_master_key_for_a_tpluspy_account(
    eth_account, eth_user, signer_keys, build_signers_client
):
    # An account tpluspy created: its master is the derived key, so signing stays direct.
    wallet_key, _ = signer_keys
    client, _ = build_signers_client({wallet_key: [eth_user.public_key, OTHER_ACCOUNT]})

    user = await client.resolve_evm_user(eth_account)

    assert not isinstance(user, EvmDelegatedUser)
    assert user.sign("payload") == eth_user.sign("payload")

    await client.close()


@pytest.mark.anyio
async def test_resolve_evm_user_requires_a_choice_between_accounts(
    eth_account, signer_keys, build_signers_client
):
    wallet_key, _ = signer_keys
    client, _ = build_signers_client({wallet_key: [TERMINAL_ACCOUNT, OTHER_ACCOUNT]})

    with pytest.raises(ValueError, match="account_public_key"):
        await client.resolve_evm_user(eth_account)

    chosen = await client.resolve_evm_user(eth_account, account_public_key=OTHER_ACCOUNT)
    assert chosen.public_key == OTHER_ACCOUNT

    with pytest.raises(ValueError, match="does not sign for account"):
        await client.resolve_evm_user(eth_account, account_public_key="11" * 32)

    await client.close()
