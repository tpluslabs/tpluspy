"""GovernanceCore operations: digests, operator keys and signed op types."""

from collections.abc import Callable
from functools import cached_property
from typing import TYPE_CHECKING, Any, NamedTuple, Protocol

from cryptography.hazmat.primitives.asymmetric import ec
from eip712 import EIP712Domain
from eth_abi import encode
from eth_account import Account
from eth_keys import keys
from eth_pydantic_types.hex.bytes import HexBytes, HexBytes32
from eth_utils import is_hex, is_hex_address, keccak, to_canonical_address, to_checksum_address
from eth_utils.abi import get_aligned_abi_inputs
from pydantic import BaseModel, ConfigDict, Field

from tplus.evm._manifest import get_abi
from tplus.evm.backends import get_backend
from tplus.evm.exceptions import ContractLogicError
from tplus.utils.operator import SECP256K1_HALF_ORDER, SECP256K1_ORDER
from tplus.utils.user.model import EvmAccount, is_ape_account, resolve_ape_account

if TYPE_CHECKING:
    from tplus.evm.backends.base import EVMBackend

APPROVAL_LIFETIME_SECS = 3_600
GOVERNANCE_DOMAIN_NAME = "TplusGovernanceCore"
GOVERNANCE_DOMAIN_VERSION = "1"
ETHEREUM_V_OFFSET = 27
CREDENTIAL_MANAGER_CONTRACT_NAME = "CredentialManager"
CHAIN_KEYED_PARAM_TYPES = {
    "ADD_VAULT": ["uint8", "uint256", "bytes32", "struct CredentialManager.ChainConfig"],
    "REGISTER_STRATEGY": ["uint8", "uint256", "address", "bytes32"],
    "REPLACE_STRATEGY": ["uint8", "uint256", "address", "address", "bytes32"],
}
OPERATION_PARAM_TYPES = {
    **CHAIN_KEYED_PARAM_TYPES,
    "SET_WITHDRAWAL_QUORUM": ["uint256"],
    "SET_PROFILE_REGISTRY": ["address"],
}
STRATEGY_OP_NAMES = ("REGISTER_STRATEGY", "REPLACE_STRATEGY")
REGISTRY_CONTRACT_NAME = "Registry"
REGISTRY_TOKEN_LIMIT_PARAM_TYPES = ["struct Registry.ChainId", "uint16", "bytes32", "uint256"]
REGISTRY_OPERATION_PARAM_TYPES = {
    "RISK_PARAMETERS": ["uint16", "struct Registry.RiskParameters"],
    "ORACLE_CONFIG": ["uint16", "struct Registry.OracleConfig"],
    "WITHDRAWAL_DELAY_PARAMETERS": ["struct Registry.WithdrawalDelayParameters"],
    "ASSET_DATA": ["struct Registry.AssetData"],
    "MAX_DEPOSITS": REGISTRY_TOKEN_LIMIT_PARAM_TYPES,
    "MAX_1HR_DEPOSITS": REGISTRY_TOKEN_LIMIT_PARAM_TYPES,
    "MIN_WEIGHT": REGISTRY_TOKEN_LIMIT_PARAM_TYPES,
    "RISK_COUNCIL": ["address[]", "uint256"],
    "REPRESENTATION_CONFIG": [
        "struct Registry.ChainId",
        "bytes32",
        "struct Registry.RepresentationConfig",
    ],
}
REGISTRY_INDEX_KEYED_OP_NAMES = ("RISK_PARAMETERS", "ORACLE_CONFIG")
REGISTRY_TOKEN_LIMIT_OP_NAMES = ("MAX_DEPOSITS", "MAX_1HR_DEPOSITS", "MIN_WEIGHT")
REGISTRY_TOKEN_PENDING_KEY_TYPES = ["bytes32", "uint64", "uint64", "uint16", "bytes32"]
STRUCT_TYPE_PREFIX = "struct "
SCHEDULE_TYPEHASH = keccak(
    text="Schedule(bytes32 opType,bytes32 key,bytes32 paramsHash,uint256 nonce,uint256 deadline)"
)
SET_DELAY_BOUNDS_OP_TYPE = keccak(text="SET_DELAY_BOUNDS")
PUBLIC_KEY_RECOVERY_DIGEST = keccak(text="CredentialManager.operatorPublicKey")
ATTESTATION_PACKET_TAG = keccak(text="TPLUS_ATTESTATION_PACKET_V1")
OPERATION_PENDING_STATUS = 1
OPERATION_EXECUTED_STATUS = 2
PUBLIC_KEY_BYTES = 64
UNCOMPRESSED_KEY_PREFIX = b"\x04"


