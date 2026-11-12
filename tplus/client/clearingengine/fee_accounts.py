"""Operator-committee signed CE fee account settings."""

import hashlib
from typing import Any

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from tplus.client.clearingengine.base import BaseClearingEngineClient
from tplus.model.types import UserPublicKey
from tplus.utils.operator import load_operator_sk, sign_operator_payload


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
    keys = [load_operator_sk(secret) for secret in operator_secrets]
    public_keys = [
        key.public_key().public_bytes(Encoding.X962, PublicFormat.CompressedPoint).hex()
        for key in keys
    ]
    committee_hash = hashlib.sha256(
        "".join(sorted(public_keys)).encode("ascii") + threshold.to_bytes(8, "big")
    ).digest()
    domain = b"tplus.ce.set_trading_fee_account.v1" if trading else b"tplus.ce.set_fee_account.v1"
    value = bytes.fromhex(account)
    signing_bytes = (
        min_seq.to_bytes(8, "big")
        + max_seq.to_bytes(8, "big")
        + committee_hash
        + len(domain).to_bytes(8, "big")
        + domain
        + len(value).to_bytes(8, "big")
        + value
    )
    return {
        "payload": {
            "min_seq": min_seq,
            "max_seq": max_seq,
            "committee_hash": committee_hash.hex(),
            "fee_account": account,
        },
        "sigs": [
            {"signer": public_key, "signature": sign_operator_payload(signing_bytes, key)}
            for public_key, key in zip(public_keys, keys, strict=True)
        ],
    }


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
