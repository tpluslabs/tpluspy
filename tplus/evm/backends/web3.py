from __future__ import annotations

import os
from collections.abc import Sequence
from functools import cached_property
from typing import TYPE_CHECKING, Any

try:
    import rlp
    from eth_account import Account
    from eth_account.messages import SignableMessage, encode_defunct
    from eth_utils import keccak, to_checksum_address
    from web3 import Web3
    from web3._utils.abi import named_tree, recursive_dict_to_namedtuple
    from web3.auto import w3 as _auto_w3
    from web3.exceptions import ContractCustomError
    from web3.exceptions import ContractLogicError as Web3ContractLogicError
except ImportError as err:  # pragma: no cover - depends on the optional extra
    raise ImportError(
        'The web3 backend requires web3.py. Install it with: pip install "tpluspy[evm]".'
    ) from err

from tplus.evm._manifest import get_abi, get_deployment_bytecode
from tplus.evm.backends.base import ContractHandle, EVMBackend
from tplus.evm.exceptions import ContractLogicError

if TYPE_CHECKING:
    from eth_account.signers.local import LocalAccount
    from web3.contract import Contract

# Chain ids commonly used by local dev nodes (anvil, hardhat).
DEFAULT_LOCAL_CHAIN_IDS = frozenset({31337, 1337, 1338})

# Transaction params we forward from ``**tx_kwargs`` to web3 (others are dropped).
_TX_PARAM_KEYS = frozenset(
    {
        "value",
        "gas",
        "gasPrice",
        "maxFeePerGas",
        "maxPriorityFeePerGas",
        "nonce",
        "chainId",
        "type",
        "accessList",
    }
)


class Web3Account:
    """A backend-neutral account: knows its address; may hold a signing key."""

    def __init__(self, backend: Web3Backend, address: str, local: LocalAccount | None):
        self.backend = backend
        self.address = address
        # An ``eth_account.LocalAccount`` when we can sign locally; ``None`` for
        # an unlocked node account.
        self.local = local

    @property
    def can_sign(self) -> bool:
        return self.local is not None

    @property
    def nonce(self) -> int:
        return self.backend.w3.eth.get_transaction_count(self.address)

    def get_deployment_address(self, nonce: int | None = None) -> str:
        """The CREATE address a deploy from this account would produce.

        Defaults to the account's current nonce -- matching what ``_send`` uses
        for the deploy transaction, so callers can pre-compute and verify it.
        """
        nonce = self.nonce if nonce is None else nonce
        return _create_address(self.address, nonce)

    def sign_message(self, message: Any, /) -> Any:
        """Sign under EIP-191, returning what an ``eth_account`` signer returns."""
        if self.local is None:
            raise ValueError(
                "Signing requires an account with a private key (a hex key or eth_account "
                "LocalAccount), not an unlocked-only node account."
            )

        return self.local.sign_message(_to_signable_message(message))

    def __repr__(self) -> str:
        return f"<Web3Account {self.address} ({'key' if self.can_sign else 'unlocked'})>"


class Web3ContractHandle(ContractHandle):
    def __init__(
        self, backend: Web3Backend, name: str, contract: Contract, abi: list[dict[str, Any]]
    ):
        self.backend = backend
        self.name = name
        self.contract = contract
        self.abi = list(abi)
        self.address = str(contract.address)

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        entry = self._function_abi(method)
        fn = self._fn(method, args)
        try:
            raw = fn.call()
        except Exception as err:
            raise _translate_web3_error(err) from err

        return _decode_outputs(raw, (entry or {}).get("outputs", []))

    def transact(self, method: str, *args: Any, sender: Any = None, **tx_kwargs: Any) -> Any:
        account = self.backend.get_account(
            sender if sender is not None else tx_kwargs.pop("sender", None)
        )
        if account is None:
            raise ValueError(
                f"'{self.name}.{method}(...)' is a transaction; pass sender=<account>."
            )

        fn = self._fn(method, args)
        return self.backend._send(fn, account, self.backend._extract_tx_params(tx_kwargs))

    def _fn(self, method: str, args: Sequence[Any]):
        entry = self._function_abi(method)
        if entry is None:
            raise AttributeError(f"Contract '{self.name}' has no method '{method}'.")

        return self.contract.functions[method](
            *_encode_args(self.backend, entry.get("inputs", []), args)
        )


