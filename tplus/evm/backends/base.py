from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any

from tplus.evm.abi import get_erc20_abi

try:
    from ape.types.address import AddressType as _ApeAddressType
except ImportError:
    _ApeAddressType = None  # type: ignore[assignment]

# An EOA in whatever form the active backend understands (web3: a hex key, an
# ``eth_account.LocalAccount``, or an unlocked address; ape: an ``AccountAPI``).
AccountLike = Any
AddressType = str


class ContractHandle(ABC):
    """
    A backend-neutral handle to one deployed contract. Attribute access
    (``handle.someMethod(...)``) dispatches to :meth:`call` or :meth:`transact`
    based on the ABI's state mutability.
    """

    name: str
    address: str
    abi: list[dict[str, Any]]
    backend: EVMBackend

    @abstractmethod
    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Invoke a read-only (``view``/``pure``) method."""

    @abstractmethod
    def transact(
        self, method: str, *args: Any, sender: AccountLike | None = None, **tx_kwargs: Any
    ) -> Any:
        """Send a state-changing transaction; returns the backend's receipt object."""

    # Set in ``__init__``; never resolved through ABI dispatch / ``__getattr__``.
    _RESERVED = ("name", "address", "abi", "backend")

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name in self._RESERVED:
            raise AttributeError(name)

        entry = self._function_abi(name)
        if entry is None:
            raise AttributeError(f"{self.__class__.__name__!s} has no method '{name}'.")

        if entry.get("stateMutability") in ("view", "pure"):
            return lambda *args, **kwargs: self.call(name, *args, **kwargs)

        return lambda *args, **kwargs: self.transact(name, *args, **kwargs)

    def _function_abi(self, name: str) -> dict[str, Any] | None:
        for entry in self.abi or []:
            if entry.get("type") == "function" and entry.get("name") == name:
                return entry

        return None

    # Lets ``ape.convert(handle, AddressType)`` work when Ape is installed.
    def is_convertible(self, to_type: type) -> bool:
        return _ApeAddressType is not None and to_type is _ApeAddressType

    def convert_to(self, to_type: type) -> Any:
        if _ApeAddressType is None:
            raise TypeError(f"Cannot convert {self!r} (Ape not installed).")

        if to_type is _ApeAddressType:
            return self.address

        raise TypeError(f"Cannot convert {self!r} to {to_type!r}.")

    def __repr__(self) -> str:
        label = self.name or self.__class__.__name__
        return f"<{label} {self.address}>"


class EVMBackend(ABC):
    """How ``tplus.evm`` talks to a chain (web3.py or Ape)."""

    name: str = "evm"

    @property
    @abstractmethod
    def chain_id(self) -> int:
        """The EVM chain id of the currently connected network."""

    @property
    @abstractmethod
    def is_local_network(self) -> bool:
        """True when connected to a local dev chain."""

    @property
    @abstractmethod
    def pending_timestamp(self) -> int:
        """A timestamp usable for ``validUntil``-style fields."""

    @abstractmethod
    def get_storage(self, address: str, slot: int) -> bytes:
        """Read a 32-byte storage slot from ``address``."""

    def get_code(self, address: str) -> bytes:
        """The deployed bytecode at ``address`` (empty when nothing is deployed)."""
        raise NotImplementedError("get_code is not supported by this backend.")

    @abstractmethod
    def convert_address(self, value: Any) -> AddressType:
        """Coerce ``value`` (address str/bytes, contract handle, account, ...) to a checksum address."""

    @contextmanager
    def connect_to(self, chain_id: Any):  # noqa: ANN201 - generator context manager
        """
        Temporarily switch to ``chain_id``. The default only succeeds when it
        already matches the connected network; the Ape backend overrides this.
        """
        target = _vm_id(chain_id)
        if target is not None and target != self.chain_id:
            raise RuntimeError(
                f"This backend is connected to chain {self.chain_id}, not {target}. "
                "Reconnect to the right network (web3: set WEB3_PROVIDER_URI or pass rpc_url=)."
            )

        yield self

    @abstractmethod
    def get_contract(
        self, name: str, address: str, *, abi: list[dict[str, Any]] | None = None
    ) -> ContractHandle:
        """A handle to the contract ``name`` deployed at ``address``."""

    @abstractmethod
    def deploy_contract(
        self,
        name: str,
        *constructor_args: Any,
        sender: AccountLike | None = None,
        abi: list[dict[str, Any]] | None = None,
        bytecode: bytes | None = None,
        **kwargs: Any,
    ) -> ContractHandle:
        """Deploy contract ``name`` and return a handle to it."""

    def get_erc20(self, address: str) -> ContractHandle:
        """A handle to the ERC20 token at ``address`` (generic ERC20 ABI)."""
        return self.get_contract("ERC20", address, abi=get_erc20_abi())

    @abstractmethod
    def get_account(self, key_or_account: AccountLike | None) -> Any:
        """Normalize ``key_or_account`` into this backend's account object (has ``.address``)."""

    @abstractmethod
    def default_test_account(self) -> Any:
        """A funded dev account, when one is available (local networks only)."""

    @abstractmethod
    def sign_message(self, account: AccountLike, message: Any) -> bytes:
        """Sign ``message`` (raw bytes/text or an ``eip712.EIP712Message``); return 65-byte r||s||v."""

    # Dev helpers; not all backends/providers support these.
    def get_balance(self, address: Any) -> int:
        raise NotImplementedError("get_balance is not supported by this backend.")

    def set_balance(self, address: Any, amount: int) -> None:
        raise NotImplementedError("set_balance is only available on local dev backends.")

    def __repr__(self) -> str:
        return f"<{type(self).__name__} chain_id={self._safe_chain_id()}>"

    def _safe_chain_id(self) -> Any:
        try:
            return self.chain_id
        except Exception:
            return "?"


def _vm_id(chain_id: Any) -> int | None:
    """Best-effort integer EVM chain id from an int, a tplus ``ChainID``, or a str."""
    if chain_id is None:
        return None

    if isinstance(chain_id, int):
        return chain_id

    vm_id = getattr(chain_id, "vm_id", None)
    if isinstance(vm_id, int):
        return vm_id

    try:
        return int(chain_id)
    except (TypeError, ValueError):
        return None
