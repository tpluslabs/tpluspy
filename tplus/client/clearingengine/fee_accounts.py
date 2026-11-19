"""Operator-committee signed CE fee account settings."""

from typing import Any

from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.council import CouncilEnvelope, build_council_request
from tplus.model.types import UserPublicKey
from tplus.utils.operator import load_operator_signers


class SetFeeAccountPayload(CouncilEnvelope):
    fee_account: str


def build_set_fee_account_request(
    fee_account: UserPublicKey,
    operator_secrets: list[str],
    threshold: int,
    min_seq: int,
    max_seq: int,
    *,
    trading: bool = False,
) -> dict[str, Any]:
    """Sign either fee setting with the supplied committee members.

    The value is the recipient's 32 raw bytes. The two routes use distinct domains.
    ``committee_hash`` is retained in the signed envelope; the CE verifies signatures
    against its installed operator committee.
    """
    account = UserPublicKey.__validate_user__(fee_account)
    domain = b"tplus.ce.set_trading_fee_account.v1" if trading else b"tplus.ce.set_fee_account.v1"
    return build_council_request(
        SetFeeAccountPayload,
        {"fee_account": account},
        domain,
        bytes.fromhex(account),
        load_operator_signers(operator_secrets),
        threshold,
        min_seq,
        max_seq,
    ).model_dump(mode="json")


class FeeAccountClient(BaseClearingEngineClient):
    async def get_fee_account(self) -> UserPublicKey | None:
        account = await self._get("fee-account")
        return UserPublicKey.__validate_user__(account) if account is not None else None

    async def get_trading_fee_account(self) -> UserPublicKey | None:
        account = await self._get("trading-fee-account")
        return UserPublicKey.__validate_user__(account) if account is not None else None

    async def set_fee_account(
        self,
        fee_account: UserPublicKey,
        operator_secrets: list[str],
        threshold: int,
        min_seq: int,
        max_seq: int,
    ) -> None:
        await self._post(
            "fee-account/set",
            json_data=build_set_fee_account_request(
                fee_account,
                operator_secrets,
                threshold,
                min_seq,
                max_seq,
            ),
        )

    async def set_trading_fee_account(
        self,
        fee_account: UserPublicKey,
        operator_secrets: list[str],
        threshold: int,
        min_seq: int,
        max_seq: int,
    ) -> None:
        await self._post(
            "trading-fee-account/set",
            json_data=build_set_fee_account_request(
                fee_account,
                operator_secrets,
                threshold,
                min_seq,
                max_seq,
                trading=True,
            ),
        )
