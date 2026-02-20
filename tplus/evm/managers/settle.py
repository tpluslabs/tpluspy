import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

from hexbytes import HexBytes

from tplus.client.clearingengine import ClearingEngineClient
from tplus.evm.contracts import DepositVault
from tplus.evm.managers.chaindata import ChainDataFetcher
from tplus.evm.managers.deposit import DepositManager
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.logger import get_logger
from tplus.model.approval import SettlementApproval
from tplus.model.settlement import TxSettlementRequest
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.amount import Amount
from tplus.utils.user.decrypt import decrypt_settlement_approval

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.api.transactions import ReceiptAPI
    from ape.contracts.base import ContractInstance
    from ape.types.address import AddressType

    from tplus.model.asset_identifier import AssetIdentifier
    from tplus.utils.user import User


@dataclass
class SettlementInfo:
    """
    Information about a settlement after initialization.
    Used to track and match approvals with their corresponding settlements.
    """

    asset_in: "AssetIdentifier"
    amount_in: Amount
    asset_out: "AssetIdentifier"
    amount_out: Amount
    nonce: int


class SettlementManager(ChainConnectedManager):
    """
    Integrates the clearing-engine client with the vault contract via Ape to
    abstract away full operations like settlements.
    """

    def __init__(
        self,
        default_user: "User",
        ape_account: "AccountAPI",
        clearing_engine: ClearingEngineClient | None = None,
        chain_id: ChainID | None = None,
        vault: DepositVault | None = None,
        settlement_vault: DepositVault | None = None,
    ):
        self.default_user = default_user
        self.ape_account = ape_account
        self.ce: ClearingEngineClient = clearing_engine or ClearingEngineClient(
            self.default_user, "http://127.0.0.1:3032"
        )
        self.chain_id = chain_id or ChainID.evm(self.chain_manager.chain_id)
        self.vault = vault or DepositVault(chain_id=self.chain_id)

        # NOTE: The user may want to use a different 'vault' instance for settling,
        #       like if following the demo-algo settler service which uses a proxy
        #       for the actual `.executeAtomicSettlement()` call because of the cb.
        self.settlement_vault = settlement_vault or self.vault
        self.logger = get_logger()

        self._approval_handling_tasks = {}

    @cached_property
    def deposits(self) -> DepositManager:
        return DepositManager(
            self.ape_account,
            self.default_user,
            vault=self.vault,
            chain_id=self.chain_id,
            clearing_engine=self.ce,
        )

    @cached_property
    def chaindata(self) -> ChainDataFetcher:
        return ChainDataFetcher(
            self.default_user,
            self.ce,
            self.chain_id,
        )

    async def deposit(
        self, token: "str | AddressType | ContractInstance", amount: int, wait: bool = False
    ):
        await self.deposits.deposit(token, amount, wait=wait)

    async def prefetch_chaindata(
        self,
        vaults: bool = True,
        assets: bool = True,
        decimals: Sequence["AssetIdentifier"] | None = None,
        deposits: bool = True,
        settlements: bool = True,
    ):
        return await self.chaindata.prefetch_chaindata(
            vaults=vaults,
            assets=assets,
            decimals=decimals,
            deposits=deposits,
            settlements=settlements,
        )

    def decrypt_settlement_approval_message(
        self, message: dict, user: "User | None" = None
    ) -> SettlementApproval | None:
        """
        Decrypt and parse a settlement approval message from the WebSocket.

        Args:
            message: The raw message dictionary from the WebSocket containing encrypted_data.
            user: Specify the tplus user. Defaults to the default_user

        Returns:
            SettlementApproval: The decrypted approval dictionary, or None if decryption/parsing fails.
        """
        user = user or self.default_user

        try:
            encrypted_data = message["encrypted_data"]
        except KeyError as err:
            self.logger.warning(f"Missing expected key 'encrypted_data' in approval message: {err}")
            return None

        try:
            encrypted_data_bytes = bytes.fromhex(encrypted_data)
        except Exception as err:
            self.logger.warning(f"Invalid hexbytes {encrypted_data}. Error: {err}")
            return None

        try:
            data = decrypt_settlement_approval(encrypted_data_bytes, user.sk)
        except Exception as err:
            self.logger.warning(f"Failed to decrypt approval: {err}")
            return None

        return SettlementApproval.model_validate(data)

    async def init_settlement(
        self,
        asset_in: "AssetIdentifier",
        amount_in: Amount,
        asset_out: "AssetIdentifier",
        amount_out: Amount,
        user: "User | None" = None,
        account_index: int | None = None,
        then_execute: bool = False,
        on_approved: "Callable[[SettlementInfo, SettlementApproval], Awaitable[None] | None] | None" = None,
    ) -> SettlementInfo:
        """
        Initialize a settlement asynchronously without waiting for approval.

        This method initializes the settlement in the clearing-engine and returns
        settlement information that can be used to track and match approvals later.

        Args:
            asset_in: The ID of the asset in going into the protocol.
            amount_in: Both the normalized and atomic amounts for the amount going into the protocol.
            asset_out: The ID of the asset leaving the protocol.
            amount_out: Both the normalized and atomic amounts for the amount leaving the protocol.
            user: Specify the tplus user. Defaults to the default tplus user.
            account_index: Specify the index of the tplus account for this settlement approval. Defaults to the
              selected user's account index.
            then_execute: Set to ``True`` to wait for the approval and then execute the settlement on-chain.
            on_approved: Custom callback for receiving the approval from the CE.

        Returns:
            SettlementInfo: Information about the settlement including the expected nonce.
        """
        if on_approved and then_execute:
            raise ValueError("Cannot provide both `on_approved` and `then_execute` arguments.")

        # Get the expected nonce (current count before this settlement - it will increment after init)
        user = user or self.default_user
        expected_nonce = self.vault.settlementCounts(user.public_key, user.sub_account)

        amount_in_normalized = amount_in.to_inventory_amount("up")
        amount_out_normalized = amount_out.to_inventory_amount("down")

        if account_index is None:
            account_index = user.sub_account

        request = TxSettlementRequest.create_signed(
            {
                "chain_id": self.chain_id,
                "asset_in": asset_in,
                "amount_in": amount_in_normalized,
                "asset_out": asset_out,
                "amount_out": amount_out_normalized,
                "sub_account_index": account_index,
            },
            user,
        )

        await self._init_settlement(request)

        self.logger.info(
            f"Initialized settlement - Asset in: {asset_in}, "
            f"Amount in: {amount_in.amount}, Asset out: {asset_out}, "
            f"Amount out: {amount_out.amount}, Expected nonce: {expected_nonce}"
        )

        settlement_info = SettlementInfo(
            asset_in=asset_in,
            amount_in=amount_in,
            asset_out=asset_out,
            amount_out=amount_out,
            nonce=expected_nonce,
        )

        if on_approved or then_execute:
            handler = SettlementApprovalHandler(self)

            if then_execute:

                async def on_approved(info, approval):
                    await self.execute_settlement(info, approval)

            async def approval_handling_task_fn():
                try:
                    async with asyncio.timeout(12):
                        await handler.handle_approvals(
                            on_approval_received=on_approved,
                            stop_at=1,
                            pending_settlements={expected_nonce: settlement_info},
                        )
                except TimeoutError:
                    self.logger.info("Approval handler timed out")

            approval_handling_task = asyncio.create_task(approval_handling_task_fn())

            self._approval_handling_tasks.setdefault(user.public_key, {})

            self._approval_handling_tasks[user.public_key][settlement_info.nonce] = (
                approval_handling_task
            )

            def _cleanup(_task: asyncio.Task):
                tasks = self._approval_handling_tasks.get(user.public_key)
                if not tasks:
                    return

                tasks.pop(settlement_info.nonce, None)

                if not tasks:
                    self._approval_handling_tasks.pop(user.public_key, None)

            approval_handling_task.add_done_callback(_cleanup)

        return settlement_info

    async def _init_settlement(self, request: "TxSettlementRequest"):
        return await self.ce.settlements.init_settlement(request)

    async def execute_settlement(
        self,
        settlement_info: SettlementInfo,
        approval: SettlementApproval,
        user: "UserPublicKey | None" = None,
        **kwargs,
    ) -> "ReceiptAPI":
        """
        Execute a settlement on-chain using the provided approval.

        Args:
            settlement_info: The settlement information from initialization.
            approval: The decrypted approval from the clearing-engine.
            user: Specify the tplus user. Defaults to the default tplus user.
            kwargs: Additional tx properties to pass to ``executeAtomicSettlement()`` e.g.
              ``gas=`` or ``required_confirmations=``.

        Returns:
            ReceiptAPI: The transaction receipt.
        """
        nonce = approval.inner.nonce
        expiry = approval.expiry
        user = user or self.default_user
        token_in_address = kwargs.pop("token_in", None)
        token_out_address = kwargs.pop("token_out", None)

        # Validate that the approval matches the expected nonce
        if nonce != settlement_info.nonce:
            raise ValueError(
                f"Approval nonce {nonce} does not match expected nonce {settlement_info.nonce}"
            )

        kwargs.setdefault("sender", self.ape_account)
        kwargs.setdefault("required_confirmations", 0)

        if token_in_address is None:
            token_in_address = settlement_info.asset_in.evm_address
        if token_out_address is None:
            token_out_address = settlement_info.asset_out.evm_address

        # Execute the settlement on-chain.
        tx = self.settlement_vault.execute_atomic_settlement(
            {
                "tokenIn": token_in_address,
                "amountIn": settlement_info.amount_in.amount,
                "tokenOut": token_out_address,
                "amountOut": settlement_info.amount_out.amount,
                "nonce": nonce,
            },
            HexBytes(user.public_key),
            user.sub_account,
            expiry,
            "",
            HexBytes(approval.inner.signature),
            **kwargs,
        )

        return tx


