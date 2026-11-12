import os
from collections.abc import Callable
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple, cast

from eth_abi import encode
from eth_pydantic_types.hex.bytes import HexBytes
from eth_utils import to_checksum_address
from eth_utils.abi import function_abi_to_4byte_selector, get_abi_input_types

from tplus.evm._manifest import get_abi
from tplus.evm.backends import ContractHandle, get_backend, resolve_backend
from tplus.evm.constants import LATEST_ARB_DEPOSIT_VAULT, REGISTRY_ADDRESS
from tplus.evm.exceptions import ContractLogicError, ContractNotExists
from tplus.evm.governance import (
    REGISTRY_CONTRACT_NAME,
    SET_DELAY_BOUNDS_OP_TYPE,
    OperationScheduled,
    ScheduleApproval,
    align_params,
    apply_operation,
    build_attestation_packet,
    build_delay_change,
    build_mock_quote,
    build_registry_operation,
    compute_majority_threshold,
    compute_op_type,
    compute_operator_address,
    convert_to_abi_value,
    execute_operation,
    execute_unless_executed,
    is_operation_due,
    schedule_operation,
    sign_schedule,
    to_operator_key,
)
from tplus.logger import get_logger
from tplus.model.asset_identifier import ChainAddress
from tplus.model.config import ChainConfig
from tplus.model.registry_asset import AssetData
from tplus.model.representation_rate import RegistryRepresentationConfig
from tplus.model.risk_parameters import RiskParameters
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.bytes32 import to_bytes32
from tplus.utils.hex import to_hex
from tplus.utils.universe import (
    DEV_UNIVERSE_ENVIRONMENT,
    build_dev_universe_name,
    compute_universe_id,
)

# Ape's ``AddressType`` / ``ConversionError`` are loaded lazily *at module
# import time* (not from inside functions): they're only needed when Ape is
# installed, so we set the names to ``None`` otherwise.
try:
    from ape.api.convert import ConvertibleAPI as _ApeConvertibleAPI
    from ape.exceptions import ConversionError as _ApeConversionError
    from ape.types.address import AddressType as _ApeAddressType
except ImportError:
    _ApeAddressType = None  # type: ignore[assignment,misc]
    _ApeConversionError = None  # type: ignore[assignment,misc]
    _ApeConvertibleAPI = None  # type: ignore[assignment,misc]

# Same pattern for the Ape ``tplus-contracts`` project loaders.
try:
    from tplus.evm.backends._ape_project import (
        load_tplus_contract_container as _load_tplus_contract_container_impl,
    )
    from tplus.evm.backends._ape_project import (
        load_tplus_contracts_project as _load_tplus_contracts_project_impl,
    )
except ImportError:
    _load_tplus_contracts_project_impl = None  # type: ignore[assignment]
    _load_tplus_contract_container_impl = None  # type: ignore[assignment]


if TYPE_CHECKING:
    from eth_pydantic_types.hex.bytes import HexBytes32

    from tplus.evm.backends.base import EVMBackend
    from tplus.evm.governance import OperatorKey
    from tplus.model.withdrawal import WithdrawalDelayParameters
    from tplus.utils.user import User

# A checksum-address string (aliased so annotations don't need Ape's AddressType).
AddressType = str

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
REPRESENTATION_CONFIG_PAGE_LIMIT = 1_000

logger = get_logger()

CHAIN_MAP = {
    1: "ethereum:mainnet",
    11155111: "ethereum:sepolia",
    143: "monad:mainnet",
    10143: "monad:testnet",
    42161: "arbitrum:mainnet",
    421614: "arbitrum:sepolia",
}
NETWORK_MAP = {
    "ethereum": {
        "mainnet": 1,
        "sepolia": 11155111,
    },
    "monad": {
        "mainnet": 143,
        "testnet": 10143,
    },
    "arbitrum": {
        "mainnet": 42161,
        "sepolia": 421614,
    },
}
DEFAULT_DEPLOYMENTS: dict = {
    42161: {"Registry": REGISTRY_ADDRESS, "DepositVault": LATEST_ARB_DEPOSIT_VAULT}
}


class TplusDeployments:
    """
    Reads the deployments from the ape-config file in the tplus-contracts
    repo. This saves 1 place at least where we have to remember to update
    new deployment addresses.
    """

    @cached_property
    def deployments(self) -> dict:
        import yaml

        contracts_path = Path(
            os.environ.get("TPLUS_CONTRACTS_PATH", "~/tplus/tplus-contracts")
        ).expanduser()
        file = contracts_path / "ape-config.yaml"

        if not file.is_file():
            return DEFAULT_DEPLOYMENTS

        registered = yaml.safe_load(file.read_text())["deployments"]
        result: dict = {}

        for ecosystem, network_deployments in registered.items():
            for network, deployments in network_deployments.items():
                if len(deployments) == 0:
                    continue

                elif not (chain_id := NETWORK_MAP.get(ecosystem, {}).get(network)):
                    continue

                for deployment in deployments:
                    result.setdefault(chain_id, {})
                    result[chain_id][deployment["contract_type"]] = deployment["address"]

        return result

    def __getitem__(self, chain_id: "int | ChainID") -> dict:
        if not isinstance(chain_id, int):
            chain_id = chain_id.vm_id

        return self.deployments[chain_id]

    def get(self, chain_id: "int | ChainID", default=None):
        if not isinstance(chain_id, int):
            chain_id = chain_id.vm_id

        return self.deployments.get(chain_id, default)


TPLUS_DEPLOYMENTS = TplusDeployments()


def load_tplus_contracts_project(version: str | None = None, allow_install: bool | None = None):
    """
    Loads the Ape project containing the Solidity contracts for tplus (Ape backend only).
    ``allow_install`` lets Ape install a missing ``tplus-contracts`` dependency; it defaults
    to the ``TPLUS_CONTRACTS_ALLOW_INSTALL`` env var.
    """
    if _load_tplus_contracts_project_impl is None:
        raise ImportError('Requires the Ape backend: pip install "tpluspy[evm-ape]".')

    return _load_tplus_contracts_project_impl(version=version, allow_install=allow_install)


def load_tplus_contract_container(
    name: str, version: str | None = None, allow_install: bool | None = None
):
    """The Ape ``ContractContainer`` for the named t+ contract (Ape backend only)."""
    if _load_tplus_contract_container_impl is None:
        raise ImportError('Requires the Ape backend: pip install "tpluspy[evm-ape]".')

    return _load_tplus_contract_container_impl(name, version=version, allow_install=allow_install)


def get_dev_default_owner() -> Any:
    """A funded development account from the active backend (local networks)."""
    return get_backend().default_test_account()


# ---------------------------------------------------------------------------
# Dev-network shortcut: before auto-redeploying, check whether the clearing
# engine already points at a live contract on this chain.
# ---------------------------------------------------------------------------

