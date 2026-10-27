from importlib.util import find_spec
from unittest.mock import MagicMock

import httpx
import pytest

from tplus.client.oms.assetregistry import AssetRegistryClient
from tplus.client.withdrawal import WithdrawalClient
from tplus.evm.contracts import DepositVault
from tplus.evm.managers.withdraw import (
    SEEDED_DECIMALS_CACHE,
    WithdrawalInfo,
    WithdrawalManager,
)
from tplus.logger import get_logger
from tplus.model.approval import WithdrawalApproval
from tplus.model.asset_identifier import Address32, AssetAddress
from tplus.model.types import ChainID
from tplus.utils.amount import Amount
from tplus.utils.user import User
from tplus.utils.user.model import EvmAccount

CHAIN_ID = ChainID.evm(11155111)
USDC = AssetAddress.from_evm_address("0x62622e77d1349face943c6e7d5c01c61465fe1dc", CHAIN_ID)
TARGET = Address32("1111111111111111111111111111111111111111000000000000000000000000")
ONE_THOUSAND_INVENTORY = 1_000 * 10**18
ONE_THOUSAND_USDC = 1_000 * 10**6


def _build_manager(decimals: int = 6) -> WithdrawalManager:
    """
    Build a manager whose collaborators are ``spec_set`` mocks, so a call to a method the
    real class does not define fails here rather than at runtime against a live service.
    """
    manager = WithdrawalManager.__new__(WithdrawalManager)
    manager.default_user = User()
    manager.account = MagicMock(spec_set=EvmAccount)
    manager.chain_id = CHAIN_ID
    manager.logger = get_logger()

    manager._decimals_cache = dict(SEEDED_DECIMALS_CACHE)

    manager.vault = MagicMock(spec_set=DepositVault)
    manager.vault.get_withdrawal_count.return_value = 4

    manager.withdrawals = MagicMock(spec_set=WithdrawalClient)

    manager.registry_client = MagicMock(spec_set=AssetRegistryClient)
    manager.registry_client.get_asset_decimals.side_effect = lambda assets: {
        str(asset): decimals for asset in assets
    }
    return manager


@pytest.fixture
def manager():
    return _build_manager()


def _signed_request(manager: WithdrawalManager):
    return manager.withdrawals.init_withdrawal.await_args.args[0]


@pytest.mark.anyio
async def test_init_withdrawal_amount_with_decimals(manager):
    amount = Amount(amount=ONE_THOUSAND_USDC, decimals=6)

    info = await manager.init_withdrawal(USDC, amount, target=TARGET)

    assert _signed_request(manager).inner.amount == ONE_THOUSAND_INVENTORY
    assert info.amount == ONE_THOUSAND_INVENTORY


@pytest.mark.anyio
async def test_get_asset_decimals_caches_by_asset_key(manager):
    await manager.get_asset_decimals(USDC)
    await manager.get_asset_decimals(USDC)

    # The CE keys its decimals response by "<address>@<chain>".
    assert manager.registry_client.get_asset_decimals.await_args.args[0] == [USDC]
    assert manager.registry_client.get_asset_decimals.await_count == 1


@pytest.mark.anyio
async def test_get_asset_decimals_falls_back_when_absent(manager):
    manager.registry_client.get_asset_decimals.side_effect = lambda assets: {}
    manager.get_erc20_decimals = MagicMock(return_value=6)

    assert await manager.get_asset_decimals(USDC) == 6
    manager.get_erc20_decimals.assert_called_once_with(USDC)


@pytest.mark.anyio
async def test_get_asset_decimals_falls_back_when_registry_errors(manager):
    manager.registry_client.get_asset_decimals.side_effect = httpx.ConnectError("no route")
    manager.get_erc20_decimals = MagicMock(return_value=6)

    assert await manager.get_asset_decimals(USDC) == 6


@pytest.mark.anyio
async def test_get_asset_decimals_caches_fallback_result(manager):
    manager.registry_client.get_asset_decimals.side_effect = httpx.ConnectError("no route")
    manager.get_erc20_decimals = MagicMock(return_value=6)

    await manager.get_asset_decimals(USDC)
    await manager.get_asset_decimals(USDC)

    manager.get_erc20_decimals.assert_called_once()


@pytest.mark.anyio
async def test_get_asset_decimals_uses_seeded_cache(manager):
    arbitrum_usdc = AssetAddress.from_evm_address(
        "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", ChainID.evm(42161)
    )

    assert await manager.get_asset_decimals(arbitrum_usdc) == 6
    manager.registry_client.get_asset_decimals.assert_not_awaited()


def test_build_seeded_decimals_cache_keys():
    # Every seed must be keyed the way get_asset_decimals looks assets up, or it never hits.
    assert SEEDED_DECIMALS_CACHE
    for key, decimals in SEEDED_DECIMALS_CACHE.items():
        assert str(AssetAddress.from_str(key)) == key
        assert decimals in (6, 18)


@pytest.mark.skipif(find_spec("ape_tokens") is None, reason="needs the evm-ape extra")
def test_get_erc20_decimals_reads_from_chain(manager, signer, chain):
    # Deploying a token needs Ape's contract fixtures, and its `chain` fixture.
    from ape_tokens.testing import MockERC20

    token = MockERC20.deploy(signer, "U.S. Dollar Coin", "USDC", 6, sender=signer)
    asset = AssetAddress.from_evm_address(token.address, ChainID.from_parts(0, chain.chain_id))

    assert manager.get_erc20_decimals(asset) == 6


def test_get_erc20_decimals_non_evm_asset(manager):
    solana_asset = AssetAddress.from_str(f"{'ab' * 32}@{ChainID.from_parts(1, 101)}")

    with pytest.raises(ValueError, match="non-EVM"):
        manager.get_erc20_decimals(solana_asset)


@pytest.mark.anyio
async def test_execute_withdrawal_uses_approval_amount(manager):
    info = WithdrawalInfo(
        asset=USDC,
        amount=ONE_THOUSAND_INVENTORY,
        nonce=4,
        target=TARGET,
        chain_id=CHAIN_ID,
    )
    approvals = [
        WithdrawalApproval.model_validate(
            {
                "inner": {"nonce": 4, "signature": "00"},
                "expiry": 1,
                "epoch_hash": [3] * 32,
                "amount": str(ONE_THOUSAND_USDC),
                "conversion": {
                    "canonical_per_representation": "1000000000000000000",
                    "state_id": "0x00",
                    "canonical_amount": str(ONE_THOUSAND_INVENTORY),
                    "representation_amount": str(ONE_THOUSAND_INVENTORY),
                    "chain_amount": str(ONE_THOUSAND_USDC),
                    "representation_remainder": "0",
                },
            }
        )
    ]

    await manager.execute_withdrawal(info, approvals)

    withdrawal, _, _, _, epoch_hash, _ = manager.vault.withdraw.call_args.args
    assert withdrawal["amount"] == ONE_THOUSAND_USDC
    assert epoch_hash == bytes([3] * 32)
    assert withdrawal["nonce"] == 4
