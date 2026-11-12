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


@pytest.fixture
def anyio_backend():
    # WithdrawalManager and its websocket fixtures use asyncio tasks and queues.
    return "asyncio"


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


def _approval_row(manager):
    return {
        "nonce": 4,
        "asset": str(USDC),
        "status": {
            "type": "approved",
            "approvals": [
                {
                    "inner": {"nonce": 4, "signature": "00"},
                    "chain_id": str(CHAIN_ID),
                    "expiry": 9999999999,
                    "epoch_hash": [3] * 32,
                    "amount": str(ONE_THOUSAND_USDC),
                    "conversion": {
                        "canonical_per_representation": str(10**18),
                        "state_id": "0x00",
                        "canonical_amount": str(ONE_THOUSAND_INVENTORY),
                        "representation_amount": str(ONE_THOUSAND_INVENTORY),
                        "chain_amount": str(ONE_THOUSAND_USDC),
                        "representation_remainder": "0",
                    },
                }
            ],
        },
    }


class _EventConnection:
    def __init__(self, messages, entered, acknowledge=True):
        self.messages = messages
        self.entered = entered
        self.acknowledge = acknowledge

    async def __aenter__(self):
        self.entered.set()
        return self

    async def __aexit__(self, *_args):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.acknowledge:
            self.acknowledge = False
            return '{"type": "subscriptions", "channels": ["user_events"], "errors": ""}'
        item = await self.messages.get()
        if item is None:
            raise StopAsyncIteration
        return item


@pytest.mark.anyio
async def test_hint_before_init_response_is_not_lost(manager):
    import asyncio
    import json
    from unittest.mock import AsyncMock

    entered = asyncio.Event()
    messages = asyncio.Queue()
    consumed = asyncio.Event()

    class Connection(_EventConnection):
        async def __anext__(self):
            item = await super().__anext__()
            if "WithdrawalSignatureAvailable" in json.loads(item):
                consumed.set()
            return item

    manager.withdrawals.open_ws.return_value = Connection(messages, entered)

    async def init(_request):
        assert entered.is_set(), "init must follow subscription handshake"
        await messages.put(
            json.dumps(
                {
                    "WithdrawalSignatureAvailable": {
                        "user": manager.default_user.public_key,
                        "asset": USDC.address,
                        "amount": "1",
                        "chain_id": str(CHAIN_ID),
                        "withdrawal_nonce": 4,
                        "valid_until_secs": 9999999999,
                        "timestamp_ns": 1,
                    }
                }
            )
        )
        await consumed.wait()

    manager.withdrawals.init_withdrawal.side_effect = init
    manager.withdrawals.get_withdrawal_status.return_value = [_approval_row(manager)]
    manager.execute_withdrawal = AsyncMock()
    await manager.init_withdrawal(USDC, 1, target=TARGET, then_execute=True, poll_timeout=1)
    manager.execute_withdrawal.assert_awaited_once()
    assert manager.withdrawals.get_withdrawal_status.await_count == 1


@pytest.mark.anyio
async def test_reconnect_resynchronises_status(manager):
    import asyncio
    from unittest.mock import AsyncMock

    messages = asyncio.Queue()
    entered = asyncio.Event()
    connections = 0

    async def connect(*args, **kwargs):
        nonlocal connections
        connections += 1
        return _EventConnection(messages, entered)

    manager.withdrawals.open_ws.side_effect = connect

    async def status(_user):
        if connections == 1:
            await messages.put(None)
            return []
        return [_approval_row(manager)]

    manager.withdrawals.get_withdrawal_status.side_effect = status
    manager.execute_withdrawal = AsyncMock()
    await manager.init_withdrawal(
        USDC, 1, target=TARGET, then_execute=True, poll_interval=0, poll_timeout=1
    )
    assert connections == 2
    assert manager.withdrawals.get_withdrawal_status.await_count == 2
    manager.execute_withdrawal.assert_awaited_once()


@pytest.mark.anyio
async def test_timeout_stays_ambiguous_without_polling(manager):
    import asyncio

    manager.withdrawals.open_ws.return_value = _EventConnection(asyncio.Queue(), asyncio.Event())
    manager.withdrawals.get_withdrawal_status.return_value = []
    with pytest.raises(TimeoutError, match="outcome unknown"):
        await manager.init_withdrawal(USDC, 1, target=TARGET, then_execute=True, poll_timeout=0.02)
    assert manager.withdrawals.get_withdrawal_status.await_count == 1
    manager.vault.withdraw.assert_not_called()