_DEFAULT_CE_URL = "http://127.0.0.1:3032"
_CE_TIMEOUT = 2.0

CANONICAL_MANAGER_ROLE = 0
"""The CredentialManager's ``ManagerRole.Canonical``: the universe's parent-chain manager."""

DEV_UNIVERSE_ID = bytes(compute_universe_id(build_dev_universe_name(DEV_UNIVERSE_ENVIRONMENT)))
"""Universe ID a dev CredentialManager deploys into by default."""
DEV_WITHDRAWAL_QUORUM = 1
"""Approvals a dev CredentialManager needs to release a withdrawal."""
DEV_TCB_EVALUATION_NUMBER = 0
"""TCB evaluation number of a dev attestation, which a manager with no verifier never reads."""
VAULT_PAGE_SIZE = 64


def _ce_base_url() -> str:
    return os.environ.get("TPLUS_CLEARING_BASE_URL") or _DEFAULT_CE_URL


def _ce_verify() -> bool:
    return os.environ.get("TPLUS_IGNORE_SSL", "").strip().lower() not in {"1", "true", "yes", "on"}


def _ce_get(endpoint: str):
    """Sync GET against the CE. Returns the parsed JSON, or None on any error."""
    import httpx

    url = f"{_ce_base_url().rstrip('/')}/{endpoint}"
    try:
        with httpx.Client(verify=_ce_verify(), timeout=_CE_TIMEOUT) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as err:
        logger.debug("CE address discovery failed for %s: %s", url, err)
        return None


def _ce_fetch_chain_address(endpoint: str) -> "ChainAddress | None":
    """Fetch a single ChainAddress from the CE."""
    data = _ce_get(endpoint)
    if data is None:
        return None

    try:
        return ChainAddress.model_validate(data)
    except Exception:
        return None


def _ce_fetch_first_chain_address(endpoint: str) -> "ChainAddress | None":
    """Fetch a list of ChainAddresses from the CE and return the first one."""
    return _ce_fetch_indexed_chain_address(endpoint, 0)


def _ce_fetch_last_chain_address(endpoint: str) -> "ChainAddress | None":
    """Fetch a list of ChainAddresses from the CE and return the last one."""
    return _ce_fetch_indexed_chain_address(endpoint, -1)


def _ce_fetch_indexed_chain_address(endpoint: str, index: int) -> "ChainAddress | None":
    data = _ce_get(endpoint)
    if not data:
        return None

    try:
        return ChainAddress.model_validate(data[index])
    except Exception:
        return None


def to_registry_token(address: "HexBytes32 | AddressType") -> "HexBytes32 | AddressType":
    if isinstance(address, str) and len(address) <= 42:
        return to_bytes32(address, pad="r")

    return address


def decode_registry_chain_address(address: bytes, chain: Any) -> ChainAddress:
    return ChainAddress.from_str(
        f"{to_hex(address)}@{ChainID.from_parts(chain.routingId, chain.vmId)}"
    )


class RepresentationConfigEntry(NamedTuple):
    """A token's representation config, as the Registry lists it."""

    token: ChainAddress
    """The configured token."""

    config: RegistryRepresentationConfig
    """The token's representation config; all zeros once removed."""


