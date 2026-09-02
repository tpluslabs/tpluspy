from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from ape.api.convert import ConvertibleAPI
from ape.exceptions import ContractLogicError as ApeContractLogicError
from ape.types.address import AddressType
from ape.utils.basemodel import ManagerAccessMixin
from ethpm_types import ContractType

from tplus.evm.abi import get_erc20_abi
from tplus.evm.backends._ape_project import load_tplus_contracts_project
from tplus.evm.backends.base import ContractHandle, EVMBackend, _vm_id
from tplus.evm.exceptions import ContractLogicError, ContractNotExists

if TYPE_CHECKING:
    from ape.contracts.base import ContractInstance

# EVM chain id -> Ape network choice (used by ``connect_to``).
CHAIN_MAP = {
    1: "ethereum:mainnet",
    11155111: "ethereum:sepolia",
    42161: "arbitrum:mainnet",
    421614: "arbitrum:sepolia",
}

# Make ``ape.convert(handle, AddressType)`` work for any t+ contract handle.
# (``TPlusContract`` is registered the same way from ``tplus.evm.contracts``.)
ConvertibleAPI.register(ContractHandle)  # type: ignore[type-abstract]


def ape_is_active() -> bool:
    """True when Ape is connected to a network."""
    try:
        return ManagerAccessMixin.network_manager.active_provider is not None
    except Exception:
        return False


def ape_is_available() -> bool:
    """True when Ape is importable (always ``True`` here -- this module needs Ape)."""
    return True


class ApeContractHandle(ContractHandle):
    """Wraps an Ape ``ContractInstance``, delegating everything to it."""

    def __init__(self, backend: ApeBackend, name: str, instance: ContractInstance):
        self.backend = backend
        self.name = name
        self.instance = instance
        self.address = str(instance.address)
        try:
            self.abi = [
                m.model_dump(by_alias=True, exclude_none=True) for m in instance.contract_type.abi
            ]
        except Exception:
            self.abi = []

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        try:
            return getattr(self.instance, method)(*args, **kwargs)
        except Exception as err:
            translated = _translate_ape_error(err)
            if translated is err:
                raise

            raise translated from err

    def transact(self, method: str, *args: Any, sender: Any = None, **tx_kwargs: Any) -> Any:
        if sender is not None:
            tx_kwargs["sender"] = sender

        try:
            return getattr(self.instance, method)(*args, **tx_kwargs)
        except Exception as err:
            translated = _translate_ape_error(err)
            if translated is err:
                raise

            raise translated from err

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name in self._RESERVED or name == "instance":
            raise AttributeError(name)

        return getattr(self.__dict__["instance"], name)


class ApeBackend(EVMBackend):
    name = "ape"

    @property
    def chain_id(self) -> int:
        return ManagerAccessMixin.chain_manager.chain_id

    @property
    def is_local_network(self) -> bool:
        return ManagerAccessMixin.network_manager.provider.network.is_local

    @property
    def pending_timestamp(self) -> int:
        return ManagerAccessMixin.chain_manager.pending_timestamp

    def get_storage(self, address: str, slot: int) -> bytes:
        return bytes(ManagerAccessMixin.chain_manager.provider.get_storage(address, slot))

    def get_code(self, address: str) -> bytes:
        return bytes(ManagerAccessMixin.chain_manager.provider.get_code(address))

    def convert_address(self, value: Any) -> str:
        if isinstance(value, ContractHandle):
            value = value.address

        return ManagerAccessMixin.conversion_manager.convert(value, AddressType)

    @contextmanager
    def connect_to(self, chain_id: Any):
        target = _vm_id(chain_id)
        if target is None or target == self.chain_id:
            yield self
            return

        choice = CHAIN_MAP.get(target)
        if not choice:
            raise RuntimeError(f"Don't know how to connect to chain {target}.")

        with ManagerAccessMixin.network_manager.parse_network_choice(choice):
            yield self

    def _tplus_project(self, version: str | None = None):
        return load_tplus_contracts_project(version=version)

    def get_contract(
        self, name: str, address: str, *, abi: list[dict[str, Any]] | None = None
    ) -> ApeContractHandle:
        if abi is not None:
            contract_type = ContractType(contractName=name, abi=abi)  # type: ignore[arg-type]
            instance = ManagerAccessMixin.chain_manager.contracts.instance_at(
                address, contract_type=contract_type
            )
            return ApeContractHandle(self, name, instance)

        container = self._tplus_project().contracts.get(name)
        if container is None:
            raise ContractNotExists(f"Missing contract '{name}' from tplus contracts project.")

        instance = container.at(address, detect_proxy=False, fetch_from_explorer=False)
        return ApeContractHandle(self, name, instance)

    def get_erc20(self, address: str) -> ApeContractHandle:
        # Prefer the token's own (verified) ABI when Ape can resolve it.
        try:
            instance = ManagerAccessMixin.chain_manager.contracts.instance_at(address)
            return ApeContractHandle(self, "ERC20", instance)
        except Exception:
            return self.get_contract("ERC20", address, abi=get_erc20_abi())

    def deploy_contract(
        self,
        name: str,
        *constructor_args: Any,
        sender: Any = None,
        abi: list[dict[str, Any]] | None = None,
        bytecode: bytes | None = None,
        **kwargs: Any,
    ) -> ApeContractHandle:
        if sender is None:
            sender = self.default_test_account()

        version = kwargs.get("tplus_contracts_version")
        container = self._tplus_project(version=version).contracts.get(name)
        if container is None:
            raise ContractNotExists(f"Missing contract '{name}' from tplus contracts project.")

        instance = sender.deploy(container, *constructor_args)
        return ApeContractHandle(self, name, instance)

    def get_account(self, key_or_account: Any) -> Any:
        if key_or_account is None:
            return None

        if hasattr(key_or_account, "address") and not isinstance(key_or_account, str | bytes):
            return key_or_account

        if isinstance(key_or_account, str):
            try:
                return ManagerAccessMixin.account_manager[key_or_account]
            except Exception:
                return key_or_account

        return key_or_account

    def default_test_account(self) -> Any:
        return ManagerAccessMixin.account_manager.test_accounts[0]

    def sign_message(self, account: Any, message: Any) -> bytes:
        account = self.get_account(account)
        signature = account.sign_message(message)
        if signature is None:
            return b""

        return bytes(signature.encode_rsv())

    def get_balance(self, address: Any) -> int:
        if hasattr(address, "address"):
            address = address.address

        return ManagerAccessMixin.chain_manager.provider.get_balance(address)

    def set_balance(self, address: Any, amount: int) -> None:
        if hasattr(address, "address"):
            address = address.address

        ManagerAccessMixin.chain_manager.provider.set_balance(address, amount)


def _translate_ape_error(err: Exception) -> Exception:
    if isinstance(err, ApeContractLogicError):
        message = getattr(err, "message", "") or str(err)
        return ContractLogicError(message, data=getattr(err, "revert_message", None))

    return err
