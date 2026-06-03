import os
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

from hexbytes import HexBytes

from tplus.client.clearingengine import ClearingEngineClient
from tplus.client.orderbook import OrderBookClient
from tplus.evm.contracts import DepositVault
from tplus.evm.managers.chaindata import ChainDataFetcher
from tplus.evm.managers.deposit import DepositManager
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.logger import get_logger
from tplus.model.approval import SettlementApproval
from tplus.model.settlement import MakerOrderAttachment, SettlementMode, TxSettlementRequest
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.amount import Amount

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.api.transactions import ReceiptAPI
    from ape.contracts.base import ContractInstance
    from ape.types.address import AddressType

    from tplus.model.asset_identifier import Address32, AssetAddress
    from tplus.utils.user import User


@dataclass
class SettlementInfo:
    """
    Information about a settlement after initialization.
    Used to track and match approvals with their corresponding settlements.
    """

    asset_in: "Address32"
    amount_in: Amount
    asset_out: "Address32"
    amount_out: Amount
    nonce: int
    chain_id: "ChainID"
    settler: "UserPublicKey | None" = None
    sub_account_index: int = 0


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
        oms_client: OrderBookClient | None = None,
        chain_id: ChainID | None = None,
        vault: DepositVault | None = None,
        settlement_vault: DepositVault | None = None,
    ):
        self.default_user = default_user
        self.ape_account = ape_account
        self.ce: ClearingEngineClient = clearing_engine or ClearingEngineClient.from_local(
            self.default_user
        )
        if oms_client is not None:
            self.oms = oms_client
        else:
            oms_base_url = os.getenv("API_BASE_URL", "https://127.0.0.1:8000")
            oms_insecure_ssl = self.ce._settings.insecure_ssl
            self.oms = OrderBookClient(
                default_user=self.default_user,
                base_url=oms_base_url,
                insecure_ssl=oms_insecure_ssl,
            )
        self.chain_id = chain_id or ChainID.evm(self.chain_manager.chain_id)
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
        decimals: Sequence["AssetAddress"] | None = None,
    ):
        return await self.chaindata.prefetch_chaindata(
            vaults=vaults,
            assets=assets,
            decimals=decimals,
        )

    async def init_settlement(
        self,
        asset_in: "Address32",
        amount_in: Amount,
        asset_out: "Address32",
        amount_out: Amount,
        user: "User | None" = None,
        settler: "UserPublicKey | None" = None,
        maker_order: MakerOrderAttachment | None = None,
        account_index: int | None = None,
        mode: SettlementMode = SettlementMode.MARGIN,
        then_execute: bool = False,
        executor_contract: "ContractInstance | None" = None,
    ) -> tuple[SettlementInfo, SettlementApproval]:
        """
        Initialize a settlement and return its approval synchronously.

        Args:
            asset_in: The address of the asset in going into the protocol.
            amount_in: Both the normalized and atomic amounts for the amount going into the protocol.
            asset_out: The address of the asset leaving the protocol.
            amount_out: Both the normalized and atomic amounts for the amount leaving the protocol.
            user: Specify the tplus user. Defaults to the default tplus user.
            settler: The settler account executing the settlement. Defaults to the user's public key.
            maker_order: Optional maker order attachment for delegated settlements.
            account_index: Specify the index of the tplus account for this settlement approval. Defaults to the
              selected user's account index.
            then_execute: Set to ``True`` to wait for the approval and then execute the settlement on-chain.
            executor_contract: Optional ape contract instance to use as ``msg.sender`` for the
              on-chain ``executeAtomicSettlement`` call. Required when the settler's registered
              executor is a contract (e.g. ``SettlerExecutor``) rather than an EOA, because the
              vault dispatches ``onAtomicSettlement`` back into ``msg.sender``. Only relevant
              when ``then_execute=True``.

        Returns:
            tuple[SettlementInfo, SettlementApproval]: Settlement metadata and the approval returned by CE.
        """

        user = user or self.default_user

        if account_index is None:
            account_index = user.sub_account

        amount_in_normalized = amount_in.to_inventory_amount("up")
        amount_out_normalized = amount_out.to_inventory_amount("down")

        request_data = {
            "chain_id": self.chain_id,
            "mode": mode,
            "asset_in": asset_in,
            "amount_in": amount_in_normalized,
            "asset_out": asset_out,
            "amount_out": amount_out_normalized,
            "sub_account_index": account_index,
        }
        if settler is not None:
            request_data["settler"] = settler
        elif maker_order is None:
            # Non-delegated: sign over an explicit settler, not null.
            request_data["settler"] = user.public_key

        request = TxSettlementRequest.create_signed(request_data, user)
        if maker_order is not None:
            request.maker_order = maker_order

        approval = await self._init_settlement(request)

        settlement_info = SettlementInfo(
            asset_in=asset_in,
            amount_in=amount_in,
            asset_out=asset_out,
            amount_out=amount_out,
            nonce=approval.inner.nonce,
            chain_id=self.chain_id,
            settler=settler or user.public_key,
            sub_account_index=account_index,
        )

        self.logger.info(
            f"Initialized settlement - Asset in: {asset_in}, "
            f"Amount in: {amount_in.amount}, Asset out: {asset_out}, "
            f"Amount out: {amount_out.amount}, Nonce: {approval.inner.nonce}"
        )

        if then_execute:
            execute_kwargs = {}
            if executor_contract is not None:
                execute_kwargs["sender"] = executor_contract
            await self.execute_settlement(settlement_info, approval, **execute_kwargs)

        return settlement_info, approval

    async def _init_settlement(self, request: "TxSettlementRequest") -> SettlementApproval:
        approval_data = await self.oms.init_settlement(request)
        return SettlementApproval.model_validate(approval_data)

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
        settler = settlement_info.settler or user.public_key
        token_in_address = kwargs.pop("token_in", None)
        token_out_address = kwargs.pop("token_out", None)

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
                "user": HexBytes(user.public_key),
                "account": settlement_info.sub_account_index,
                "nonce": nonce,
                "validUntil": expiry,
            },
            HexBytes(settler),
            "",
            HexBytes(approval.inner.signature),
            **kwargs,
        )

        return tx