class TPlusContract:
    """
    An abstraction around a t+ contract, independent of the EVM backend.
    """

    NAME: ClassVar[str] = ""

    def __init__(
        self,
        default_deployer: Any | None = None,
        chain_id: "ChainID | int | None" = None,
        address: str | None = None,
        tplus_contracts_version: str | None = None,
        *,
        backend: "EVMBackend | None" = None,
        rpc_url: str | None = None,
        web3: Any | None = None,
    ) -> None:
        self._deployments: dict[str, Any] = {}
        self._default_deployer = default_deployer

        if isinstance(chain_id, int):
            chain_id = ChainID.evm(chain_id)

        self._chain_id = chain_id
        self._address = address
        self._tplus_contracts_version = tplus_contracts_version
        self._attempted_deploy_dev = False
        self._attempted_ce_adopt = False

        self._backend_arg = backend
        self._rpc_url = rpc_url
        self._web3 = web3
        self._resolved_backend: EVMBackend | None = None

        if address is not None and chain_id is not None:
            self._deployments[f"{chain_id}"] = self.backend.get_contract(self.NAME, address)

    @property
    def backend(self) -> "EVMBackend":
        if self._resolved_backend is None:
            self._resolved_backend = resolve_backend(
                self._backend_arg, rpc_url=self._rpc_url, web3=self._web3
            )

        return self._resolved_backend

    @property
    def tplus_contracts_project(self):
        """The Ape ``tplus-contracts`` project (Ape backend only)."""
        return load_tplus_contracts_project(version=self._tplus_contracts_version)

    @classmethod
    def at(cls, address: str, *, backend: "EVMBackend | None" = None) -> "TPlusContract":
        backend = backend or get_backend()
        return cls(address=address, chain_id=backend.chain_id, backend=backend)

    @property
    def chain_address(self) -> ChainAddress:
        return ChainAddress.from_str(f"{to_bytes32(self.address).hex()}@{self.chain_id}")

    @classmethod
    def deploy(cls, *args, sender: Any, **kwargs) -> "TPlusContract":
        tplus_contracts_version = kwargs.pop("tplus_contracts_version", None)
        backend = kwargs.pop("backend", None) or get_backend()

        handle = backend.deploy_contract(
            cls.NAME, *args, sender=sender, tplus_contracts_version=tplus_contracts_version
        )
        chain_id = backend.chain_id

        if tplus_contracts_version:
            kwargs["tplus_contracts_version"] = tplus_contracts_version

        return cls(
            default_deployer=sender,
            chain_id=chain_id,
            address=handle.address,
            backend=backend,
            **kwargs,
        )

    @classmethod
    def deploy_dev(cls, **kwargs):
        backend = kwargs.get("backend") or get_backend()
        owner = kwargs.get("sender") or backend.default_test_account()
        return cls.deploy(owner, sender=owner, backend=backend)

    @classmethod
    def _fetch_ce_address(cls) -> "ChainAddress | None":
        """Subclasses override to return the CE's stored address for this contract."""
        return None

    @classmethod
    def from_ce_address(cls, **kwargs) -> "TPlusContract":
        """Instantiate at the address the clearing engine reports for this contract.

        Raises ``ValueError`` if the CE is unreachable or has no address registered
        for this contract class. Extra ``**kwargs`` are forwarded to ``__init__``
        (e.g. ``default_deployer``, ``backend``, ``tplus_contracts_version``).
        """
        chain_addr = cls._fetch_ce_address()
        if chain_addr is None:
            raise ValueError(f"No clearing-engine address registered for {cls.__name__}.")

        kwargs.setdefault("address", chain_addr.evm_address)
        kwargs.setdefault("chain_id", chain_addr.chain_id)
        return cls(**kwargs)

    def _adopt_ce_deployment(self) -> "TPlusContract | None":
        """If the CE points at a live deployment for this contract on the
        currently-connected chain, adopt it instead of redeploying."""
        if self._attempted_ce_adopt:
            return None
        self._attempted_ce_adopt = True

        ce_addr = type(self)._fetch_ce_address()
        if ce_addr is None or ce_addr.chain_id != self.chain_id:
            return None

        evm = ce_addr.evm_address
        try:
            code = self.backend.get_code(evm)
        except Exception:
            return None
        if not code or code == b"" or code == "0x":
            return None

        instance = self.__class__(
            chain_id=self.chain_id,
            address=evm,
            tplus_contracts_version=self._tplus_contracts_version,
            backend=self.backend,
        )
        self._address = evm
        self._deployments[f"{self.chain_id}"] = instance
        return instance

    def deploy_dev_and_set_deployment(self) -> "TPlusContract":
        self._attempted_deploy_dev = True

        if (adopted := self._adopt_ce_deployment()) is not None:
            return adopted

        instance = self.deploy_dev(backend=self.backend)
        self._address = instance.address
        self._deployments[f"{instance.chain_id}"] = instance
        return instance

    def __repr__(self) -> str:
        return f"<{self.name}>"

    def __getattr__(self, attr_name: str):
        try:
            # First, try a regular attribute on the class
            return self.__getattribute__(attr_name)
        except AttributeError:
            if attr_name.startswith("_"):
                # Ignore internals, causes integration issues.
                raise

            # Try something defined on the contract.
            return getattr(self.contract, attr_name)

    @property
    def name(self) -> str:
        return self.__class__.NAME

    @cached_property
    def chain_id(self) -> ChainID:
        return self._chain_id or ChainID.evm(self.backend.chain_id)

    @property
    def address(self) -> str:
        if address := self._address:
            return address

        return self.get_address(chain_id=self.chain_id)

    @property
    def contract(self) -> "ContractHandle":
        """The contract handle on the currently connected chain."""
        try:
            return self.get_contract()
        except ContractNotExists:
            if self.is_local_network and not self._attempted_deploy_dev:
                # If simulating, deploy it now.
                return self.deploy_dev_and_set_deployment()

            raise  # This error.

    @property
    def is_local_network(self) -> bool:
        try:
            return self.backend.is_local_network
        except Exception:
            return False

    @property
    def default_deployer(self) -> Any:
        if deployer := self._default_deployer:
            return deployer

        if self._default_deployer is None and self.is_local_network:
            deployer = self.backend.default_test_account()
            self._default_deployer = deployer
            return deployer

        raise ValueError(f"Cannot deploy '{self.name}' - No default deployer configured.")

    @property
    def is_deployed(self) -> bool:
        return self.is_deployed_on(chain_id=self.chain_id)

    def is_deployed_on(self, chain_id: ChainID) -> bool:
        if chain_id in self._deployments:
            return True

        return self._get_address(chain_id=chain_id, deploy_on_dev=False) is not None

    def is_convertible(self, to_type: type) -> bool:
        return _ApeAddressType is not None and to_type is _ApeAddressType

    def convert_to(self, to_type: type) -> Any:
        if _ApeAddressType is None:
            raise TypeError(f"Cannot convert '{self.name}' (Ape not installed).")

        if to_type is _ApeAddressType:
            return self.address

        err_cls = _ApeConversionError if _ApeConversionError is not None else TypeError
        raise err_cls(f"Cannot convert '{self.name}' to '{to_type}'.")

    def set_chain(self, chain_id: ChainID) -> None:
        self._chain_id = chain_id

    def get_contract(self, chain_id: "ChainID | None" = None) -> "ContractHandle":
        """
        Load a contract handle for the given chain ID. Defaults to the currently
        connected chain.
        """
        chain_id = chain_id or self.chain_id
        if f"{chain_id}" in self._deployments:
            return self._deployments[f"{chain_id}"]

        address = self.get_address(chain_id=chain_id)
        handle = self.backend.get_contract(self.NAME, address)

        # Cache for next time.
        self._deployments[f"{chain_id}"] = handle
        return handle

    def get_address(self, chain_id: "ChainID | None" = None, deploy_on_dev: bool = True) -> str:
        if address := self._get_address(chain_id=chain_id, deploy_on_dev=deploy_on_dev):
            return address

        raise ContractNotExists(f"{self.name} not deployed on chain '{chain_id}'.")

    def _get_address(
        self, chain_id: "ChainID | None" = None, deploy_on_dev: bool = True
    ) -> str | None:
        if self._address and self._chain_id and chain_id == self._chain_id:
            return self._address

        chain_id = chain_id or self.chain_id
        if (hardcoded := TPLUS_DEPLOYMENTS.get(chain_id, {}).get(self.name)) is not None:
            return hardcoded

        # Ask the clearing engine — authoritative on any network.
        if (adopted := self._adopt_ce_deployment()) is not None:
            return adopted.address

        if deploy_on_dev and self.is_local_network and not self._attempted_deploy_dev:
            try:
                return self.deploy_dev_and_set_deployment().address
            except Exception:
                pass

        return None