class DigestSigner(Protocol):
    address: str

    def sign_digest(self, digest: bytes) -> bytes: ...


class SignatureBundle(NamedTuple):
    """Signers sorted by address, with each one's signature over the same digest."""

    signers: list[str]
    """The signing members, in ascending address order."""

    signatures: list[bytes]
    """Each signer's signature, in the same order as `signers`."""


class ScheduleApproval(NamedTuple):
    """The nonce, deadline and signature bundle that schedule one operation."""

    nonce: int
    """The schedule nonce the signatures cover; one past the host's last."""

    deadline_secs: int
    """Unix time after which the signatures no longer schedule."""

    signers: list[str]
    """The signing members, in ascending address order."""

    signatures: list[bytes]
    """Each signer's signature, in the same order as `signers`."""


class RegistryOperation(NamedTuple):
    """A Registry operation's op type, pending key and ABI-encoded params."""

    op_type: bytes
    """The operation's type."""

    key: bytes
    """The slot the operation is pending under."""

    params: bytes
    """The full ABI-encoded params."""


class DelayChange(NamedTuple):
    """A delay bounds change's pending key and ABI-encoded params."""

    key: bytes
    """The slot the change is pending under."""

    params: bytes
    """The full ABI-encoded params."""


class AlignedParams(NamedTuple):
    """ABI types and the values aligned to them, ready for `eth_abi.encode`."""

    types: list[str]
    values: list


class OperationScheduled(BaseModel):
    """A GovernanceCore `OperationScheduled` event."""

    model_config = ConfigDict(populate_by_name=True)

    op_id: HexBytes32 = Field(alias="opId")
    """The new operation's ID."""

    op_type: HexBytes32 = Field(alias="opType")
    """The operation's type."""

    key: HexBytes32
    """The slot the operation is pending under."""

    lower_eta_secs: int = Field(alias="lowerEtaSeconds")
    """Earliest timestamp at which a council-approved execute succeeds."""

    upper_eta_secs: int = Field(alias="upperEtaSeconds")
    """Earliest timestamp at which anyone can execute."""

    parameters: HexBytes
    """The full ABI-encoded params."""

    signers: list[str]
    """The approving members; empty for a self-authorized schedule."""

    @classmethod
    def from_receipt(
        cls, receipt: Any, contract: Any, backend: "EVMBackend"
    ) -> "OperationScheduled":
        return cls.model_validate(backend.get_event_args(receipt, contract, "OperationScheduled"))


class OperatorKey:
    """A CE operator's secp256k1 key, signing CredentialManager digests."""

    def __init__(self, signer: "str | EvmAccount"):
        self.account = Account.from_key(signer) if isinstance(signer, str) else signer

    @classmethod
    def create(cls) -> "OperatorKey":
        return cls(Account.create().key.to_0x_hex())

    @classmethod
    def from_ape_account(cls, account: "str | EvmAccount") -> "OperatorKey":
        return cls(resolve_ape_account(account))

    @property
    def address(self) -> str:
        return self.account.address

    @cached_property
    def public_key(self) -> bytes:
        if not is_ape_account(self.account):
            return compute_public_key(self.account.key)

        return recover_public_key(
            PUBLIC_KEY_RECOVERY_DIGEST, self.sign_digest(PUBLIC_KEY_RECOVERY_DIGEST)
        )

    def sign_digest(self, digest: bytes) -> bytes:
        if not is_ape_account(self.account):
            signature = self.account.unsafe_sign_hash(digest)
            return encode_low_s_signature(
                signature.v, signature.r.to_bytes(32, "big"), signature.s.to_bytes(32, "big")
            )

        message_signature = self.account.sign_raw_msghash(digest)
        if message_signature is None:
            raise ValueError(f"{self.address} declined to sign {digest.hex()}")

        signature = encode_low_s_signature(*message_signature)
        if compute_operator_address(recover_public_key(digest, signature)) != self.address:
            raise ValueError(f"{self.address} produced a signature recovering another signer")

        return signature


def to_operator_key(account: "OperatorKey | str | Any") -> "OperatorKey":
    """An `OperatorKey` for a private key, an Ape account, or a backend account with a local key."""
    if isinstance(account, OperatorKey):
        return account

    if isinstance(account, str):
        return OperatorKey(account)

    if is_ape_account(account):
        return OperatorKey.from_ape_account(account)

    local_account = getattr(account, "local", account)
    if not hasattr(local_account, "key"):
        raise ValueError(f"{account.address} has no local signing key")

    return OperatorKey(local_account)


