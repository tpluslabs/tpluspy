import asyncio
import time
from typing import TYPE_CHECKING

from tplus.client.clearingengine import ClearingEngineClient
from tplus.evm.contracts import DepositVault
from tplus.model.settlement import TxSettlementRequest
from tplus.utils.amount import AmountPair

try:
    from ape.utils.basemodel import ManagerAccessMixin
except ImportError:
    raise ImportError("Please install ape to use the ClearingManager")

if TYPE_CHECKING:
    from ape.api.accounts import AccountAPI

    from tplus.model.asset_identifier import AssetIdentifier
    from tplus.utils.user import User


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

    async def settle(
        self,
        asset_in: "AssetIdentifier",
        amount_in: AmountPair,
        asset_out: "AssetIdentifier",
        amount_out: AmountPair,
    ):
        """
        Initializes a settlement, waits for the approval from the clearing-engine and submits
        the final settlement on-chain.
        """
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
        approval: dict = await self.wait_for_settlement_approval()
        inner = approval["inner"]
        signature = inner["signature"]
        nonce = inner["nonce"]
        expiry = approval["expiry"]

        order = {
            "asset_in": asset_in.evm_address,
            "amount_in": amount_in.atomic,
            "asset_out": asset_out.evm_address,
            "amount_out": amount_out.atomic,
            "nonce": nonce,
        }
        self.vault.executeAtomicSettlement(
            order, self.tplus_user.public_key, expiry, "", signature, nonce, sender=self.ape_account
        )

        # Update the CE.
        await self.ce.settlements.update(self.tplus_user.public_key, self.chain_id)

    async def wait_for_settlement_approval(self) -> list:
        # Get back the approvals. If it takes longer than 5 seconds, consider it not approved.
        # (shouldn't take too terribly long in practice).
        timeout = 10
        started = int(time.time())
        wait_time = 1
        while True:
            approvals = await self.ce.settlements.get_signatures(self.tplus_user)
            if len(approvals) > 0:
                # TODO: This will be problematic if attempting to settle more than once at the same time.
                return approvals[-1]

            elif int(time.time()) - started > timeout:
                # It would be nice if the CE gave us some sort of error here. But here are some things to check:
                # 1. Do you have a client running from the tplus core repo? e.g. arbitrum-client or threshold-client.
                # 2. Are you using a settler that is approved on the vault?
                # 3. Your settler account does not have enough credits in the CE.
                raise Exception("Settlement initialization failed. Check server logs.")

            await asyncio.sleep(wait_time)
