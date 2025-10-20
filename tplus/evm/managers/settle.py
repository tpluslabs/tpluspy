import asyncio
import time
from collections.abc import Sequence
from functools import cached_property
from typing import TYPE_CHECKING

from hexbytes import HexBytes

from tplus.client.clearingengine import ClearingEngineClient
from tplus.evm.contracts import DepositVault
from tplus.evm.managers.deposit import DepositManager
from tplus.evm.managers.evm import ChainConnectedManager
from tplus.logger import get_logger
from tplus.model.settlement import TxSettlementRequest
from tplus.utils.amount import AmountPair

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
        self.nonce = 0

    @cached_property
    def deposits(self):
        return DepositManager(
            self.ape_account,
            self.tplus_user,
            vault=self.vault,
            chain_id=self.chain_id,
            clearing_engine=self.ce,
        )

    async def prefetch_chaindata(
        self,
        vaults: bool = True,
        decimals: Sequence["AssetIdentifier"] | None = None,
        deposits: bool = True,
    ):
        """
        Do any initial set up on a fresh CE, such as check for new vaults and deposits.
        """
        await self.ensure_vault_registered(check_for_new_vaults=vaults)

        # Next, force the decimals to update. This isn't really needed but helps things run consistently from the go.
        if dec := decimals:
            await self.update_decimals(dec)

        # Finally, ingest the deposits that you should have already made by running `ape run deposit`, else this won't
        # do anything for the CE, but you can always run `ape run ingest deposits` separately.
        if deposits:
            await self.check_for_new_deposits()

    async def ensure_vault_registered(self, check_for_new_vaults: bool) -> None:
        if check_for_new_vaults:
            await self.check_for_new_vaults()

            await asyncio.sleep(2)  # Give CE time to register vaults.

        for attempt in range(2):  # Try up to 2 times
            ce_vaults = await self.ce.vaults.get()
            if ce_vaults:
                return

            await asyncio.sleep(2)

        raise ValueError("Vault never registered.")

    async def deposit(
        self, token: "str | AddressType | ContractInstance", amount: int, wait: bool = False
    ):
        await self.deposits.deposit(token, amount, wait=wait)

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

        # Wait for the approvals using a re-try/timeout approach.
        # NOTE: Hopefully we improve this in the clearing-engine.
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
        tx = self.settlement_vault.executeAtomicSettlement(
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

        # Update the CE.
        await self.ce.settlements.update(self.tplus_user.public_key, self.chain_id)

        self.nonce += 1

        return tx

    async def wait_for_settlement_approval(
        self, timeout: int = DEFAULT_WAIT_SECONDS, wait_interval: int = DEFAULT_WAIT_INTERVAL
    ) -> dict:
        """
        Waits for the existence of settlement approvals. Returns the last of the first approvals
        that get returned from the clearing-engine's permissionless API.

        Args:
            timeout (int): The number of seconds to wait for the settlement approval.
            wait_interval (int): The number of seconds to between checks.

        Returns:
            dict: clearing-engine approval data
        """
        # Get back the approvals. If it takes longer than 5 seconds, consider it not approved.
        # (shouldn't take too terribly long in practice).
        started = int(time.time())
        while True:
            approvals = await self.get_approvals()
            if isinstance(approvals, list) and len(approvals) > 0:
                for approval in approvals[::-1]:
                    if approval["inner"]["nonce"] == self.nonce:
                        return approvals[-1]
                    elif approval["inner"]["nonce"] < self.nonce:
                        # No need to search rest of list.
                        break

            elif int(time.time()) - started > timeout:
                # It would be nice if the CE gave us some sort of error here. But here are some things to check:
                # 1. Do you have a client running from the tplus core repo? e.g. arbitrum-client or threshold-client.
                # 2. Are you using a settler that is approved on the vault?
                # 3. Your settler account does not have enough credits in the CE.
                raise Exception("Settlement initialization failed. Check server logs.")

            await asyncio.sleep(wait_interval)

    async def check_for_new_vaults(self):
        await self.ce.vaults.update()

    async def check_for_new_deposits(self):
        await self.ce.deposits.update(self.tplus_user.public_key, self.chain_id)

    async def update_decimals(self, assets: Sequence["AssetIdentifier"]):
        await self.ce.decimals.update(
            list(assets),
            [self.chain_id],
        )

    async def init_settlement(self, request: "TxSettlementRequest"):
        return await self.ce.settlements.init_settlement(request)

    async def get_approvals(self) -> list[dict]:
        return await self.ce.settlements.get_signatures(self.tplus_user.public_key)