def parse_operator_public_key(value: str) -> bytes:
    """An operator's public key from `ADDRESS:PUBLIC_KEY`, a bare public key or an Ape account alias."""
    address, separator, key_hex = value.partition(":")
    if separator and is_hex_address(address):
        public_key = decode_public_key(key_hex)
        if compute_operator_address(public_key) != to_checksum_address(address):
            raise ValueError(f"public key {key_hex} does not derive operator {address}")

        return public_key

    if is_hex_address(value):
        raise ValueError(
            f"{value} is an address; pass ADDRESS:PUBLIC_KEY, a public key or an Ape account alias, "
            "since a public key cannot be recovered from an address"
        )

    if is_public_key_hex(value):
        return decode_public_key(value)

    return OperatorKey.from_ape_account(value).public_key


def is_public_key_hex(value: str) -> bool:
    digits = value.removeprefix("0x")
    return len(digits) in (2 * PUBLIC_KEY_BYTES, 2 * PUBLIC_KEY_BYTES + 2) and is_hex(digits)


def decode_public_key(key_hex: str) -> bytes:
    """A 64-byte secp256k1 public key from hex, accepting the uncompressed `04` prefix."""
    public_key = bytes.fromhex(key_hex.removeprefix("0x"))
    if len(public_key) == PUBLIC_KEY_BYTES + 1 and public_key.startswith(UNCOMPRESSED_KEY_PREFIX):
        public_key = public_key[1:]

    if len(public_key) != PUBLIC_KEY_BYTES:
        raise ValueError(f"a public key is {PUBLIC_KEY_BYTES} bytes, got {len(public_key)}")

    try:
        ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256K1(), UNCOMPRESSED_KEY_PREFIX + public_key
        )
    except ValueError as err:
        raise ValueError(f"{key_hex} is not a point on secp256k1") from err

    return public_key


def compute_majority_threshold(member_count: int) -> int:
    """The strict-majority signature threshold of a council of ``member_count`` members."""
    return member_count // 2 + 1


def compute_op_type(name: str, contract_name: str = CREDENTIAL_MANAGER_CONTRACT_NAME) -> bytes:
    return keccak(text=f"{contract_name}.{name}")


def compute_public_key(private_key) -> bytes:
    return keys.PrivateKey(bytes(Account.from_key(private_key).key)).public_key.to_bytes()


def compute_operator_address(public_key: bytes) -> str:
    return to_checksum_address(keccak(public_key)[-20:])


def compute_code_hash(address: str, backend: "EVMBackend | None" = None) -> bytes:
    return keccak((backend or get_backend()).get_code(address))


def compute_operation_key(name: str, deployment_type: bytes, values: list) -> bytes:
    if name not in CHAIN_KEYED_PARAM_TYPES:
        return deployment_type

    return keccak(encode(["bytes32", "uint8", "uint256"], [deployment_type, *values[:2]]))


def build_registry_operation(name: str, values: list) -> RegistryOperation:
    aligned = align_params(REGISTRY_CONTRACT_NAME, REGISTRY_OPERATION_PARAM_TYPES[name], values)
    op_type = compute_op_type(name, REGISTRY_CONTRACT_NAME)
    return RegistryOperation(
        op_type=op_type,
        key=compute_registry_operation_key(name, op_type, aligned.values),
        params=encode(*aligned),
    )


def align_params(contract_name: str, type_names: list[str], values: list) -> AlignedParams:
    """`values` aligned to `type_names`, resolving each `struct` from `contract_name`'s ABI."""
    contract_abi = get_abi(contract_name)
    function_abi = {
        "type": "function",
        "inputs": [build_param_abi(contract_abi, type_name) for type_name in type_names],
    }
    types, aligned_values = get_aligned_abi_inputs(
        function_abi, [convert_to_abi_value(value) for value in values]
    )
    return AlignedParams(types=list(types), values=list(aligned_values))


def convert_to_abi_value(value: Any) -> Any:
    """A model as the dict of its aliased fields, keeping byte values as bytes."""
    if not isinstance(value, BaseModel):
        return value

    return {
        field.alias or name: convert_to_abi_value(getattr(value, name))
        for name, field in type(value).model_fields.items()
    }


