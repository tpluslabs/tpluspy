import asyncio
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from tplus.client.clearingengine import ClearingEngineClient
from tplus.evm.contracts import DepositVault
from tplus.model.settlement import TxSettlementRequest
from tplus.utils.address import public_key_to_address
from tplus.utils.amount import AmountPair

try:
    from ape.utils.basemodel import ManagerAccessMixin
except ImportError:
    raise ImportError("Please install ape to use the ClearingManager")

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI
    from ape.api.transactions import ReceiptAPI

    from tplus.model.asset_identifier import AssetIdentifier
    from tplus.utils.user import User


class SettlementResult:
    success: bool
    execute_atomic_settlement_tx: "ReceiptAPI | None" = None


class ClearingManager(ManagerAccessMixin):
    """
    Integrates the clearing-engine client with the vault contract via Ape to
    abstract away full operations like settlements.
    """

    def __init__(
        self,
        tplus_user: "User",
        ape_account: "AccountAPI",
        ce: ClearingEngineClient | None = None,
        chain_id: int | None = None,
        vault: DepositVault | None = None,
    ):
        self.tplus_user = tplus_user
        self.ape_account = ape_account
        self.ce: ClearingEngineClient = ce or ClearingEngineClient(
            self.tplus_user, "http://127.0.0.1:3032"
        )
        self.chain_id = self.chain_manager.chain_id if chain_id is None else chain_id
        self.vault = vault or DepositVault(chain_id=self.chain_id)

    async def prefetch_chaindata(
        self,
        vaults: bool = True,
        decimals: Sequence["AssetIdentifier"] | None = None,
        deposits: bool = True,
    ):
        """
        Do any initial set up on a fresh CE, such as check for new vaults and deposits.
        """
        if vaults:
            await self.check_for_new_vaults()
            await asyncio.sleep(
                2
            )  # Have to sleep because can't do anything until the CE has vaults.

        # Next, force the decimals to update. This isn't really needed but helps things run consistently from the go.
        if dec := decimals:
            await self.update_decimals(dec)

        # Finally, ingest the deposits that you should have already made by running `ape run deposit`, else this won't
        # do anything for the CE, but you can always run `ape run ingest deposits` separately.
        if deposits:
            await self.check_for_new_deposits()

    async def register_admin(self, vault_owner: "AccountAPI") -> "ReceiptAPI":
        """
        Register the connected clearing-engine as a valid deposit vault admin.
        """
        key = await self.ce.admin.get_verifying_key()
        address = public_key_to_address(key)
        return self.vault.setAdmin(address, True, sender=vault_owner)

    async def settle(
        self,
        asset_in: "AssetIdentifier",
        amount_in: AmountPair,
        asset_out: "AssetIdentifier",
        amount_out: AmountPair,
        confirmations: int = 0,
    ) -> SettlementResult:
        """
        Initializes a settlement, waits for the approval from the clearing-engine and submits
        the final settlement on-chain.

        Args:
            asset_in (AssetIdentifier): The ID of the asset in going into the protocol.
            amount_in (AmountPair): Both the normalized and atomic amounts for the amount going into the protocol.
            asset_out (AssetIdentifier): The ID of the asset leaving the protocol.
            amount_out (AmountPair): Both the normalized and atomic amounts for the amount leaving the protocol.
            confirmations (int): The number of confirmations to wait for the settlement transaction to count as
              complete. Defaults to ``0``.

        Return:
            SettlementResult
        """
        # Initialize the settlement in the clearing-engine. If the user passes solvency checks,
        # approval signatures will eventually become available.
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
        await self.ce.settlements.init_settlement(request)

        # Wait for the approvals using a re-try/timeout approach.
        # NOTE: Hopefully we improve this in the clearing-engine.
        approval: dict = await self.wait_for_settlement_approval()

        # Execute the settlement on-chain.
        tx = self.vault.executeAtomicSettlement(
            {
                "tokenIn": asset_in.evm_address,
                "amountIn": amount_in.atomic,
                "tokenOut": asset_out.evm_address,
                "amountOut": amount_out.atomic,
                "nonce": approval["inner"]["nonce"],
            },
            self.tplus_user.public_key,
            approval["expiry"],
            "",
            approval["inner"]["signature"],
            sender=self.ape_account,
            required_confirmations=confirmations,
        )

        # Update the CE.
        await self.ce.settlements.update(self.tplus_user.public_key, self.chain_id)

        return SettlementResult(success=True, execute_atomic_settlement_tx=tx)

    async def wait_for_settlement_approval(self) -> dict:
        """
        Waits for the existence of settlement approvals. Returns the last of the first approvals
        that get returned from the clearing-engine's permissionless API.

        Returns:
            dict: clearing-engine approval data
        """
        # Get back the approvals. If it takes longer than 5 seconds, consider it not approved.
        # (shouldn't take too terribly long in practice).
        timeout = 10
        started = int(time.time())
        wait_time = 1
        while True:
            approvals = await self.ce.settlements.get_signatures(self.tplus_user.public_key)
            if isinstance(approvals, list) and len(approvals) > 0:
                # TODO: This will be problematic if attempting to settle more than once at the same time.
                return approvals[-1]

            elif int(time.time()) - started > timeout:
                # It would be nice if the CE gave us some sort of error here. But here are some things to check:
                # 1. Do you have a client running from the tplus core repo? e.g. arbitrum-client or threshold-client.
                # 2. Are you using a settler that is approved on the vault?
                # 3. Your settler account does not have enough credits in the CE.
                raise Exception("Settlement initialization failed. Check server logs.")

            await asyncio.sleep(wait_time)

    async def check_for_new_vaults(self):
        await self.ce.vaults.update()

    async def check_for_new_deposits(self):
        await self.ce.deposits.update(self.tplus_user.public_key, self.chain_id)

    async def update_decimals(self, assets: Sequence["AssetIdentifier"]):
        await self.ce.decimals.update(
            list(assets),
            self.chain_id,
        )

    async def get_vaults(self):
        return await self.ce.vaults.get()

    async def init_settlement(self, request: "TxSettlementRequest"):
        return await self.ce.settlements.init_settlement(request)

    async def get_approvals(self):
        return await self.ce.settlements.get_signatures(self.tplus_user)