class Registry(TPlusContract):
    NAME = "Registry"

    @classmethod
    def deploy_proxy(
        cls,
        *,
        sender: Any,
        risk_param_delay_secs: int = 0,
        upgrade_delay_secs: int = 0,
        backend: "EVMBackend | None" = None,
    ) -> "Registry":
        """Deploy a Registry behind an ERC1967 proxy, administered by `sender`."""
        backend = backend or get_backend()
        owner = backend.get_account(sender)
        implementation = backend.deploy_contract(
            cls.NAME, owner, risk_param_delay_secs, sender=owner
        )
        factory = ERC1967ProxyFactory.deploy(sender=owner, backend=backend)
        proxy = factory.deploy_proxy(
            implementation.address,
            encode_initialization(
                find_initialize_abi(cls.NAME),
                [owner.address, risk_param_delay_secs, upgrade_delay_secs],
            ),
            sender=owner,
        )
        return cls(
            default_deployer=owner, chain_id=backend.chain_id, address=proxy, backend=backend
        )

    @classmethod
    def deploy_dev(cls, **kwargs):
        backend = kwargs.get("backend") or get_backend()
        return cls.deploy_proxy(
            sender=kwargs.get("sender") or backend.default_test_account(),
            risk_param_delay_secs=kwargs.get("risk_param_delay_secs", 0),
            upgrade_delay_secs=kwargs.get("upgrade_delay_secs", 0),
            backend=backend,
        )

    @classmethod
    def _fetch_ce_address(cls) -> "ChainAddress | None":
        return _ce_fetch_chain_address("registry")

    def get_assets(
        self,
        chain_id: "ChainID | None" = None,
        start: int = 0,
        end: int = 65535,
    ) -> list:
        connected_chain = ChainID.evm(self.backend.chain_id)
        if chain_id is not None and connected_chain != chain_id:
            with self.backend.connect_to(chain_id):
                return self._get_assets(start, end)

        return self._get_assets(start, end)

    def get_asset_addresses(
        self, start_index: int | None = None, end_index: int | None = None
    ) -> list[ChainAddress]:
        return [r["chain_address"] for r in self.get_asset_records(start_index, end_index)]

    def get_asset_records(
        self, start_index: int | None = None, end_index: int | None = None
    ) -> list[dict]:
        start_index = 0 if start_index is None else start_index
        end_index = 65535 if end_index is None else end_index
        data = self.contract.getAssets(start_index, end_index)
        return [
            {
                "chain_address": decode_registry_chain_address(itm.assetAddress, itm.chainId),
                "max_deposits": itm.maxDeposits,
                "max_1hr_deposits": itm.max1hrDeposits,
                "min_weight": itm.minWeight,
            }
            for itm in data
        ]

    def _get_assets(self, start: int, end: int) -> list:
        res = []
        for chain_addr in self.get_asset_addresses(start, end):
            # The EVM backends only know about EVM contracts; skip non-EVM entries.
            if chain_addr.chain_id.routing_id != 0:
                continue

            address = chain_addr.evm_address
            res.append(self.backend.get_erc20(address))

        return res

    def set_asset(
        self,
        index: int,
        asset_address: "HexBytes32 | AddressType",
        chain_id: ChainID,
        max_deposit: int,
        max_1hr_deposits: int,
        min_weight: int,
        *,
        council: list,
        sender: Any,
        **tx_kwargs,
    ):
        data = self.build_asset_data(
            index, asset_address, chain_id, max_deposit, max_1hr_deposits, min_weight
        )
        return self.schedule_and_execute_if_due(
            "ASSET_DATA", [data], council=council, sender=sender, **tx_kwargs
        )

    @staticmethod
    def build_asset_data(
        index: int,
        asset_address: "HexBytes32 | AddressType",
        chain_id: ChainID,
        max_deposit: int,
        max_1hr_deposits: int,
        min_weight: int,
    ) -> AssetData:
        """The `Registry.AssetData` of an asset entry."""
        return AssetData(
            index=index,
            asset_address=to_registry_token(asset_address),
            chain_id=chain_id.to_registry_chain(),
            max_deposits=max_deposit,
            max_1hr_deposits=max_1hr_deposits,
            min_weight=min_weight,
        )

    def set_representation_config(
        self,
        chain_id: ChainID,
        token: "HexBytes32 | AddressType",
        config: RegistryRepresentationConfig,
        *,
        council: list,
        sender: Any,
        **tx_kwargs,
    ) -> OperationScheduled:
        """Configure the provider a registered token's representation rate is read from."""
        return self.schedule_and_execute_if_due(
            "REPRESENTATION_CONFIG",
            self.build_representation_config_values(chain_id, token, config),
            council=council,
            sender=sender,
            **tx_kwargs,
        )

    @staticmethod
    def build_representation_config_values(
        chain_id: ChainID, token: "HexBytes32 | AddressType", config: RegistryRepresentationConfig
    ) -> list:
        """The `REPRESENTATION_CONFIG` operation values of a token's config."""
        return [chain_id.to_registry_chain(), to_registry_token(token), config]

    def get_representation_configs(
        self, start: int = 0, end: int = REPRESENTATION_CONFIG_PAGE_LIMIT
    ) -> list[RepresentationConfigEntry]:
        """One entry per token ever configured; a removed token's config is all zeros."""
        return [
            RepresentationConfigEntry(
                token=decode_registry_chain_address(entry.token, entry.chain),
                config=RegistryRepresentationConfig.from_struct(entry.config),
            )
            for entry in self.contract.getRepresentationConfigs(start, end)
        ]

    def get_representation_config(
        self, chain_id: ChainID, token: "HexBytes32 | AddressType"
    ) -> RegistryRepresentationConfig:
        return RegistryRepresentationConfig.from_struct(
            self.contract.getRepresentationConfig(
                convert_to_abi_value(chain_id.to_registry_chain()), to_registry_token(token)
            )
        )

    def get_asset_index(self, chain_id: ChainID, token: "HexBytes32 | AddressType") -> int:
        return self.contract.getAssetIndex(
            convert_to_abi_value(chain_id.to_registry_chain()), to_registry_token(token)
        )

    def get_risk_parameters(
        self, start_index: int | None = None, end_index: int | None = None
    ) -> list["RiskParameters"]:
        start_index = 0 if start_index is None else start_index
        end_index = 100 if end_index is None else end_index
        result = self.contract.getRiskParameters(start_index, end_index)
        return [RiskParameters.model_validate(item.__dict__) for item in result]

    def validate_risk_parameters(self, params: "RiskParameters | dict") -> None:
        if not isinstance(params, dict):
            params = params.model_dump(mode="python", by_alias=True)

        self.contract.validateRiskParameters(params)

    def get_withdrawal_delay_parameters(self) -> "WithdrawalDelayParameters":
        from tplus.model.withdrawal import WithdrawalDelayParameters

        result = self.contract.getWithdrawalDelayParameters()
        return WithdrawalDelayParameters.model_validate(result.__dict__)

    def get_credential_manager(self) -> "AddressType":
        """The CredentialManager governing the risk council, or the zero address before one."""
        return self.contract.credentialManager()

    def initialize_risk_council(
        self,
        manager: "AddressType",
        universe_id: bytes,
        members: "list[AddressType]",
        threshold: int,
        *,
        sender: Any,
        **tx_kwargs,
    ) -> Any:
        return self.contract.initializeRiskCouncil(
            manager, universe_id, members, threshold, sender=sender, **tx_kwargs
        )

    def schedule_operation(
        self, name: str, values: list, *, council: list, sender: Any, **tx_kwargs
    ) -> OperationScheduled:
        """Schedule a risk council operation."""
        op_type, key, params = build_registry_operation(name, values)
        return schedule_operation(
            self.contract,
            op_type,
            key,
            params,
            signers=[to_operator_key(member) for member in council],
            sender=sender,
            backend=self.backend,
            **tx_kwargs,
        )

    def execute_operation(
        self, name: str, values: list, op_id: bytes, *, sender: Any, **tx_kwargs
    ) -> Any:
        """Execute operation `op_id`, scheduled for `values`, once its delay has passed."""
        op_type, _, params = build_registry_operation(name, values)
        return execute_operation(self.contract, op_id, op_type, params, sender=sender, **tx_kwargs)

    def schedule_and_execute_if_due(
        self, name: str, values: list, *, council: list, sender: Any, **tx_kwargs
    ) -> OperationScheduled:
        """Schedule a risk council operation, executing it when its delay has already passed."""
        _, key, _ = build_registry_operation(name, values)
        return self._schedule_and_execute_if_due(
            lambda: self.schedule_operation(
                name, values, council=council, sender=sender, **tx_kwargs
            ),
            lambda op_id: self.execute_operation(name, values, op_id, sender=sender, **tx_kwargs),
            key,
        )

    def _schedule_and_execute_if_due(
        self,
        schedule: Callable[[], OperationScheduled],
        execute: Callable[[bytes], Any],
        pending_key: bytes,
    ) -> OperationScheduled:
        schedule_event = schedule()
        if is_operation_due(schedule_event, self.backend):
            op_id = bytes(schedule_event.op_id)
            execute_unless_executed(
                lambda: execute(op_id),
                lambda: bytes(self.contract.pendingId(pending_key)) != op_id,
            )

        return schedule_event

    def change_delay_bounds(
        self,
        name: str,
        lower_secs: int,
        upper_secs: int,
        *,
        council: list,
        sender: Any,
        **tx_kwargs,
    ) -> OperationScheduled:
        """Schedule new delay bounds for a risk council op type, executing them when already due."""
        target_op_type = compute_op_type(name, REGISTRY_CONTRACT_NAME)
        return self._schedule_and_execute_if_due(
            lambda: self.schedule_delay_change(
                target_op_type, lower_secs, upper_secs, council=council, sender=sender, **tx_kwargs
            ),
            lambda op_id: self.contract.executeDelayChange(
                op_id, target_op_type, lower_secs, upper_secs, [], [], sender=sender, **tx_kwargs
            ),
            build_delay_change(target_op_type, lower_secs, upper_secs).key,
        )

    def schedule_delay_change(
        self,
        target_op_type: bytes,
        lower_secs: int,
        upper_secs: int,
        *,
        council: list,
        sender: Any,
        **tx_kwargs,
    ) -> OperationScheduled:
        delay_change = build_delay_change(target_op_type, lower_secs, upper_secs)
        approval = sign_schedule(
            self.contract,
            SET_DELAY_BOUNDS_OP_TYPE,
            delay_change.key,
            delay_change.params,
            signers=[to_operator_key(member) for member in council],
            backend=self.backend,
        )
        receipt = self.contract.scheduleDelayChange(
            target_op_type,
            lower_secs,
            upper_secs,
            approval.nonce,
            approval.deadline_secs,
            approval.signers,
            approval.signatures,
            sender=sender,
            **tx_kwargs,
        )
        return OperationScheduled.from_receipt(receipt, self.contract, self.backend)