def build_param_abi(abi: list[dict[str, Any]], type_name: str) -> dict[str, Any]:
    """The ABI parameter of a Solidity type, resolving `struct <Contract>.<Name>` from `abi`."""
    if not type_name.startswith(STRUCT_TYPE_PREFIX):
        return {"type": type_name}

    for entry in abi:
        for param in [*entry.get("inputs", []), *entry.get("outputs", [])]:
            if param.get("internalType", "").removesuffix("[]") == type_name:
                return {
                    "type": param["type"].removesuffix("[]"),
                    "internalType": type_name,
                    "components": param["components"],
                }

    raise ValueError(f"the ABI has no {type_name}")


def compute_registry_operation_key(name: str, op_type: bytes, values: list) -> bytes:
    if name in REGISTRY_INDEX_KEYED_OP_NAMES:
        return keccak(encode(["bytes32", "uint16"], [op_type, values[0]]))

    if name == "ASSET_DATA":
        index, asset_address, chain = values[0][:3]
        return compute_registry_token_key(op_type, chain, index, asset_address)

    if name in REGISTRY_TOKEN_LIMIT_OP_NAMES:
        chain, index, asset_address = values[:3]
        return compute_registry_token_key(op_type, chain, index, asset_address)

    if name == "REPRESENTATION_CONFIG":
        chain, token = values[:2]
        return compute_registry_representation_key(op_type, chain, token)

    return op_type


def compute_registry_token_key(op_type: bytes, chain: list, index: int, asset_address) -> bytes:
    return keccak(encode(REGISTRY_TOKEN_PENDING_KEY_TYPES, [op_type, *chain, index, asset_address]))


def compute_registry_representation_key(op_type: bytes, chain: list, token: bytes) -> bytes:
    token_key = keccak(encode(["uint64", "uint64", "bytes32"], [*chain, token]))
    return keccak(encode(["bytes32", "bytes32"], [op_type, token_key]))


def compute_domain_separator(universe_id: bytes) -> bytes:
    """EIP-712 domain separator GovernanceCore signs under in one universe."""
    domain = EIP712Domain(
        name=GOVERNANCE_DOMAIN_NAME, version=GOVERNANCE_DOMAIN_VERSION, salt=universe_id
    )
    return bytes(domain.separator)


def compute_schedule_digest(
    domain_separator: bytes,
    signed_op_type: bytes,
    key: bytes,
    params: bytes,
    nonce: int,
    deadline_secs: int,
) -> bytes:
    struct_hash = keccak(
        encode(
            ["bytes32", "bytes32", "bytes32", "bytes32", "uint256", "uint256"],
            [SCHEDULE_TYPEHASH, signed_op_type, key, keccak(params), nonce, deadline_secs],
        )
    )
    return keccak(b"\x19\x01" + domain_separator + struct_hash)


def build_attestation_packet(
    domain_separator: bytes, raw_quote: bytes, sequence: int, operator: OperatorKey
) -> tuple[bytes, bytes]:
    """An attestation packet's digest and the operator key's signature over it."""
    digest = keccak(
        encode(
            ["bytes32", "bytes32", "bytes32", "uint256"],
            [ATTESTATION_PACKET_TAG, domain_separator, keccak(raw_quote), sequence],
        )
    )
    return digest, operator.sign_digest(digest)


def build_mock_quote(signer_key: str, operator: str) -> bytes:
    """A quote a manager with no verifier reads as its report data: the signer key, then the operator."""
    return to_canonical_address(signer_key) + to_canonical_address(operator)


def encode_low_s_signature(recovery_id: int, r_bytes: bytes, s_bytes: bytes) -> bytes:
    """The 65-byte `r || s || v` signature the CredentialManager recovers, with `s` low."""
    parity = recovery_id - ETHEREUM_V_OFFSET if recovery_id >= ETHEREUM_V_OFFSET else recovery_id
    s_value = int.from_bytes(s_bytes, "big")
    if s_value > SECP256K1_HALF_ORDER:
        s_value = SECP256K1_ORDER - s_value
        parity ^= 1

    return (
        int.from_bytes(r_bytes, "big").to_bytes(32, "big")
        + s_value.to_bytes(32, "big")
        + bytes([parity + ETHEREUM_V_OFFSET])
    )


def recover_public_key(digest: bytes, signature: bytes) -> bytes:
    vrs_signature = keys.Signature(signature[:64] + bytes([signature[64] - ETHEREUM_V_OFFSET]))
    return vrs_signature.recover_public_key_from_msg_hash(digest).to_bytes()