class Web3Backend(EVMBackend):
    name = "web3"

    def __init__(
        self,
        web3: Web3 | None = None,
        rpc_url: str | None = None,
        *,
        local_chain_ids: frozenset[int] | None = None,
        is_local: bool | None = None,
    ):
        self._web3 = web3
        self._rpc_url = rpc_url
        self._local_chain_ids = (
            local_chain_ids if local_chain_ids is not None else DEFAULT_LOCAL_CHAIN_IDS
        )
        self._is_local_override = is_local

    @cached_property
    def w3(self) -> Web3:
        if self._web3 is not None:
            return self._web3

        if self._rpc_url:
            url = self._rpc_url
            provider = (
                Web3.LegacyWebSocketProvider(url)
                if url.startswith(("ws://", "wss://"))
                else Web3.HTTPProvider(url)
            )
            return Web3(provider)

        if not os.environ.get("WEB3_PROVIDER_URI") and not _is_connected(_auto_w3):
            raise ConnectionError(
                "No reachable web3 provider. Set WEB3_PROVIDER_URI, or pass rpc_url=/web3= "
                "(see tplus.evm.use_web3)."
            )

        return _auto_w3

    @property
    def chain_id(self) -> int:
        return self.w3.eth.chain_id

    @property
    def is_local_network(self) -> bool:
        if self._is_local_override is not None:
            return self._is_local_override

        try:
            return self.chain_id in self._local_chain_ids
        except Exception:
            return False

    @property
    def pending_timestamp(self) -> int:
        try:
            return int(self.w3.eth.get_block("pending")["timestamp"])
        except Exception:
            return int(self.w3.eth.get_block("latest")["timestamp"]) + 12

    def get_storage(self, address: str, slot: int) -> bytes:
        return bytes(self.w3.eth.get_storage_at(self._checksum(address), slot))

    def get_code(self, address: str) -> bytes:
        return bytes(self.w3.eth.get_code(self._checksum(address)))

    def convert_address(self, value: Any) -> str:
        if isinstance(value, ContractHandle | Web3Account):
            return value.address

        if hasattr(value, "address") and not isinstance(value, str | bytes | bytearray):
            value = value.address

        if isinstance(value, bytes | bytearray):
            return self._checksum(bytes(value))

        if isinstance(value, str):
            return self._checksum(value)

        raise TypeError(f"Cannot interpret {value!r} as an address.")

    def _checksum(self, value: Any) -> str:
        return Web3.to_checksum_address(value)

    def get_contract(
        self, name: str, address: str, *, abi: list[dict[str, Any]] | None = None
    ) -> Web3ContractHandle:
        abi = abi if abi is not None else get_abi(name)
        contract = self.w3.eth.contract(address=self._checksum(address), abi=abi)
        return Web3ContractHandle(self, name, contract, abi)

    def deploy_contract(
        self,
        name: str,
        *constructor_args: Any,
        sender: Any = None,
        abi: list[dict[str, Any]] | None = None,
        bytecode: bytes | None = None,
        **kwargs: Any,
    ) -> Web3ContractHandle:
        account = self.get_account(sender)
        if account is None:
            raise ValueError(f"Deploying '{name}' requires sender=<account>.")

        abi = abi if abi is not None else get_abi(name)
        bytecode = bytecode if bytecode is not None else get_deployment_bytecode(name)
        factory = self.w3.eth.contract(abi=abi, bytecode=bytecode)

        ctor_inputs = next((e.get("inputs", []) for e in abi if e.get("type") == "constructor"), [])
        receipt = self._send(
            factory.constructor(*_encode_args(self, ctor_inputs, constructor_args)), account, {}
        )
        return self.get_contract(name, receipt["contractAddress"], abi=abi)

    def get_account(self, key_or_account: Any) -> Web3Account | None:
        if key_or_account is None:
            accounts = self._node_accounts()
            return Web3Account(self, accounts[0], None) if accounts else None

        if isinstance(key_or_account, Web3Account):
            return key_or_account

        # eth_account LocalAccount.
        if hasattr(key_or_account, "key") and hasattr(key_or_account, "address"):
            return Web3Account(self, self._checksum(key_or_account.address), key_or_account)

        if isinstance(key_or_account, bytes | bytearray) and len(key_or_account) == 32:
            local = Account.from_key(bytes(key_or_account))
            return Web3Account(self, self._checksum(local.address), local)

        if isinstance(key_or_account, str):
            if len(key_or_account.removeprefix("0x")) == 64:
                local = Account.from_key(key_or_account)
                return Web3Account(self, self._checksum(local.address), local)

            return Web3Account(self, self._checksum(key_or_account), None)  # unlocked address

        # Anything else exposing ``.address`` (e.g. an Ape account) -> unlocked.
        if hasattr(key_or_account, "address"):
            return Web3Account(self, self._checksum(key_or_account.address), None)

        raise TypeError(f"Cannot interpret {key_or_account!r} as an account.")

    def default_test_account(self) -> Web3Account | None:
        return self.get_account(None)

    def sign_message(self, account: Any, message: Any) -> bytes:
        acct = self.get_account(account)
        if acct is None or acct.local is None:
            raise ValueError(
                "Signing requires an account with a private key (a hex key or eth_account "
                "LocalAccount), not an unlocked-only node account."
            )

        signed = acct.local.sign_message(_to_signable_message(message))
        return bytes(signed.signature)

    def get_balance(self, address: Any) -> int:
        return self.w3.eth.get_balance(self.convert_address(address))

    def set_balance(self, address: Any, amount: int) -> None:
        addr = self.convert_address(address)
        for method in ("anvil_setBalance", "hardhat_setBalance"):
            try:
                self.w3.provider.make_request(method, [addr, hex(amount)])
                return
            except Exception:
                continue

        raise NotImplementedError("set_balance requires an anvil/hardhat dev node.")

    def _node_accounts(self) -> list[str]:
        try:
            return [self._checksum(a) for a in self.w3.eth.accounts]
        except Exception:
            return []

    def _extract_tx_params(self, tx_kwargs: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in tx_kwargs.items() if k in _TX_PARAM_KEYS and v is not None}

    def _send(self, fn: Any, account: Web3Account, tx_params: dict[str, Any]):
        params: dict[str, Any] = {"from": account.address, **tx_params}

        if account.local is not None:
            params.setdefault(
                "nonce",
                self.w3.eth.get_transaction_count(account.address),  # type: ignore[arg-type]
            )
            try:
                built = fn.build_transaction(params)
            except Exception as err:
                raise _translate_web3_error(err) from err

            signed = account.local.sign_transaction(built)
            # ``raw_transaction`` on eth-account >=0.13; older versions exposed ``rawTransaction``.
            raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction  # type: ignore[attr-defined]
            tx_hash = self.w3.eth.send_raw_transaction(raw)
        else:
            try:
                tx_hash = fn.transact(params)
            except Exception as err:
                raise _translate_web3_error(err) from err

        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.get("status") == 0:
            raise ContractLogicError("Transaction reverted.")

        return receipt