class DepositVault(TPlusContract):
    NAME = "DepositVault"

    @classmethod
    def _fetch_ce_address(cls) -> "ChainAddress | None":
        return _ce_fetch_last_chain_address("vaults")

    @classmethod
    def latest_on_chain(cls, **kwargs) -> "DepositVault":
        """Instantiate at the most recently registered vault address per the CE.

        Raises ``ValueError`` if the CE is unreachable or has no registered vaults.
        Extra ``**kwargs`` forward to ``__init__``.
        """
        chain_addr = _ce_fetch_last_chain_address("vaults")
        if chain_addr is None:
            raise ValueError("No vaults registered on the clearing engine.")

        kwargs.setdefault("address", chain_addr.evm_address)
        kwargs.setdefault("chain_id", chain_addr.chain_id)
        return cls(**kwargs)

    def __getattr__(self, attr_name: str):
        if self._chain_id is None or attr_name in ("address",) or attr_name.startswith("_"):
            return super().__getattr__(attr_name)

        # If connected elsewhere, switch to the vault's chain first.
        try:
            connected_chain = self.backend.chain_id
        except Exception:
            return super().__getattr__(attr_name)

        if connected_chain != self._chain_id.vm_id:
            with self.backend.connect_to(self._chain_id):
                return super().__getattr__(attr_name)

        return super().__getattr__(attr_name)

    @classmethod
    def from_chain_address(cls, chain_address: ChainAddress, **kwargs) -> "DepositVault":
        return cls(chain_id=chain_address.chain_id, address=chain_address.evm_address, **kwargs)

    @property
    def domain_separator(self) -> HexBytes:
        return HexBytes(self.backend.get_storage(self.address, 3))

    @property
    def approved_settlers(self) -> list:
        return self.contract.getApprovedSettlers()

    def add_settler_executor(self, settler: UserPublicKey, executor: AddressType, **kwargs):
        return self.contract.addSettlerExecutor(settler, executor, **kwargs)

    def get_settlement_count(self, user: "UserPublicKey | User", account_index: int) -> int:
        if not isinstance(user, UserPublicKey):
            user = user.public_key

        return self.contract.settlementCounts(user, account_index)

    def get_deposit_count(self, user: "UserPublicKey | User") -> int:
        if not isinstance(user, UserPublicKey):
            user = user.public_key

        return self.contract.depositCounts(user)

    def get_withdrawal_count(self, user: "UserPublicKey | User") -> int:
        if not isinstance(user, UserPublicKey):
            user = user.public_key

        return self.contract.withdrawalCounts(user)

    def deposit(
        self,
        user: UserPublicKey,
        token: "str | AddressType | Any",
        amount: int,
        **tx_kwargs,
    ):
        try:
            return self.contract.deposit(user, token, amount, **tx_kwargs)
        except ContractLogicError as err:
            err_id = err.message
            if erc20_err_name := _decode_erc20_error(err_id):
                raise ContractLogicError(erc20_err_name) from err

            raise  # Error as-is.

    def withdraw(
        self,
        withdrawal: dict,
        user: "bytes | UserPublicKey",
        target: AddressType,
        valid_until: int,
        epoch_hash: "bytes | HexBytes",
        signatures: "list[bytes | HexBytes]",
        **tx_kwargs,
    ):
        return self.contract.withdraw(
            withdrawal,
            user,
            target,
            valid_until,
            epoch_hash,
            signatures,
            **tx_kwargs,
        )

    def execute_atomic_settlement(
        self,
        settlement: dict,
        settler: HexBytes,
        data: HexBytes,
        signature: HexBytes,
        **tx_kwargs,
    ):
        try:
            return self.contract.executeAtomicSettlement(
                settlement, settler, data, signature, **tx_kwargs
            )
        except Exception as err:
            err_id = getattr(err, "message", "")
            if erc20_err_name := _decode_erc20_error(getattr(err, "message", f"{err}")):
                raise ContractLogicError(erc20_err_name) from err

            elif err_id == "0x203d82d8":
                raise ContractLogicError("Signature expired") from err

            elif isinstance(err_id, str) and err_id.startswith("0x06427aeb"):
                raise ContractLogicError("Invalid nonce") from err

            elif err_id == "0x8baa579f":
                raise ContractLogicError("Invalid signature") from err

            elif err_id == "0xc32d1d76":
                raise ContractLogicError("Not executor") from err

            raise  # Error as-is

    @classmethod
    def deploy(cls, *args, sender: Any, **kwargs) -> "DepositVault":
        args = list(args)
        backend = kwargs.get("backend") or get_backend()
        sender_account = backend.get_account(sender)
        try:
            expected_address = sender_account.get_deployment_address()
        except Exception:
            # Some account types may not expose this; skip the check if so.
            expected_address = None

        instance = cast("DepositVault", super().deploy(*args, sender=sender, **kwargs))

        if expected_address is not None and instance.address != expected_address:
            # Shouldn't happen - but just in case, as this will cause hard to detect problems.
            raise ValueError("Invalid address in domain separator")

        return instance

    @classmethod
    def deploy_proxy(
        cls,
        owner: "AddressType",
        credential_manager: "AddressType",
        *,
        sender: Any,
        upgrade_delay_secs: int = 0,
        genesis: "tuple | None" = None,
        backend: "EVMBackend | None" = None,
    ) -> "DepositVault":
        """Deploy a DepositVault behind an ERC1967 proxy.

        A vault starts from a governance snapshot. ``genesis`` defaults to the one
        ``credential_manager`` has committed, which exists once attested keys reach its
        withdrawal quorum; before that the read reverts with ``GovernanceSnapshotUnavailable``.
        Pass ``genesis`` where ``credential_manager`` is a receiver rather than the manager.
        """
        backend = backend or get_backend()
        account = backend.get_account(sender)
        owner = backend.convert_address(owner)
        credential_manager = backend.convert_address(credential_manager)
        if genesis is None:
            manager = CredentialManager(
                address=credential_manager, chain_id=backend.chain_id, backend=backend
            )
            genesis = manager.get_governance_snapshot()

        implementation = backend.deploy_contract(
            cls.NAME, owner, credential_manager, genesis, sender=account
        )
        factory = ERC1967ProxyFactory.deploy(sender=account, backend=backend)
        proxy = factory.deploy_proxy(
            implementation.address,
            encode_initialization(
                find_initialize_abi(cls.NAME),
                [owner, credential_manager, upgrade_delay_secs, genesis],
            ),
            sender=account,
        )
        return cls(
            default_deployer=account, chain_id=backend.chain_id, address=proxy, backend=backend
        )

    @classmethod
    def deploy_dev(cls, sender: Any | None = None, **kwargs) -> "TPlusContract":
        """
        Deploy and set up a development vault.
        """
        backend = kwargs.get("backend") or get_backend()
        if not (credman := kwargs.get("credential_manager")):
            credman = credential_manager.address

        sender = sender or backend.default_test_account()

        # The genesis makes the owner the one key that approves settlements/withdrawals.
        # (we only do this in dev mode; irl the genesis is the manager's committed snapshot).
        genesis = build_dev_genesis(backend.get_account(sender).address)
        return cast(
            "DepositVault", cls.deploy(sender, credman, genesis, sender=sender, backend=backend)
        )

    def set_domain_separator(self, domain_separator: bytes, *, sender: Any):
        return self.contract.setDomainSeparator(domain_separator, sender=sender)

    def set_credential_manager(self, new_credential_manager: "AddressType", *, sender: Any) -> Any:
        return self.contract.setCredentialManager(new_credential_manager, sender=sender)


