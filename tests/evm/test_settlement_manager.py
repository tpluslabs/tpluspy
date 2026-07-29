from unittest.mock import MagicMock

import pytest

from tplus.evm.managers.settle import SettlementInfo, SettlementManager
from tplus.logger import get_logger
from tplus.model.approval import SettlementApproval
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
    manager.init_requests = []

    vault = MagicMock()
    vault.settlementCounts.side_effect = [approval.inner.nonce for approval in approvals]
    manager.vault = vault
    manager.settlement_vault = vault

    queue = list(approvals)

    async def fake_init(request):
        manager.init_requests.append(request)
        return queue.pop(0)

    manager._init_settlement = fake_init  # type: ignore[method-assign]
    return manager


@pytest.fixture
def settle_args():
    return {
        "asset_in": "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000",
        "amount_in": Amount(amount=1_000_000, decimals=6),
        "asset_out": "11fe4b6ae13d2a6055c8d9cf65c55bac32b5d844000000000000000000000000",
        "amount_out": Amount(amount=500_000, decimals=6),
    }


@pytest.fixture
def manager():
    return _build_manager([_approval(42)])


@pytest.fixture
def back_to_back_manager():
    return _build_manager([_approval(7), _approval(8)])


@pytest.mark.anyio
async def test_init_settlement_signs_with_expected_nonce(manager, settle_args):
    info, result = await manager.init_settlement(**settle_args)

    assert isinstance(info, SettlementInfo)
    assert info.nonce == 42
    assert result.inner.nonce == 42
    assert manager.init_requests[0].inner.nonce == 42
    manager.vault.settlementCounts.assert_called_once_with(
        manager.default_user.public_key,
        manager.default_user.sub_account,
    )


@pytest.mark.anyio
async def test_back_to_back_settlements_get_distinct_nonces(back_to_back_manager, settle_args):
    first_info, _ = await back_to_back_manager.init_settlement(**settle_args)
    second_info, _ = await back_to_back_manager.init_settlement(**settle_args)

    assert first_info.nonce == 7
    assert second_info.nonce == 8
    assert [request.inner.nonce for request in back_to_back_manager.init_requests] == [7, 8]