def _to_signable_message(message: Any):
    # eip712.EIP712Message (and Ape's EIP712 messages) expose ``signable_message``.
    signable = getattr(message, "signable_message", None)
    if signable is not None:
        return signable

    if isinstance(message, SignableMessage):
        return message

    if isinstance(message, bytes | bytearray):
        return encode_defunct(primitive=bytes(message))

    if isinstance(message, str):
        return encode_defunct(text=message)

    raise TypeError(f"Don't know how to sign {message!r}.")


# Web3.py is strict in ways t+ wire types trip over: it rejects bare (no-``0x``)
# hex for ``bytesN`` and *any* non-checksummed address (even all-lowercase).
# User keys serialize to 0x-less hex and struct fields carry un-checksummed
# addresses, so we normalize both here -- recursing through tuples/arrays so
# fields nested inside structs (settlement orders, withdrawals) get fixed too.
# Pydantic models are dumped to dicts and our account/handle wrappers resolved
# to ``.address`` along the way.


def _encode_args(
    backend: EVMBackend, abi_inputs: Sequence[dict[str, Any]], args: Sequence[Any]
) -> list[Any]:
    converted = [
        _encode_arg(backend, value, inp) for value, inp in zip(args, abi_inputs, strict=False)
    ]
    converted.extend(args[len(converted) :])  # pass extra positional args through untouched
    return converted


