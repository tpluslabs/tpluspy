import asyncio
import time
from functools import cached_property
from typing import TYPE_CHECKING

from ape.contracts.base import ContractContainer
from ape.utils.basemodel import ManagerAccessMixin
from ape_test.accounts import TestAccount
from ape_tokens.testing import MockERC20

from tplus.evm.contracts import DepositVault
from tplus.evm.dev.contracts import SettlerExecutor
from tplus.evm.dev.token import Token
from tplus.evm.exceptions import SettlementError
from tplus.evm.managers.settle import SettlementApprovalHandler, SettlementManager
from tplus.evm.managers.withdraw import WithdrawalInfo, WithdrawalManager
from tplus.model.asset_identifier import AssetAddress, AssetIdentifier
from tplus.model.settlement import (
    InnerMakerOrderAttachment,
    MakerOrderAttachment,
    SettlementMode,
)
from tplus.model.types import ChainID
from tplus.utils.address import to_evm_address
from tplus.utils.amount import Amount
from tplus.utils.hex import str_to_vec

if TYPE_CHECKING:
    from tplus.client import ClearingEngineClient
    from tplus.model.chain_address import Address32
    from tplus.model.types import UserPublicKey
    from tplus.utils.user import User


class DeveloperEnvironment(ManagerAccessMixin):
    """
    Python-side dev helpers: test-token deploys, SettlerExecutor deploy,
    and settlement/withdrawal pending-state tracking.

    Contract bootstrapping (Registry, CredentialManager, DepositVault, asset
    registration, etc.) is driven via the tplus CLI or scripts/dev-bootstrap.sh.
    """

    def __init__(
        self,
        default_user: "User",
        ce: "ClearingEngineClient",
        deposit_vault: DepositVault | None = None,
    ):
        self.default_user = default_user
        self.ce_client: ClearingEngineClient = ce
        self._deposit_vault = deposit_vault
        self.setup_snapshot = None

        self._pending_settlements = {}
        self._pending_settlement_errors = {}
        self._pending_withdrawals = {}
        self._pending_withdrawal_errors = {}

    @cached_property
    def admin(self) -> TestAccount:
        return self.account_manager.test_accounts[0]

    @cached_property
    def chain_id(self) -> ChainID:
        return ChainID.from_parts(0, self.chain_manager.chain_id)

    @property
    def deposit_vault(self) -> DepositVault:
        if self._deposit_vault is None:
            self._deposit_vault = DepositVault()

        return self._deposit_vault

    @cached_property
    def settler_executor(self) -> ContractContainer:
        settler = SettlerExecutor.deploy(sender=self.admin)
        settler.balance += int(1e18) * 5000
        return settler

    @cached_property
    def usdc(self) -> Token:
        return Token(self.deploy_token("U.S. Dollar Coin", "USDC", 6), self.chain_id, asset_index=0)

    @cached_property
    def weth(self) -> Token:
        return Token(self.deploy_token("Wrapped Ether", "WETH", 18), self.chain_id, asset_index=1)

    def deploy_token(self, name: str, symbol: str, decimals: int) -> "MockERC20":
        return MockERC20.deploy(self.admin, name, symbol, decimals, sender=self.admin)

    def get_token(self, symbol: str) -> Token:
        if symbol == "USDC":
            return self.usdc
        elif symbol == "WETH":
            return self.weth

        raise NotImplementedError(f"Token not yet implemented {symbol}")

    async def sync_vault_balances(self):
        await self.ce_client.vaults.update_balance(self.usdc.asset_address)
        await self.ce_client.vaults.update_balance(self.weth.asset_address)

    async def disable_withdrawal_delay(self):
        await self.ce_client.admin.set_withdrawal_delay_params(
            min_delay=0,
            max_delay=0,
            delay_clamps=[0, 1_000_000],
            delay_values=[0, 0],
        )

    def snapshot_chain_state(self):
        self.setup_snapshot = self.chain_manager.snapshot()

    @cached_property
    def settlement_manager(self) -> SettlementManager:
        return self.create_settlement_manager()

    def create_settlement_manager(self, trader: "User | None" = None) -> SettlementManager:
        trader = trader or self.default_user
        return SettlementManager(
            trader,
            self.admin,
            clearing_engine=self.ce_client,
            chain_id=self.chain_id,
            vault=self.deposit_vault,
        )

    @cached_property
    def settlement_approval_handler(self):
        return SettlementApprovalHandler(self.settlement_manager)

    @cached_property
    def withdrawal_manager(self) -> WithdrawalManager:
        return self.create_withdrawal_manager()

    def create_withdrawal_manager(self, trader: "User | None" = None) -> WithdrawalManager:
        trader = trader or self.default_user
        return WithdrawalManager(
            trader,
            self.admin,
            clearing_engine=self.ce_client,
            chain_id=self.chain_id,
            vault=self.deposit_vault,
        )

    @staticmethod
    def create_maker_order(
        mm: "User",
        settler: "UserPublicKey",
        expires_at_ns: int | None = None,
    ) -> MakerOrderAttachment:
        """
        Create a signed :class:`~tplus.model.settlement.MakerOrderAttachment`
        for delegated settlement tests.
        """
        if expires_at_ns is None:
            expires_at_ns = int((time.time() + 300) * 1e9)

        inner = InnerMakerOrderAttachment(
            mm_pubkey=mm.public_key,
            settler=settler,
            expires_at=expires_at_ns,
        )
        payload = inner.model_dump_json(exclude_none=True)
        signature = str_to_vec(mm.sign(payload).hex())
        return MakerOrderAttachment(inner=inner, signature=signature)

    async def init_settlement(
        self,
        asset_in: AssetAddress,
        amount_in: Amount,
        asset_out: AssetAddress,
        amount_out: Amount,
        user: "User | None" = None,
        settler: "UserPublicKey | None" = None,
        maker_order: MakerOrderAttachment | None = None,
        sub_account: int | None = None,
        mode: SettlementMode = SettlementMode.MARGIN,
    ):
        user = user or self.default_user
        key = f"{user.public_key}"
        self._pending_settlements.setdefault(key, {})
        self._pending_settlement_errors.pop(key, None)

        self.settler_executor.setReturnAmount(amount_in.amount, sender=self.admin)

        try:
            info, approval = await self.settlement_manager.init_settlement(
                asset_in,
                amount_in,
                asset_out,
                amount_out,
                user=user,
                settler=settler,
                maker_order=maker_order,
                account_index=sub_account,
                mode=mode,
            )
        except SettlementError as err:
            self._pending_settlement_errors[key] = err
            return
        except Exception as err:
            self._pending_settlement_errors[key] = SettlementError(str(err))
            return

        self._pending_settlements[key][info.nonce] = (info, approval)

    async def wait_for_settlement_approval_result(
        self,
        user: "UserPublicKey | User | None" = None,
        nonce: int | None = None,
        timeout: float = 10.0,
        poll_interval: float = 0.2,
    ) -> dict[str, bool | str | None]:
        if user:
            if not isinstance(user, str):
                user = user.public_key
        else:
            user = self.default_user.public_key

        loop = asyncio.get_running_loop()
        timeout_at = loop.time() + timeout
        key = f"{user}"

        while loop.time() < timeout_at:
            if key in self._pending_settlement_errors:
                err = self._pending_settlement_errors.pop(key)
                reason = str(err)

                if isinstance(err, SettlementError) and err.args:
                    first_arg = err.args[0]

                    if isinstance(first_arg, dict):
                        reason = first_arg.get("reason", reason)

                return {"success": False, "reason": reason}

            if key in self._pending_settlements:
                settlements = self._pending_settlements[key]

                if nonce is not None:
                    if nonce in settlements and settlements[nonce][1] is not None:
                        return {"success": True, "reason": None}

                elif settlements:
                    latest_nonce = max(settlements.keys())

                    if settlements[latest_nonce][1] is not None:
                        return {"success": True, "reason": None}

            await asyncio.sleep(poll_interval)

        return {
            "success": False,
            "reason": f"Timed out waiting for settlement approval result for settler '{user}'.",
        }

    async def submit_latest_approved_settlement_onchain(
        self, user: "User | UserPublicKey | None" = None, nonce: int | None = None
    ):
        approval, info = await self._prepare_settlement_execution(nonce, user)
        receipt = await self._execute_settlement(approval, info)
        print(f"Settlement submitted: {receipt.txn_hash}")

    async def _execute_settlement(self, approval, info):
        return await self.settlement_manager.execute_settlement(
            info,
            approval,
            token_in=to_evm_address(info.asset_in),
            token_out=to_evm_address(info.asset_out),
            sender=self.settler_executor,
        )

    async def _prepare_settlement_execution(self, nonce, user):
        if user:
            if not isinstance(user, str):
                user = user.public_key
        else:
            user = self.default_user.public_key

        approvals = self._pending_settlements[f"{user}"]
        if not approvals:
            raise ValueError(f"No approvals for user '{user}'")

        if nonce is None:
            nonce = max(approvals.keys())

        info, approval = approvals[nonce]
        return approval, info

    async def init_withdrawal(
        self,
        asset: AssetAddress,
        amount: Amount,
        user: "User | None" = None,
        target: "Address32 | str | None" = None,
        nonce: int | None = None,
    ) -> WithdrawalInfo:
        user = user or self.default_user
        key = f"{user.public_key}"
        self._pending_withdrawals.setdefault(key, {})
        self._pending_withdrawal_errors.pop(key, None)

        try:
            info = await self.withdrawal_manager.init_withdrawal(
                asset,
                amount.amount,
                target=target,
                user=user,
                nonce=nonce,
            )
        except BaseException as err:
            self._pending_withdrawal_errors[key] = err
            raise

        self._pending_withdrawals[key][info.nonce] = (info, None)
        return info

    async def wait_for_withdrawal_approval_result(
        self,
        user: "UserPublicKey | User | None" = None,
        nonce: int | None = None,
        timeout: float = 30.0,
        poll_interval: float = 1.0,
    ) -> dict[str, bool | str | None]:
        if user:
            user_pubkey = user if isinstance(user, str) else user.public_key
        else:
            user_pubkey = self.default_user.public_key

        key = f"{user_pubkey}"

        if key in self._pending_withdrawal_errors:
            err = self._pending_withdrawal_errors.pop(key)
            return {"success": False, "reason": str(err)}

        pending = self._pending_withdrawals.get(key, {})
        if not pending:
            return {
                "success": False,
                "reason": f"No withdrawals initiated for user '{user_pubkey}'.",
            }

        target_nonce = nonce if nonce is not None else max(pending.keys())
        info, _ = pending[target_nonce]

        try:
            approvals = await self.withdrawal_manager._wait_for_approvals(
                user_pubkey, target_nonce, poll_interval, timeout
            )
        except TimeoutError as err:
            return {"success": False, "reason": str(err)}

        self._pending_withdrawals[key][target_nonce] = (info, approvals)
        return {"success": True, "reason": None, "approvals": approvals}

    async def submit_approved_withdrawal_onchain(
        self,
        info: WithdrawalInfo,
        approvals: list[dict],
        user: "User | None" = None,
    ):
        user = user or self.default_user
        return await self.withdrawal_manager.execute_withdrawal(info, approvals, user=user)

    async def submit_latest_approved_withdrawal_onchain(
        self, user: "User | None" = None, nonce: int | None = None
    ):
        user = user or self.default_user
        key = f"{user.public_key}"
        pending = self._pending_withdrawals.get(key, {})
        if not pending:
            raise ValueError(f"No pending withdrawals for user '{key}'")

        if nonce is None:
            nonce = max(pending.keys())

        info, approvals = pending[nonce]
        if not approvals:
            raise ValueError(f"No approvals fetched for withdrawal nonce {nonce}")

        receipt = await self.withdrawal_manager.execute_withdrawal(info, approvals, user=user)
        print(f"Withdrawal submitted: {receipt.txn_hash}")

    async def verify_inventory(
        self,
        user: "User | UserPublicKey | None" = None,
        sub_account: int | None = None,
        asset: AssetIdentifier | None = None,
        expected_amount: int | None = None,
        expected_quote: int | None = None,
        spot: bool = False,
        expected_spot_usd: int | None = None,
        retries: int = 5,
        delay: float = 1.0,
    ):
        if user:
            if not isinstance(user, str):
                user = user.public_key
        else:
            user = self.default_user.public_key

        if sub_account is None:
            sub_account = self.default_user.sub_account

        asset = asset or self.weth.asset_identifier

        last_error: Exception | None = None

        for attempt in range(1, retries + 1):
            response = await self.ce_client.admin.get_user_inventory(user)
            account = response["accounts"][f"{sub_account}"]

            try:
                if spot:
                    asset_inv = int(account["spot"].get(f"{asset}", "0x0"), 16)
                    usd_inv = int(account["spot"].get("0", "0x0"), 16)

                    if expected_amount is not None and asset_inv != expected_amount:
                        raise ValueError(f"Spot '{asset_inv}' != expected '{expected_amount}'")

                    if expected_spot_usd is not None and usd_inv != expected_spot_usd:
                        raise ValueError(f"Spot USD '{usd_inv}' != expected '{expected_spot_usd}'")

                    print(f"Spot {asset} balance: {asset_inv}")
                    print(f"Spot USD balance: {usd_inv}")
                    return

                inventory = account["margins"][f"{asset}"]
                asset_inv = int(inventory["asset"]["credits"], 16) - int(
                    inventory["asset"]["liabilities"], 16
                )
                quote_inv = int(inventory["quote"]["credits"], 16) - int(
                    inventory["quote"]["liabilities"], 16
                )

                if expected_amount is not None and asset_inv != expected_amount:
                    raise ValueError(f"Amount '{asset_inv}' != expected '{expected_amount}'")

                if expected_quote is not None and quote_inv != expected_quote:
                    raise ValueError(f"Quote '{quote_inv}' != expected '{expected_quote}'")

                print(f"Asset inventory amount: {asset_inv}")
                print(f"Quote inventory amount: {quote_inv}")
                return

            except (ValueError, KeyError) as err:
                last_error = err if isinstance(err, ValueError) else ValueError(str(err))

                if attempt == retries:
                    break

                print(
                    f"[verify_inventory] attempt {attempt}/{retries} failed — retrying in {delay}s"
                )
                await asyncio.sleep(delay)

        raise last_error or RuntimeError("Inventory verification failed")