def _decode_erc20_error(err: Any) -> str | None:
    if err == "0x7939f424":
        # The sender likely didn't approve, or they don't have the tokens.
        return "TransferFromFailed()"

    elif err == "0x90b8ec18":
        # The sender likely doesn't have the tokens.
        return "TransferFailed()"

    return None


class ERC1967ProxyFactory(TPlusContract):
    """
    Deploys ERC1967 proxies, initialised in the deploying transaction.
    """

    NAME = "ERC1967ProxyFactory"

    def deploy_proxy(self, implementation: str, initialization_data: bytes, *, sender: Any) -> str:
        receipt = self.contract.deployProxy(implementation, initialization_data, sender=sender)
        return self.backend.get_event_args(receipt, self.contract, "ProxyDeployed")["proxy"]


class CredentialManager(TPlusContract):
    """
    Manages Vaults and contract secrets.
    """

    NAME = "CredentialManager"

    @classmethod
    def deploy_dev(cls, **kwargs):
        backend = kwargs.get("backend") or get_backend()
        owner = kwargs.get("sender") or backend.default_test_account()
        operator_public_keys = [
            to_operator_key(operator).public_key for operator in kwargs.get("operators") or [owner]
        ]
        security_council = kwargs.get("security_council") or [owner.address]
        return cls.deploy(
            sender=owner,
            backend=backend,
            universe_id=kwargs.get("universe_id") or DEV_UNIVERSE_ID,
            operator_public_keys=operator_public_keys,
            committee_threshold=kwargs.get("committee_threshold") or len(operator_public_keys),
            security_council=security_council,
            security_council_threshold=kwargs.get("security_council_threshold")
            or compute_majority_threshold(len(security_council)),
            automata_verifier=kwargs.get("automata_verifier") or ZERO_ADDRESS,
            registry=kwargs.get("registry") or registry.address,
            withdrawal_quorum=kwargs.get("withdrawal_quorum") or DEV_WITHDRAWAL_QUORUM,
        )

    @classmethod
    def deploy(
        cls,
        *,
        sender: Any,
        universe_id: bytes,
        operator_public_keys: list[bytes],
        committee_threshold: int,
        security_council: list[str],
        security_council_threshold: int,
        automata_verifier: str,
        registry: str,
        withdrawal_quorum: int,
        backend: "EVMBackend | None" = None,
    ) -> "CredentialManager":
        """Deploy the canonical manager behind a proxy, initialised with zero delay bounds."""
        backend = backend or get_backend()
        initialization_data = build_credential_manager_initialization(
            universe_id=universe_id,
            operator_public_keys=operator_public_keys,
            committee_threshold=committee_threshold,
            security_council=security_council,
            security_council_threshold=security_council_threshold,
            automata_verifier=automata_verifier,
            registry=registry,
            withdrawal_quorum=withdrawal_quorum,
        )
        implementation = backend.deploy_contract(cls.NAME, sender=sender)
        factory = ERC1967ProxyFactory.deploy(sender=sender, backend=backend)
        proxy = factory.deploy_proxy(implementation.address, initialization_data, sender=sender)
        return cls(
            default_deployer=sender, chain_id=backend.chain_id, address=proxy, backend=backend
        )

    @property
    def governance_nonce(self) -> int:
        return self.contract.governanceNonces().lastScheduleNonce

    def add_vault(
        self,
        address: ChainAddress,
        config: ChainConfig,
        *,
        operator_keys: "list[OperatorKey]",
        sender: Any,
        **tx_kwargs,
    ):
        chain_id = address.chain_id
        return self.apply_operation(
            "ADD_VAULT",
            [
                chain_id.routing_id,
                chain_id.vm_id,
                bytes.fromhex(address.address),
                tuple(config.abi_values),
            ],
            operator_keys=operator_keys,
            sender=sender,
            **tx_kwargs,
        )

    def apply_operation(
        self,
        name: str,
        values: list,
        *,
        operator_keys: "list[OperatorKey]",
        sender: Any,
        **tx_kwargs,
    ):
        """Schedule and execute a zero-delay op type with committee signatures."""
        return apply_operation(
            self.contract,
            name,
            values,
            operator_signers=operator_keys,
            sender=sender,
            backend=self.backend,
            **tx_kwargs,
        )

    def set_withdrawal_quorum(
        self, quorum: int, *, operator_keys: "list[OperatorKey]", sender: Any, **tx_kwargs
    ):
        return self.apply_operation(
            "SET_WITHDRAWAL_QUORUM",
            [quorum],
            operator_keys=operator_keys,
            sender=sender,
            **tx_kwargs,
        )

    def set_profile_registry(
        self,
        profile_registry: "AddressType",
        *,
        operator_keys: "list[OperatorKey]",
        sender: Any,
        **tx_kwargs,
    ):
        return self.apply_operation(
            "SET_PROFILE_REGISTRY",
            [profile_registry],
            operator_keys=operator_keys,
            sender=sender,
            **tx_kwargs,
        )

    def register_strategy(
        self,
        chain_id: ChainID,
        strategy: "AddressType",
        *,
        operator_keys: "list[OperatorKey]",
        sender: Any,
        **tx_kwargs,
    ):
        return self.apply_operation(
            "REGISTER_STRATEGY",
            [chain_id.routing_id, chain_id.vm_id, strategy],
            operator_keys=operator_keys,
            sender=sender,
            **tx_kwargs,
        )

    def register_intra_chain_strategy(
        self, chain_id: ChainID, *, operator_keys: "list[OperatorKey]", sender: Any, **tx_kwargs
    ) -> "AddressType":
        """Deploy an `IntraChainAdminUpdateStrategy` and register it for `chain_id`."""
        strategy = self.backend.deploy_contract("IntraChainAdminUpdateStrategy", sender=sender)
        self.register_strategy(
            chain_id, strategy.address, operator_keys=operator_keys, sender=sender, **tx_kwargs
        )
        return strategy.address

    def get_attested_key(self, operator: "AddressType") -> "AddressType":
        return to_checksum_address(bytes(self.contract.operatorToAttestedKey(operator))[-20:])

    def attest(
        self,
        raw_quote: bytes,
        operator: "OperatorKey",
        *,
        sender: Any,
        sequence: int | None = None,
        tcb_evaluation_number: int = DEV_TCB_EVALUATION_NUMBER,
        **tx_kwargs,
    ) -> bytes:
        """Submit `operator`'s attestation packet over `raw_quote`; returns the rotation's op ID."""
        if sequence is None:
            sequence = self.contract.lastAttestationSequence(operator.address) + 1

        _, signature = build_attestation_packet(
            bytes(self.contract.domainSeparator()), raw_quote, sequence, operator
        )
        receipt = self.contract.submitNodeAttestationOnChain(
            raw_quote, tcb_evaluation_number, sequence, signature, sender=sender, **tx_kwargs
        )
        return bytes(OperationScheduled.from_receipt(receipt, self.contract, self.backend).op_id)

    def execute_key_rotation(
        self,
        op_id: bytes,
        operator: "AddressType",
        key: "AddressType",
        *,
        sender: Any,
        **tx_kwargs,
    ):
        return self.contract.executeKeyRotation(
            op_id, operator, key, [], [], sender=sender, **tx_kwargs
        )

    def get_governance_snapshot(self) -> tuple:
        """The committed governance snapshot, as the tuple a vault takes for its genesis.

        Reverts with ``GovernanceSnapshotUnavailable`` before the first commit.
        """
        # Backends differ on whether a nested struct comes back named, so read by position:
        # (version, committeeThreshold, councilThreshold, withdrawalQuorum, members, council).
        snapshot, _state_hash = self.contract.getGovernanceSnapshot()
        version, committee_threshold, council_threshold, withdrawal_quorum, members, council = (
            snapshot
        )
        return (
            version,
            committee_threshold,
            council_threshold,
            withdrawal_quorum,
            [(member[0], member[1]) for member in members],
            list(council),
        )

    def sync_vault_governance_snapshot(self, chain_id: ChainID, *, sender: Any, **tx_kwargs):
        return self.contract.syncVaultGovernanceSnapshot(
            chain_id.routing_id, chain_id.vm_id, sender=sender, **tx_kwargs
        )

    def attest_signer(
        self,
        operator: "OperatorKey | Any",
        signer_key: "AddressType",
        *,
        sender: Any,
        **tx_kwargs,
    ) -> bool:
        """Attest `signer_key` for `operator` over a mock quote unless it holds; whether it did."""
        operator = to_operator_key(operator)
        if self.get_attested_key(operator.address) == to_checksum_address(signer_key):
            return False

        op_id = self.attest(
            build_mock_quote(signer_key, operator.address), operator, sender=sender, **tx_kwargs
        )
        self.execute_key_rotation(op_id, operator.address, signer_key, sender=sender, **tx_kwargs)
        return True

    def install_vault_signers(
        self,
        vault: "ChainAddress | DepositVault",
        operator: "OperatorKey | Any",
        signer_key: "AddressType",
        *,
        sender: Any,
        **tx_kwargs,
    ):
        """Attest `signer_key` for `operator` over a mock quote unless it holds, then sync `vault`."""
        if isinstance(vault, DepositVault):
            vault = vault.chain_address

        self.attest_signer(operator, signer_key, sender=sender, **tx_kwargs)
        return self.sync_vault_governance_snapshot(vault.chain_id, sender=sender, **tx_kwargs)

    def get_vaults(self) -> "list[DepositVault]":
        vault_records: list = []
        while True:
            start = len(vault_records)
            page = self.contract.getVaults(start, start + VAULT_PAGE_SIZE)
            vault_records.extend(page)
            if len(page) < VAULT_PAGE_SIZE:
                break

        return [
            DepositVault(
                address=to_hex(record.vaultAddress[:20]),
                chain_id=ChainID.from_parts(record.routingId, record.vmId),
                backend=self.backend,
            )
            for record in vault_records
        ]