def _encode_arg(backend: EVMBackend, value: Any, abi_input: dict[str, Any]) -> Any:
    t = abi_input.get("type", "")

    if t == "address":
        return backend.convert_address(value)
    if t.startswith("address["):
        return [backend.convert_address(v) for v in value]

    if t.startswith("bytes"):  # ``bytes`` / ``bytesN`` and their arrays
        if t.endswith("]"):
            return [_to_bytes(v) for v in value]

        return _to_bytes(value)

    if t.startswith("tuple"):
        components = abi_input.get("components", [])
        if t != "tuple":  # tuple[] / tuple[N]
            return [_encode_tuple(backend, v, components) for v in value]

        return _encode_tuple(backend, value, components)

    return value


def _encode_tuple(backend: EVMBackend, value: Any, components: Sequence[dict[str, Any]]) -> Any:
    value = _pydantic_to_dict(value)
    by_name = {c.get("name"): c for c in components}

    if isinstance(value, dict):
        return {
            k: (_encode_arg(backend, v, by_name[k]) if k in by_name else v)
            for k, v in value.items()
        }

    if isinstance(value, list | tuple):
        return [_encode_arg(backend, v, c) for v, c in zip(value, components, strict=False)]

    return value


def _to_bytes(value: Any) -> Any:
    if isinstance(value, bytes | bytearray):
        return bytes(value)
    if isinstance(value, str):
        return bytes.fromhex(value[2:] if value.startswith(("0x", "0X")) else value)
    if isinstance(value, list | tuple):
        return bytes(value)

    return value  # ints and anything else: let web3 encode it


def _pydantic_to_dict(value: Any) -> Any:
    if not isinstance(value, dict) and hasattr(value, "model_dump"):
        return value.model_dump(mode="python", by_alias=True)

    return value


# Web3.py returns plain tuples for struct-typed outputs; we use its own
# ``named_tree`` / ``recursive_dict_to_namedtuple`` helpers to wrap them as
# attribute-accessible structs (matching Ape's ergonomics).


def _decode_outputs(value: Any, outputs: Sequence[dict[str, Any]]) -> Any:
    if not outputs:
        return value

    data = [value] if len(outputs) == 1 else list(value)
    wrapped = recursive_dict_to_namedtuple(named_tree(outputs, data))
    return wrapped[0] if len(outputs) == 1 else wrapped


def _create_address(sender: str, nonce: int) -> str:
    """The contract address produced by a CREATE (plain deploy) from ``sender``."""
    sender_bytes = bytes.fromhex(sender[2:] if sender.startswith(("0x", "0X")) else sender)
    nonce_bytes = b"" if nonce == 0 else nonce.to_bytes((nonce.bit_length() + 7) // 8, "big")
    return to_checksum_address(keccak(rlp.encode([sender_bytes, nonce_bytes]))[-20:])


def _is_connected(w3: Any) -> bool:
    try:
        return bool(w3.is_connected())
    except Exception:
        return False


def _translate_web3_error(err: Exception) -> Exception:
    if not isinstance(err, Web3ContractLogicError):
        return err

    data = getattr(err, "data", None)
    if isinstance(err, ContractCustomError) and isinstance(data, str):
        return ContractLogicError(data, data=data)  # surface the selector (+args) as the message

    message = getattr(err, "message", None) or str(err)
    return ContractLogicError(message, data=data if isinstance(data, str) else None)
