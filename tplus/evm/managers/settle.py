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
from tplus.model.settlement import TxSettlementRequest
from tplus.utils.amount import AmountPair
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
    amount_in: AmountPair
    asset_out: "AssetIdentifier"
    amount_out: AmountPair
    expected_nonce: int


class SettlementManager(ChainConnectedManager):
    """
    Integrates the clearing-engine client with the vault contract via Ape to
    abstract away full operations like settlements.
    """

    def __init__(
        self,
        tplus_user: "User",
        ape_account: "AccountAPI",
        clearing_engine: ClearingEngineClient | None = None,
        chain_id: int | None = None,
        vault: DepositVault | None = None,
        settlement_vault: DepositVault | None = None,
    ):
        self.tplus_user = tplus_user
        self.ape_account = ape_account
        self.ce: ClearingEngineClient = clearing_engine or ClearingEngineClient(
            self.tplus_user, "http://127.0.0.1:3032"
        )
        self.chain_id = self.chain_manager.chain_id if chain_id is None else chain_id
        self.vault = vault or DepositVault(chain_id=self.chain_id)

        # NOTE: The user may want to use a different 'vault' instance for settling,
        #       like if following the demo-algo settler service which uses a proxy
        #       for the actual `.executeAtomicSettlement()` call because of the cb.
        self.settlement_vault = settlement_vault or self.vault
        self.logger = get_logger()

    @cached_property
    def deposits(self) -> DepositManager:
        return DepositManager(
            self.ape_account,
            self.tplus_user,
            vault=self.vault,
            chain_id=self.chain_id,
            clearing_engine=self.ce,
        )

    @cached_property
    def chaindata(self) -> ChainDataFetcher:
        return ChainDataFetcher(
            self.tplus_user,
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

    def _decrypt_settlement_approval_message(self, message: dict) -> dict | None:
        """
        Decrypt and parse a settlement approval message from the WebSocket.

        Args:
            message: The raw message dictionary from the WebSocket containing encrypted_data.

        Returns:
            dict: The decrypted approval dictionary, or None if decryption/parsing fails.
        """
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
            return decrypt_settlement_approval(encrypted_data_bytes, self.tplus_user.sk)
        except Exception as err:
            self.logger.warning(f"Failed to decrypt approval: {err}")
            return None

    async def init_settlement(
        self,
        asset_in: "AssetIdentifier",
        amount_in: AmountPair,
        asset_out: "AssetIdentifier",
        amount_out: AmountPair,
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

        Returns:
            SettlementInfo: Information about the settlement including the expected nonce.
        """
        # Get the expected nonce (current count before this settlement - it will increment after init)
        expected_nonce = self.vault.settlementCounts(self.tplus_user.public_key)

        request = TxSettlementRequest.create_signed(
            {
                "chain_id": self.chain_id,
                "asset_in": asset_in,
                "amount_in": amount_in.normalized,
                "asset_out": asset_out,
                "amount_out": amount_out.normalized,
            },
            self.tplus_user,
        )
        await self._init_settlement(request)

        self.logger.info(
            f"Initialized settlement - Asset in: {asset_in.evm_address}, "
            f"Amount in: {amount_in.atomic}, Asset out: {asset_out.evm_address}, "
            f"Amount out: {amount_out.atomic}, Expected nonce: {expected_nonce}"
        )

        return SettlementInfo(
            asset_in=asset_in,
            amount_in=amount_in,
            asset_out=asset_out,
            amount_out=amount_out,
            expected_nonce=expected_nonce,
        )

    async def _init_settlement(self, request: "TxSettlementRequest"):
        return await self.ce.settlements.init_settlement(request)

    async def execute_settlement(
        self,
        settlement_info: SettlementInfo,
        approval: dict,
        **kwargs,
    ) -> "ReceiptAPI":
        """
        Execute a settlement on-chain using the provided approval.

        Args:
            settlement_info: The settlement information from initialization.
            approval: The decrypted approval dictionary from the clearing-engine.
            kwargs: Additional tx properties to pass to ``executeAtomicSettlement()`` e.g.
              ``gas=`` or ``required_confirmations=``.

        Returns:
            ReceiptAPI: The transaction receipt.
        """
        nonce = approval["inner"]["nonce"]
        expiry = approval["expiry"]

        # Validate that the approval matches the expected nonce
        if nonce != settlement_info.expected_nonce:
            raise ValueError(
                f"Approval nonce {nonce} does not match expected nonce {settlement_info.expected_nonce}"
            )

        kwargs.setdefault("sender", self.ape_account)
        kwargs.setdefault("required_confirmations", 0)

        self.logger.info(
            "Executing settlement: "
            f"Vault: {self.vault.address}, "
            f"Chain ID: {self.chain_id}, "
            f"User: {self.tplus_user.public_key}, "
            f"Asset in: {settlement_info.asset_in.evm_address}, "
            f"Amount in: {settlement_info.amount_in.atomic}, "
            f"Asset out: {settlement_info.asset_out.evm_address}, "
            f"Amount out: {settlement_info.amount_out.atomic}, "
            f"Nonce: {nonce}, "
            f"Expiry: {expiry}, "
            f"Domain separator: {self.vault.domain_separator.hex()}"
        )

        # Execute the settlement on-chain.
        tx = self.settlement_vault.execute_atomic_settlement(
            {
                "tokenIn": settlement_info.asset_in.evm_address,
                "amountIn": settlement_info.amount_in.atomic,
                "tokenOut": settlement_info.asset_out.evm_address,
                "amountOut": settlement_info.amount_out.atomic,
                "nonce": nonce,
            },
            HexBytes(self.tplus_user.public_key),
            expiry,
            "",
            HexBytes(approval["inner"]["signature"]),
            **kwargs,
        )

        return tx

    async def get_approvals(self) -> list[dict]:
        return await self.ce.settlements.get_signatures(self.tplus_user.public_key)


class SettlementApprovalHandler:
    """
    Handles settlement approval stream independently from settlement initialization.
    Can be run in a separate async task to process approvals as they arrive.
    """

    def __init__(
        self,
        settlement_manager: SettlementManager,
    ):
        self.settlement_manager = settlement_manager
        self.logger = settlement_manager.logger

    async def handle_approvals(
        self,
        pending_settlements: dict[int, SettlementInfo],
        on_approval_received: (
            "Callable[[SettlementInfo, dict], Awaitable[None] | None] | None"
        ) = None,
    ) -> None:
        """
        Continuously listen for settlement approvals and match them with pending settlements.

        Args:
            pending_settlements: Dictionary mapping nonce -> SettlementInfo for settlements
              waiting for approval. Approved settlements will be removed from this dict.
            on_approval_received: Optional callback function that will be called when an approval
              is received. Called with (settlement_info, approval_dict). If not provided,
              approvals will just be logged.
        """
        self.logger.info(
            f"Starting approval handler for user {self.settlement_manager.tplus_user.public_key}"
        )

        async for message in self.settlement_manager.ce.settlements.stream_approvals(
            self.settlement_manager.tplus_user.public_key
        ):
            approval = self.settlement_manager._decrypt_settlement_approval_message(message)
            if approval is None:
                continue

            nonce = approval.get("inner", {}).get("nonce")
            if nonce is None:
                continue

            # Check if we have a pending settlement for this nonce
            settlement_info = pending_settlements.get(nonce)
            if settlement_info is None:
                self.logger.debug(f"Received approval for unknown nonce {nonce}, ignoring")
                continue

            self.logger.info(f"Received approval for nonce {nonce}")

            # Remove from pending
            del pending_settlements[nonce]

            # Call callback if provided
            if on_approval_received:
                try:
                    result = on_approval_received(settlement_info, approval)
                    if isinstance(result, Awaitable):
                        await result
                except Exception as err:
                    self.logger.error(
                        f"Error in on_approval_received callback for nonce {nonce}: {err}",
                        exc_info=True,
                    )