class SettlementApprovalHandler:
    """
    Handles settlement approval stream independently of settlement initialization.
    Can be run in a separate async task to process approvals as they arrive.
    """

    def __init__(
        self,
        settlement_manager: SettlementManager,
    ):
        self.settlement_manager = settlement_manager
        self.logger = settlement_manager.logger
        self.on_approval_received = None

    async def handle_approvals(
        self,
        on_approval_received: (
            "Callable[[SettlementInfo | None, SettlementApproval], Awaitable[None] | None] | None"
        ) = None,
        pending_settlements: dict[int, SettlementInfo] | None = None,
        stop_at: int | None = None,
        user: "UserPublicKey | None" = None,
    ) -> None:
        """
        Continuously listen for settlement approvals and match them with pending settlements.

        Args:
            on_approval_received: Optional callback function that will be called when an approval
              is received. Called with (settlement_info, approval_dict). If not provided,
              approvals will just be logged.
            pending_settlements: Dictionary mapping nonce -> SettlementInfo for settlements
              waiting for approval. Approved settlements will be removed from this dict, if given.
              To handle any settlement regardless, pass ``None`` or leave as default.
            stop_at: The amount of approvals to handle before stopping.
            user: Specify the user. Defaults to the default user.
        """
        user = user or self.settlement_manager.default_user.public_key
        self.logger.info(f"Starting approval handler for user {user}")
        amount_handled = 0

        try:
            async for message in self.settlement_manager.ce.settlements.stream_approvals(user):
                approval = self.settlement_manager.decrypt_settlement_approval_message(message)
                if approval is None:
                    continue

                nonce = approval.inner.nonce
                pending_settlements = pending_settlements or {}
                settlement_info = pending_settlements.get(nonce)
                if settlement_info is None:
                    self.logger.debug(f"Received approval for unknown nonce {nonce}, ignoring")
                    continue

                else:
                    self.logger.info(f"Received approval for nonce {nonce}")
                    del pending_settlements[nonce]

                callback = on_approval_received or self.on_approval_received
                if callback:
                    try:
                        result = callback(settlement_info, approval)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as err:
                        self.logger.error(
                            f"Error in on_approval_received callback for nonce {nonce}: {err}",
                            exc_info=True,
                        )

                amount_handled += 1
                if stop_at is not None and amount_handled >= stop_at:
                    break

        except asyncio.TimeoutError:
            self.logger.info("Approval handler timed out")
