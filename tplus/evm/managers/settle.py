import json
import time
from collections.abc import Sequence
from functools import cached_property
from typing import TYPE_CHECKING

from hexbytes import HexBytes

from tplus.client.clearingengine import ClearingEngineClient
from tplus.evm.contracts import DepositVault
from tplus.evm.exceptions import SettlementApprovalTimeout
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


DEFAULT_WAIT_SECONDS = 10  # Seconds
DEFAULT_WAIT_INTERVAL = 1  # Seconds


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

    async def settle(
        self,
        asset_in: "AssetIdentifier",
        amount_in: AmountPair,
        asset_out: "AssetIdentifier",
        amount_out: AmountPair,
        **kwargs,
    ) -> "ReceiptAPI":
        """
        Initializes a settlement, waits for the approval from the clearing-engine and submits
        the final settlement on-chain.

        Args:
            asset_in (AssetIdentifier): The ID of the asset in going into the protocol.
            amount_in (AmountPair): Both the normalized and atomic amounts for the amount going into the protocol.
            asset_out (AssetIdentifier): The ID of the asset leaving the protocol.
            amount_out (AmountPair): Both the normalized and atomic amounts for the amount leaving the protocol.
            kwargs (dict[str, Any]): Additional tx properties to pass to the ``executeAtomicSettlement()`` e.g.
              ``gas=`` or ``required_confirmations=``.

        Return:
            ReceiptAPI
        """
        # Initialize the settlement in the clearing-engine. If the user passes solvency checks,
        # approval signatures will eventually become available.
        wait_timeout = kwargs.pop("wait_timeout", DEFAULT_WAIT_SECONDS)
        wait_interval = kwargs.pop("wait_interval", DEFAULT_WAIT_INTERVAL)
        force_update = kwargs.pop("force_update", False)
        kwargs.setdefault("sender", self.ape_account)
        kwargs.setdefault("required_confirmations", 0)

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
        await self.init_settlement(request)

        approval: dict = await self.wait_for_settlement_approval(
            timeout=wait_timeout, wait_interval=wait_interval
        )

        nonce = approval["inner"]["nonce"]
        expiry = approval["expiry"]

        self.logger.info(
            "Settlement data: "
            f"Vault: {self.vault.address}, "
            f"Chain ID: {self.chain_id}, "
            f"User: {self.tplus_user.public_key}, "
            f"Asset in: {asset_in.evm_address}, "
            f"Amount in: {amount_in.atomic}, "
            f"Asset out: {asset_out.evm_address}, "
            f"Amount out: {amount_out.atomic}, "
            f"Nonce: {nonce}, "
            f"Expiry: {expiry}, "
            f"Domain separator: {self.vault.domain_separator.hex()}"
        )

        # Execute the settlement on-chain.
        tx = self.settlement_vault.execute_atomic_settlement(
            {
                "tokenIn": asset_in.evm_address,
                "amountIn": amount_in.atomic,
                "tokenOut": asset_out.evm_address,
                "amountOut": amount_out.atomic,
                "nonce": nonce,
            },
            HexBytes(self.tplus_user.public_key),
            expiry,
            "",
            HexBytes(approval["inner"]["signature"]),
            **kwargs,
        )

        # Typically, core has websockets running handling the events and shouldn't need to manually call
        # the update methods.
        if force_update:
            await self.ce.settlements.update(self.tplus_user.public_key, self.chain_id)

        return tx

    async def wait_for_settlement_approval(self, timeout: int = DEFAULT_WAIT_SECONDS) -> dict:
        """
        Waits for the existence of settlement approvals via WebSocket. Returns the approval
        matching the current settlement nonce.

        Args:
            timeout (int): The number of seconds to wait for the settlement approval.

        Returns:
            dict: clearing-engine approval data
        """
        started = int(time.time())
        expected_nonce = self.vault.settlementCounts(self.tplus_user.public_key)

        self.logger.info(
            f"Waiting for settlement approval via WebSocket. Expected nonce: {expected_nonce}"
        )

        try:
            async for message in self.ce.settlements.stream_approvals(self.tplus_user.public_key):
                if int(time.time()) - started > timeout:
                    raise SettlementApprovalTimeout(timeout, expected_nonce)

                approval = self._decrypt_settlement_approval_message(message)
                if approval is None:
                    continue

                # Check if this approval matches the expected nonce
                if approval.get("inner", {}).get("nonce") == expected_nonce:
                    self.logger.info(
                        f"Received settlement approval for nonce {expected_nonce} via WebSocket"
                    )
                    return approval

                self.logger.debug(
                    f"Received approval for nonce {approval.get('inner', {}).get('nonce')}, "
                    f"expected {expected_nonce}, continuing to wait..."
                )

        except SettlementApprovalTimeout:
            raise

        except Exception as err:
            elapsed = int(time.time()) - started
            if elapsed >= timeout:
                raise SettlementApprovalTimeout(timeout, expected_nonce) from err

            raise

    def _decrypt_settlement_approval_message(self, message: dict) -> dict | None:
        """
        Decrypt and parse a settlement approval message from the WebSocket.

        Args:
            message: The raw message dictionary from the WebSocket containing encrypted_data.

        Returns:
            dict: The decrypted approval dictionary, or None if decryption/parsing fails.
        """
        try:
            encrypted_data_bytes = bytes.fromhex(message["encrypted_data"])
            decrypted_json = decrypt_settlement_approval(encrypted_data_bytes, self.tplus_user.sk)
            return json.loads(decrypted_json)
        except Exception as err:
            self.logger.warning(f"Failed to decrypt or parse settlement approval message: {err}")
            return None

    async def init_settlement(self, request: "TxSettlementRequest"):
        return await self.ce.settlements.init_settlement(request)

    async def get_approvals(self) -> list[dict]:
        return await self.ce.settlements.get_signatures(self.tplus_user.public_key)