class MeasurementProfile(NamedTuple):
    """Mirror of `MeasurementProfileRegistry.Profile`: one service kind's TDX measurements."""

    mrtd: bytes
    """The first 32 bytes of the expected MRTD; zero means no profile is in force."""

    rtmr0: bytes
    """The first 32 bytes of the expected RTMR0; zero means not checked."""

    rtmr1: bytes
    """The first 32 bytes of the expected RTMR1; zero means not checked."""

    rtmr2: bytes
    """The first 32 bytes of the expected RTMR2; zero means not checked."""

    rtmr3: bytes
    """The first 32 bytes of the expected RTMR3; zero means not checked."""


class MeasurementProfileRegistry(TPlusContract):
    """
    Approved TDX measurements per service kind, governed by a CredentialManager's committee.
    """

    NAME = "MeasurementProfileRegistry"
    CLEARING_ENGINE_KIND: ClassVar[int] = 0

    @classmethod
    def deploy(
        cls,
        *,
        sender: Any,
        credential_manager: "AddressType",
        universe_id: bytes,
        backend: "EVMBackend | None" = None,
    ) -> "MeasurementProfileRegistry":
        """Deploy behind a proxy, initialised with zero delay bounds."""
        backend = backend or get_backend()
        implementation = backend.deploy_contract(cls.NAME, sender=sender)
        zero_bounds = (0, 0)
        initialization_data = encode_initialization(
            find_initialize_abi(cls.NAME),
            [
                credential_manager,
                universe_id,
                [zero_bounds] * implementation.KIND_COUNT(),
                zero_bounds,
            ],
        )
        factory = ERC1967ProxyFactory.deploy(sender=sender, backend=backend)
        proxy = factory.deploy_proxy(implementation.address, initialization_data, sender=sender)
        return cls(
            default_deployer=sender, chain_id=backend.chain_id, address=proxy, backend=backend
        )

    def schedule_profile(
        self,
        kind: int,
        profile: MeasurementProfile,
        *,
        operator_keys: "list[OperatorKey]",
        sender: Any,
        **tx_kwargs,
    ) -> OperationScheduled:
        """Schedule `kind`'s measurements."""
        op_type = bytes(self.contract.profileOpType(kind))
        params = encode(
            *align_params(
                self.NAME, ["uint32", "struct MeasurementProfileRegistry.Profile"], [kind, profile]
            )
        )
        approval = sign_schedule(
            self.contract, op_type, op_type, params, signers=operator_keys, backend=self.backend
        )
        return self._submit_profile_schedule(kind, profile, approval, sender=sender, **tx_kwargs)

    def _submit_profile_schedule(
        self,
        kind: int,
        profile: MeasurementProfile,
        approval: ScheduleApproval,
        *,
        sender: Any,
        **tx_kwargs,
    ) -> OperationScheduled:
        receipt = self.contract.scheduleSetProfile(
            kind,
            profile,
            approval.nonce,
            approval.deadline_secs,
            approval.signers,
            approval.signatures,
            sender=sender,
            **tx_kwargs,
        )
        return OperationScheduled.from_receipt(receipt, self.contract, self.backend)

    def execute_profile(
        self,
        op_id: bytes,
        kind: int,
        profile: MeasurementProfile,
        *,
        sender: Any,
        **tx_kwargs,
    ):
        return self.contract.executeSetProfile(
            op_id, kind, profile, [], [], sender=sender, **tx_kwargs
        )


