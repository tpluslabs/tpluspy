from unittest.mock import MagicMock

import pytest

from tplus.evm.managers.settle import SettlementInfo, SettlementManager
from tplus.logger import get_logger
from tplus.model.approval import SettlementApproval
from tplus.model.asset_identifier import AssetAddress
from tplus.model.types import ChainID
from tplus.utils.amount import Amount
from tplus.utils.user import User


def _approval(nonce: int) -> SettlementApproval:
    return SettlementApproval.model_validate(
        {"inner": {"nonce": nonce, "signature": "00"}, "expiry": 1}
    )


def _build_manager(approvals: list[SettlementApproval]) -> SettlementManager:
    manager = SettlementManager.__new__(SettlementManager)
    manager.default_user = User(sub_account=3)
    manager.chain_id = ChainID.evm(11155111)
    manager.logger = get_logger()
    manager._approval_handling_tasks = {}

    vault = MagicMock()
    vault.settlementCounts.side_effect = AssertionError(
        "init_settlement must not read on-chain settlementCounts"
    )
    manager.vault = vault
    manager.settlement_vault = vault

    queue = list(approvals)

    async def fake_init(_request):
        return queue.pop(0)

    manager._init_settlement = fake_init  # type: ignore[method-assign]
    return manager


@pytest.fixture
def settle_args():
    return {
        "asset_in": AssetAddress.from_evm_address(
            "0x62622E77D1349Face943C6e7D5c01C61465FE1dc", chain_id=11155111
        ),
        "amount_in": Amount(amount=1_000_000, decimals=6),
        "asset_out": AssetAddress.from_evm_address(
            "0x11fe4b6AE13d2a6055C8D9cF65c55bAc32B5d844", chain_id=11155111
        ),
        "amount_out": Amount(amount=500_000, decimals=6),
    }


@pytest.fixture
def manager():
    return _build_manager([_approval(42)])


@pytest.fixture
def back_to_back_manager():
    return _build_manager([_approval(7), _approval(8)])


@pytest.mark.anyio
async def test_init_settlement_uses_nonce_from_approval(manager, settle_args):
    info, result = await manager.init_settlement(**settle_args)

    assert isinstance(info, SettlementInfo)
    assert info.nonce == 42
    assert result.inner.nonce == 42
    manager.vault.settlementCounts.assert_not_called()


@pytest.mark.anyio
async def test_back_to_back_settlements_get_distinct_nonces(back_to_back_manager, settle_args):
    first_info, _ = await back_to_back_manager.init_settlement(**settle_args)
    second_info, _ = await back_to_back_manager.init_settlement(**settle_args)

    assert first_info.nonce == 7
    assert second_info.nonce == 8