def sign_bundle(signers: list[DigestSigner], digest: bytes) -> SignatureBundle:
    if not signers:
        raise ValueError("a signature bundle needs at least one signer")

    sorted_signers = sorted(signers, key=lambda signer: int(signer.address, 16))
    return SignatureBundle(
        signers=[signer.address for signer in sorted_signers],
        signatures=[signer.sign_digest(digest) for signer in sorted_signers],
    )


def sign_schedule(
    contract: Any,
    signed_op_type: bytes,
    key: bytes,
    params: bytes,
    *,
    signers: list[DigestSigner],
    backend: "EVMBackend",
) -> ScheduleApproval:
    nonce = contract.governanceNonces().lastScheduleNonce + 1
    deadline_secs = backend.pending_timestamp + APPROVAL_LIFETIME_SECS
    digest = compute_schedule_digest(
        bytes(contract.domainSeparator()), signed_op_type, key, params, nonce, deadline_secs
    )
    return ScheduleApproval(nonce, deadline_secs, *sign_bundle(signers, digest))


def schedule_operation(
    contract: Any,
    op_type: bytes,
    key: bytes,
    params: bytes,
    *,
    signers: list[DigestSigner],
    sender: Any,
    signed_op_type: bytes | None = None,
    backend: "EVMBackend | None" = None,
    **tx_kwargs: Any,
) -> OperationScheduled:
    backend = backend or get_backend()
    nonce, deadline_secs, signer_addresses, signatures = sign_schedule(
        contract, signed_op_type or op_type, key, params, signers=signers, backend=backend
    )
    receipt = contract.scheduleOperation(
        op_type,
        params,
        nonce,
        deadline_secs,
        signer_addresses,
        signatures,
        sender=sender,
        **tx_kwargs,
    )
    return OperationScheduled.from_receipt(receipt, contract, backend)


def build_delay_change(target_op_type: bytes, lower_secs: int, upper_secs: int) -> DelayChange:
    return DelayChange(
        key=keccak(encode(["bytes32", "bytes32"], [SET_DELAY_BOUNDS_OP_TYPE, target_op_type])),
        params=encode(["bytes32", "uint64", "uint64"], [target_op_type, lower_secs, upper_secs]),
    )


def execute_operation(
    contract: Any, op_id: bytes, op_type: bytes, params: bytes, *, sender: Any, **tx_kwargs: Any
) -> Any:
    return contract.executeOperation(op_id, op_type, params, [], [], sender=sender, **tx_kwargs)


def execute_unless_executed(execute: Callable[[], Any], is_executed: Callable[[], bool]) -> None:
    """Run `execute`, counting an execute by another caller as success."""
    if is_executed():
        return

    try:
        execute()
    except ContractLogicError:
        if not is_executed():
            raise


def apply_operation(
    manager: Any,
    name: str,
    values: list,
    *,
    operator_signers: list[DigestSigner],
    sender: Any,
    backend: "EVMBackend | None" = None,
    **tx_kwargs: Any,
) -> bytes:
    """Schedule and execute a zero-delay op type on `manager`; returns its operation ID."""
    backend = backend or get_backend()
    if name in STRATEGY_OP_NAMES:
        values = [*values, compute_code_hash(values[-1], backend)]

    op_type = compute_op_type(name)
    deployment_type = bytes(manager.deploymentOpType(op_type))
    key = compute_operation_key(name, deployment_type, values)
    params = encode(
        *align_params(CREDENTIAL_MANAGER_CONTRACT_NAME, OPERATION_PARAM_TYPES[name], values)
    )
    schedule_event = schedule_operation(
        manager,
        op_type,
        key,
        params,
        signers=operator_signers,
        sender=sender,
        signed_op_type=deployment_type,
        backend=backend,
        **tx_kwargs,
    )
    op_id = bytes(schedule_event.op_id)
    execute_unless_executed(
        lambda: execute_operation(manager, op_id, op_type, params, sender=sender, **tx_kwargs),
        lambda: is_operation_executed(manager, op_id),
    )

    return op_id


def is_operation_due(schedule_event: OperationScheduled, backend: "EVMBackend") -> bool:
    """Whether the next block may execute the operation `schedule_event` scheduled, unsigned."""
    return backend.pending_timestamp >= schedule_event.upper_eta_secs


def is_operation_executed(manager: Any, op_id: bytes) -> bool:
    return int(manager.operation(op_id).status) == OPERATION_EXECUTED_STATUS