def build_credential_manager_initialization(
    *,
    universe_id: bytes,
    operator_public_keys: list[bytes],
    committee_threshold: int,
    security_council: list[str],
    security_council_threshold: int,
    automata_verifier: str,
    registry: str,
    withdrawal_quorum: int,
) -> bytes:
    """`initialize` calldata for a canonical manager with zero delay bounds on every op type."""
    initialize_abi = find_credential_manager_initialize_abi()
    params = (
        universe_id,
        [compute_operator_address(public_key) for public_key in operator_public_keys],
        list(operator_public_keys),
        committee_threshold,
        security_council,
        security_council_threshold,
        automata_verifier,
        registry,
        withdrawal_quorum,
        CANONICAL_MANAGER_ROLE,
        tuple((0, 0) for _ in range(count_credential_manager_op_types(initialize_abi))),
    )
    return encode_initialization(initialize_abi, [params])


def build_dev_genesis(signer: "AddressType") -> tuple:
    """A vault genesis for development: version 1, `signer` as the one member, key and council
    member, and every threshold at 1."""
    return (1, 1, 1, 1, [(signer, signer)], [signer])


def read_genesis(
    manager: str, *, rpc_url: str | None = None, backend: "EVMBackend | None" = None
) -> tuple:
    """A vault genesis: the governance snapshot the CredentialManager at ``manager`` has committed.

    For a vault whose credential manager is a receiver, which relays the snapshots of a manager
    on another chain. ``rpc_url`` is that chain's RPC; without it (or ``backend``) the manager
    is read on the connected chain.
    """
    if rpc_url:
        from tplus.evm.backends.web3 import Web3Backend

        backend = Web3Backend(rpc_url=rpc_url)

    backend = backend or get_backend()
    return CredentialManager(
        address=backend.convert_address(manager), chain_id=backend.chain_id, backend=backend
    ).get_governance_snapshot()


def encode_initialization(initialize_abi: dict[str, Any], args: list) -> bytes:
    return function_abi_to_4byte_selector(initialize_abi) + encode(
        get_abi_input_types(initialize_abi), args
    )


def find_initialize_abi(contract_name: str) -> dict[str, Any]:
    """A contract's `initialize` ABI entry from the bundled manifest."""
    for entry in get_abi(contract_name):
        if entry.get("type") == "function" and entry.get("name") == "initialize":
            return entry

    raise ValueError(f"the {contract_name} ABI has no initialize function")


def find_credential_manager_initialize_abi() -> dict[str, Any]:
    return find_initialize_abi("CredentialManager")


def count_credential_manager_op_types(initialize_abi: dict[str, Any] | None = None) -> int:
    """The number of op types, one delay-bounds pair each in `initialize`'s `bounds` struct."""
    entry = (
        initialize_abi if initialize_abi is not None else find_credential_manager_initialize_abi()
    )
    [params] = entry["inputs"]
    for component in params["components"]:
        if component["name"] == "bounds":
            return len(component["components"])

    raise ValueError("the CredentialManager initialize ABI has no bounds struct")


registry = Registry()
vault = DepositVault()
credential_manager = CredentialManager()


# Keep ``ape.convert(<tplus contract>, AddressType)`` working under Ape.
# (``ContractHandle`` is registered the same way from ``tplus.evm.backends.ape``.)
if _ApeConvertibleAPI is not None:
    _ApeConvertibleAPI.register(TPlusContract)
