import json

import httpx
import pytest
from eth_account import Account

# These cover Ape/T+ account interop specifically, so they need the `evm-ape` extra.
pytest.importorskip("ape")

from tests.client.user_argument import (
    check_read_call_uses_derived_user,
    check_read_call_with_per_call_user,
    check_signed_call_uses_derived_key,
)
from tplus.client.clearingengine import ClearingEngineClient
from tplus.evm.managers.deposit import DepositManager
from tplus.evm.managers.evm import ChainSigningManager
from tplus.utils.user import User, load_user_from_ape_account, to_user


def test_from_ape_account_matches_from_eth_account(signer):
    """The Ape and ``eth_account`` paths derive the same T+ user from one EVM key."""
    ape_user = User.from_ape_account(signer)
    eth_user = User.from_eth_account(Account.from_key(signer.private_key))

    assert ape_user.public_key == eth_user.public_key
    assert ape_user.evm_address == signer.address


def test_load_user_from_ape_account_alias(signer, mocker):
    mocker.patch("ape.accounts.load", return_value=signer)

    user = load_user_from_ape_account("antazoey")

    assert user.public_key == User.from_ape_account(signer).public_key


def test_to_user_ape_account(signer):
    assert to_user(signer).public_key == User.from_ape_account(signer).public_key


@pytest.mark.anyio
async def test_get_user_inventory_ape_account_as_default_user(signer, build_client):
    await check_read_call_uses_derived_user(signer, build_client)


@pytest.mark.anyio
async def test_get_user_inventory_ape_account_as_user_argument(signer, build_client):
    await check_read_call_with_per_call_user(signer, build_client)


@pytest.mark.anyio
async def test_cancel_order_ape_account_as_default_user(signer, build_client):
    await check_signed_call_uses_derived_key(signer, build_client)


def test_chain_signing_manager_derives_user_from_ape_account(signer):
    manager = ChainSigningManager(signer)

    assert manager.account is signer
    assert manager.default_user.public_key == User.from_ape_account(signer).public_key


def test_chain_signing_manager_requires_an_account():
    with pytest.raises(ValueError, match="`account` is required"):
        ChainSigningManager(User())


def test_chain_signing_manager_keeps_separate_default_user(accounts, signer):
    """The T+ signer and the chain signer stay independent when both are given."""
    gas_payer = accounts[1]
    alice = User()

    manager = ChainSigningManager(default_user=alice, account=gas_payer)

    assert manager.default_user is alice
    assert manager.account is gas_payer
    assert manager.default_user.public_key != User.from_ape_account(gas_payer).public_key


def test_deposit_manager_separate_default_user(accounts, signer):
    alice = User()
    manager = DepositManager(account=signer, default_user=alice)

    assert manager.default_user is alice
    assert manager.account is signer


@pytest.mark.anyio
async def test_deposit_manager_credits_the_wallets_own_account(signer, mocker):
    """A wallet with a T+ account gets credited there, not on its derived identity."""
    account_id = "cd" * 32

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/multisig/signers"
        return httpx.Response(200, json=[account_id])

    ce = ClearingEngineClient(
        "http://test",
        client=httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)),
    )
    manager = DepositManager(account=signer, clearing_engine=ce)
    deposit = mocker.patch.object(manager.vault, "deposit")

    await manager.deposit("0xToken", 100)

    credited = deposit.call_args.args[0]
    assert credited == account_id
    assert credited != User.from_ape_account(signer).public_key

    await ce.close()


@pytest.mark.anyio
async def test_deposit_manager_will_not_guess_the_account(signer):
    """With nothing to look the account up against, refuse rather than credit a guess."""
    manager = DepositManager(account=signer)

    with pytest.raises(ValueError, match="Cannot tell which T\\+ account"):
        await manager.deposit("0xToken", 100)


@pytest.mark.anyio
async def test_manager_resolves_the_trading_wallet_not_the_gas_payer(accounts, signer, mocker):
    """With two wallets, the account is looked up for the one that signs, not the one paying."""
    from tplus.utils.user.evm import recover_signer_key
    from tplus.utils.user.model import sign_master_key_message

    gas_payer = accounts[1]
    trader_account = "cd" * 32
    gas_payer_account = "ef" * 32
    accounts_by_key = {
        bytes(recover_signer_key(sign_master_key_message(signer))): [trader_account],
        bytes(recover_signer_key(sign_master_key_message(gas_payer))): [gas_payer_account],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        key = bytes(json.loads(request.read())["Secp256k1"])
        return httpx.Response(200, json=accounts_by_key.get(key, []))

    ce = ClearingEngineClient(
        "http://test",
        client=httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)),
    )
    manager = DepositManager(account=gas_payer, default_user=signer, clearing_engine=ce)
    deposit = mocker.patch.object(manager.vault, "deposit")

    await manager.deposit("0xToken", 100)

    assert deposit.call_args.args[0] == trader_account
    assert manager.account is gas_payer
    await ce.close()