@pytest.mark.anyio
async def test_status_timeout_retries_without_another_hint(manager):
    import asyncio
    from unittest.mock import AsyncMock

    from tplus.exceptions import OmsError

    manager.withdrawals.open_ws.return_value = _EventConnection(asyncio.Queue(), asyncio.Event())
    manager.withdrawals.get_withdrawal_status.side_effect = [
        OmsError(code="TIMEOUT_UNKNOWN_STATE", message="read timed out", status_code=504),
        [_approval_row(manager)],
    ]
    manager.execute_withdrawal = AsyncMock()
    await manager.init_withdrawal(
        USDC,
        1,
        target=TARGET,
        then_execute=True,
        poll_interval=0.001,
        poll_timeout=1,
    )
    assert manager.withdrawals.get_withdrawal_status.await_count == 2
    manager.execute_withdrawal.assert_awaited_once()


@pytest.mark.anyio
async def test_repeated_status_timeouts_are_bounded_by_claim_timeout(manager):
    import asyncio

    from tplus.exceptions import OmsError

    manager.withdrawals.open_ws.return_value = _EventConnection(asyncio.Queue(), asyncio.Event())
    manager.withdrawals.get_withdrawal_status.side_effect = OmsError(
        code="TIMEOUT_UNKNOWN_STATE",
        message="read timed out",
        status_code=504,
    )
    with pytest.raises(TimeoutError, match="outcome unknown"):
        await manager.init_withdrawal(
            USDC,
            1,
            target=TARGET,
            then_execute=True,
            poll_interval=0.001,
            poll_timeout=0.03,
        )
    assert manager.withdrawals.get_withdrawal_status.await_count >= 2
    manager.vault.withdraw.assert_not_called()


@pytest.mark.anyio
async def test_init_waits_for_subscription_acknowledgement(manager):
    import asyncio
    from unittest.mock import AsyncMock

    messages = asyncio.Queue()
    entered = asyncio.Event()
    manager.withdrawals.open_ws.return_value = _EventConnection(
        messages, entered, acknowledge=False
    )
    manager.withdrawals.get_withdrawal_status.return_value = [_approval_row(manager)]
    manager.execute_withdrawal = AsyncMock()
    task = asyncio.create_task(
        manager.init_withdrawal(
            USDC,
            1,
            target=TARGET,
            then_execute=True,
            poll_timeout=1,
        )
    )
    try:
        await entered.wait()
        await messages.put('{"type": "heartbeat"}')
        await asyncio.sleep(0)
        manager.withdrawals.init_withdrawal.assert_not_awaited()
        manager.withdrawals.get_withdrawal_status.assert_not_awaited()
        await messages.put('{"type": "subscriptions", "channels": ["user_events"], "errors": ""}')
        await task
        manager.withdrawals.init_withdrawal.assert_awaited_once()
    finally:
        if not task.done():
            task.cancel()
            from contextlib import suppress

            with suppress(asyncio.CancelledError):
                await task


@pytest.mark.anyio
async def test_subscription_timeout_reports_not_submitted(manager):
    import asyncio

    manager.withdrawals.open_ws.return_value = _EventConnection(
        asyncio.Queue(),
        asyncio.Event(),
        acknowledge=False,
    )
    with pytest.raises(TimeoutError, match="nothing was submitted"):
        await manager.init_withdrawal(USDC, 1, target=TARGET, then_execute=True, poll_timeout=0.02)
    manager.withdrawals.init_withdrawal.assert_not_awaited()
    manager.withdrawals.get_withdrawal_status.assert_not_awaited()
    manager.vault.withdraw.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "frame",
    [
        '{"type":"subscriptions","channels":[],"errors":"unauthorized"}',
        '{"type":"subscriptions","channels":[],"errors":""}',
        '{"type":"subscriptions","channels":["user_events"],"errors":"unauthorized"}',
    ],
)
async def test_rejected_subscription_never_submits_withdrawal(manager, frame):
    import asyncio

    messages = asyncio.Queue()
    await messages.put(frame)
    manager.withdrawals.open_ws.return_value = _EventConnection(
        messages,
        asyncio.Event(),
        acknowledge=False,
    )
    with pytest.raises(TimeoutError, match="nothing was submitted"):
        await manager.init_withdrawal(USDC, 1, target=TARGET, then_execute=True, poll_timeout=0.02)
    manager.withdrawals.init_withdrawal.assert_not_awaited()
    manager.withdrawals.get_withdrawal_status.assert_not_awaited()
    manager.vault.withdraw.assert_not_called()
