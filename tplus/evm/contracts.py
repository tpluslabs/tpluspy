import os
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

import yaml
from ape.api.accounts import AccountAPI
from ape.api.convert import ConvertibleAPI
from ape.exceptions import ContractLogicError, ContractNotFoundError, ConversionError, ProjectError
from ape.managers.project import Project
from ape.types.address import AddressType
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.misc import ZERO_ADDRESS
from eth_pydantic_types.hex.bytes import HexBytes

from tplus.evm.abi import get_erc20_type
from tplus.evm.constants import LATEST_ARB_DEPOSIT_VAULT, REGISTRY_ADDRESS
from tplus.evm.exceptions import ContractNotExists
from tplus.logger import get_logger
from tplus.model.asset_identifier import ChainAddress
from tplus.model.config import ChainConfig
from tplus.model.risk_parameters import RiskParameters
from tplus.model.types import ChainID, UserPublicKey
from tplus.utils.bytes32 import to_bytes32
from tplus.utils.hex import to_hex

if TYPE_CHECKING:
    from ape.api.transactions import ReceiptAPI
    from ape.contracts.base import ContractContainer, ContractInstance
    from ape.managers.project import LocalProject
    from eth_pydantic_types.hex.bytes import HexBytes32

    from tplus.model.withdrawal import WithdrawalDelayParameters
    from tplus.utils.user import User

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

    def __getitem__(self, chain_id: int | ChainID) -> "ContractInstance":
        if not isinstance(chain_id, int):
            chain_id = chain_id.vm_id

        return self.deployments[chain_id]

    def get(self, chain_id: int | ChainID, default=None):
        if not isinstance(chain_id, int):
            chain_id = chain_id.vm_id

        return self.deployments.get(chain_id, default)


TPLUS_DEPLOYMENTS = TplusDeployments()


# ---------------------------------------------------------------------------
# Dev-network shortcut: before auto-redeploying, check whether the clearing
# engine already points at a live contract on this chain.
# ---------------------------------------------------------------------------

_DEFAULT_CE_URL = "http://127.0.0.1:3032"
_CE_TIMEOUT = 2.0


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


def load_tplus_contracts_project(version: str | None = None) -> "LocalProject":
    """
    Loads the Ape project containing the Solidity contracts for tplus.
    If you are in the tplus-contracts repo, it detects that and loads that way.
    Else, it checks all Ape installed dependencies. If it is not installed, it will fail.
    Install the tplus-contracts project by running ``ape pm install tpluslabs/tplus-contracts``.
    """
    if path := os.environ.get("TPLUS_CONTRACTS_PATH"):
        return Project(path)

    elif ManagerAccessMixin.local_project.name == "tplus-contracts":
        # Working from the t+ contracts repo
        return ManagerAccessMixin.local_project

    # Load the project from dependencies.
    try:
        project = _load_tplus_contracts_from_dependencies(version=version)
    except Exception:
        if version:
            # If specifying a version, this has to have worked or else it is a mistake.
            raise

        # Use manifest that comes with tpluspy.
        project = _load_tplus_contracts_from_manifest()

    try:
        project.load_contracts()  # Ensure is compiled.
    except Exception:
        if version:
            # If specifying a version, this has to have worked or else it is a mistake.
            raise

        # Compiling failed for some reason. Just use the manifest, which is already compiled.
        project = _load_tplus_contracts_from_manifest()

    return project


def _load_tplus_contracts_from_dependencies(version: str | None = None) -> dict:
    available_versions = ManagerAccessMixin.local_project.dependencies["tplus-contracts"]
    if version:
        return available_versions[version]

    # Select first one.
    if not (version_key := next(iter(available_versions), None)):
        raise ProjectError("Please install the t+ contracts project")

    return available_versions[version_key]


def _load_tplus_contracts_from_manifest() -> Project:
    # Use manifest that comes with tpluspy.
    manifest_path = Path(__file__).parent / "manifests" / "tplus-contracts.json"
    return Project.from_manifest(manifest_path)


def load_tplus_contract_container(name: str, version: str | None = None) -> "ContractContainer":
    project = load_tplus_contracts_project(version=version)
    contract = project.contracts.get(name)
    if contract is None:
        raise ValueError(f"Missing contract '{name}' from tplus contracts project.")

    return contract


def get_dev_default_owner() -> "AccountAPI":
    return ManagerAccessMixin.account_manager.test_accounts[0]


class TPlusMixin(ManagerAccessMixin):
    """
    A mixin for access to relevant t+ constructs.
    """

    @property
    def tplus_contracts_project(self) -> "Project":
        """
        The t+ contacts project. This will fail if Ape is not able to
        download and cache the contracts project from GitHub. See pyproject.toml
        Ape config for current specification.
        """
        return load_tplus_contracts_project()


class TPlusContract(TPlusMixin, ConvertibleAPI):
    """
    An abstraction around a t+ contract.
    """

    NAME: ClassVar[str] = ""

    def __init__(
        self,
        default_deployer: "AccountAPI | None" = None,
        chain_id: ChainID | None = None,
        address: str | None = None,
        tplus_contracts_version: str | None = None,
    ) -> None:
        self._deployments: dict[str, ContractInstance] = {}
        self._default_deployer = default_deployer

        if isinstance(chain_id, int):
            chain_id = ChainID.evm(chain_id)

        self._chain_id = chain_id
        self._address = address
        self._tplus_contracts_version = tplus_contracts_version
        self._attempted_deploy_dev = False
        self._attempted_ce_adopt = False

        if address is not None and chain_id is not None:
            self._deployments[f"{chain_id}"] = self._contract_container.at(
                address, detect_proxy=False, fetch_from_explorer=False
            )

    @classmethod
    def at(cls, address: str) -> "TPlusContract":
        return cls(address=address, chain_id=cls.chain_manager.chain_id)

    @property
    def chain_address(self) -> ChainAddress:
        return ChainAddress.from_str(f"{to_bytes32(self.address).hex()}@{self.chain_id}")

    @classmethod
    def deploy(cls, *args, sender: "AccountAPI", **kwargs) -> "TPlusContract":
        tplus_contracts_version = kwargs.pop("tplus_contracts_version", None)
        contract_container = load_tplus_contract_container(
            cls.NAME, version=tplus_contracts_version
        )
        instance = sender.deploy(contract_container, *args, **kwargs)
        chain_id = cls.chain_manager.chain_id

        if version := tplus_contracts_version:
            kwargs["tplus_contracts_version"] = version

        return cls(default_deployer=sender, chain_id=chain_id, address=instance.address, **kwargs)

    @classmethod
    def deploy_dev(cls, **kwargs):
        owner = kwargs.get("sender") or get_dev_default_owner()
        return cls.deploy(owner, sender=owner)

    @classmethod
    def _fetch_ce_address(cls) -> "ChainAddress | None":
        """Subclasses override to return the CE's stored address for this contract."""
        return None

    @classmethod
    def from_ce_address(cls, **kwargs) -> "TPlusContract":
        """Instantiate at the address the clearing engine reports for this contract.

        Raises ``ValueError`` if the CE is unreachable or has no address registered
        for this contract class. Extra ``**kwargs`` are forwarded to ``__init__``
        (e.g. ``default_deployer``, ``tplus_contracts_version``).
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
            code = self.chain_manager.provider.get_code(evm)
        except Exception:
            return None
        if not code or code == b"" or code == "0x":
            return None

        instance = self.__class__(
            chain_id=self.chain_id,
            address=evm,
            tplus_contracts_version=self._tplus_contracts_version,
        )
        self._address = evm
        self._deployments[f"{self.chain_id}"] = instance
        return instance

    def deploy_dev_and_set_deployment(self) -> "TPlusContract":
        self._attempted_deploy_dev = True

        if (adopted := self._adopt_ce_deployment()) is not None:
            return adopted

        instance = self.deploy_dev()
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
        return self._chain_id or ChainID.evm(self.chain_manager.chain_id)

    @property
    def address(self) -> str:
        if address := self._address:
            return address

        return self.get_address(chain_id=self.chain_id)

    @property
    def tplus_contracts_project(self) -> "Project":
        # Overridden.
        return load_tplus_contracts_project(version=self._tplus_contracts_version)

    @property
    def _contract_container(self) -> "ContractContainer":
        return self.tplus_contracts_project.contracts.get(self.name)

    @property
    def contract(self) -> "ContractInstance":
        """
        The contract instance at the currently connected chain.
        """
        try:
            return self.get_contract()
        except ContractNotExists:
            if self.is_local_network and not self._attempted_deploy_dev:
                # If simulating, deploy it now.
                return self.deploy_dev_and_set_deployment()

            raise  # This error.

    @property
    def is_local_network(self) -> bool:
        return self.chain_manager.provider.network.is_local

    @property
    def default_deployer(self) -> "AccountAPI":
        if deployer := self._default_deployer:
            return deployer

        elif self._default_deployer is None and self.network_manager.provider.network.is_local:
            deployer = self.account_manager.test_accounts[0]
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
        return to_type is AddressType

    def convert_to(self, to_type: type) -> Any:
        if to_type is AddressType:
            return self.address

        raise ConversionError(f"Cannot convert '{self.name}' to '{to_type}'.")

    def set_chain(self, chain_id: ChainID) -> None:
        self._chain_id = chain_id

    def get_contract(self, chain_id: ChainID | None = None) -> "ContractInstance":
        """
        Load a contact instance for the given chain ID. Defaults to currently
        connected chain.

        Args:
            chain_id (ChainID | None): The chain ID. Defaults to currently connected
              chain.

        Returns:
            ContractInstance
        """
        chain_id = chain_id or self.chain_id
        if chain_id in self._deployments:
            # Get previously cached instance.
            return self._deployments[chain_id]

        address = self.get_address(chain_id=chain_id)
        contract_container = self._contract_container.at(
            address, detect_proxy=False, fetch_from_explorer=False
        )

        # Cache for next time.
        self._deployments[chain_id] = contract_container

        return contract_container

    def get_address(self, chain_id: ChainID | None = None, deploy_on_dev: bool = True) -> str:
        if address := self._get_address(chain_id=chain_id, deploy_on_dev=deploy_on_dev):
            return address

        raise ContractNotExists(f"{self.name} not deployed on chain '{chain_id}'.")

    def _get_address(
        self, chain_id: ChainID | None = None, deploy_on_dev: bool = True
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
    def deploy_dev(cls, **kwargs):
        owner = kwargs.get("sender") or get_dev_default_owner()
        risk_param_delay = kwargs.get("risk_param_delay_seconds", 0)
        return cls.deploy(owner, risk_param_delay, sender=owner)

    @classmethod
    def _fetch_ce_address(cls) -> "ChainAddress | None":
        return _ce_fetch_chain_address("registry")

    def get_assets(
        self,
        chain_id: ChainID | None = None,
        start: int = 0,
        end: int = 65535,
    ) -> list["ContractInstance"]:
        connected_chain = ChainID.evm(self.chain_manager.chain_id)
        if connected_chain != chain_id and chain_id == ChainID.evm(11155111):
            with self.network_manager.ethereum.sepolia.use_default_provider():
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
                "chain_address": ChainAddress.from_str(
                    f"{to_hex(itm.assetAddress)}@"
                    f"{ChainID.from_parts(itm.chainId.routingId, itm.chainId.vmId)}"
                ),
                "max_deposits": itm.maxDeposits,
                "max_1hr_deposits": itm.max1hrDeposits,
                "min_weight": itm.minWeight,
            }
            for itm in data
        ]

    def _get_assets(self, start: int, end: int) -> list["ContractInstance"]:
        res = []
        for chain_addr in self.get_asset_addresses(start, end):
            # Ape only knows about EVM contracts; skip non-EVM entries.
            if chain_addr.chain_id.routing_id != 0:
                continue

            address = chain_addr.evm_address
            try:
                contract = self.chain_manager.contracts.instance_at(address)
            except ContractNotFoundError:
                contract_type = get_erc20_type()
                contract = self.chain_manager.contracts.instance_at(
                    address, contract_type=contract_type
                )

            res.append(contract)

        return res

    def set_asset(
        self,
        index: int,
        asset_address: "HexBytes32 | AddressType",
        chain_id: ChainID,
        max_deposit: int,
        max_1hr_deposits: int,
        min_weight: int,
        sender=None,
    ) -> None:
        if isinstance(asset_address, str) and len(asset_address) <= 42:
            # Given EVM style address. Store as right-padded address.
            asset_address = to_bytes32(asset_address, pad="r")

        data = {
            "index": index,
            "assetAddress": asset_address,
            "chainId": {"routingId": chain_id.routing_id, "vmId": chain_id.vm_id},
            "maxDeposits": max_deposit,
            "max1hrDeposits": max_1hr_deposits,
            "minWeight": min_weight,
        }
        return self.contract.setAssetData(data, sender=sender)

    def get_risk_parameters(
        self, start_index: int | None = None, end_index: int | None = None
    ) -> list[RiskParameters]:
        start_index = 0 if start_index is None else start_index
        end_index = 100 if end_index is None else end_index
        result = self.contract.getRiskParameters(start_index, end_index)
        return [RiskParameters.model_validate(item.__dict__) for item in result]

    def set_pending_risk_parameters(
        self, index: int, params: "RiskParameters | dict", **kwargs
    ) -> "ReceiptAPI":
        if not isinstance(params, dict):
            params = params.model_dump(mode="python", by_alias=True)

        return self.contract.setPendingRiskParameters(index, params, **kwargs)

    def apply_pending_risk_parameters(self, index: int, **kwargs) -> "ReceiptAPI":
        return self.contract.applyPendingRiskParameters(index, **kwargs)

    def validate_risk_parameters(self, params: "RiskParameters | dict") -> None:
        if not isinstance(params, dict):
            params = params.model_dump(mode="python", by_alias=True)

        self.contract.validateRiskParameters(params)

    def set_pending_withdrawal_delay_parameters(
        self, params: "WithdrawalDelayParameters | dict", **kwargs
    ) -> "ReceiptAPI":
        if not isinstance(params, dict):
            params = params.model_dump(mode="python", by_alias=True)

        return self.contract.setPendingWithdrawalDelayParameters(params, **kwargs)

    def apply_pending_withdrawal_delay_parameters(self, **kwargs) -> "ReceiptAPI":
        return self.contract.applyPendingWithdrawalDelayParameters(**kwargs)

    def get_withdrawal_delay_parameters(self) -> "WithdrawalDelayParameters":
        from tplus.model.withdrawal import WithdrawalDelayParameters

        result = self.contract.getWithdrawalDelayParameters()
        return WithdrawalDelayParameters.model_validate(result.__dict__)

    def set_risk_manager_multisig(
        self, multisig: "AddressType", *, sender: AccountAPI
    ) -> "ReceiptAPI":
        return self.contract.setRiskManagerMultisig(multisig, sender=sender)


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

        # Verify chain first. Read chain_id straight off the live provider —
        # chain_manager.chain_id caches by network.name, which collides between
        # ape-test (local:1337) and ape-foundry (local:31337) and can return a
        # stale value from a previous activation.
        active_provider = self.network_manager.active_provider
        connected_chain = active_provider.chain_id if active_provider else None
        if connected_chain != self._chain_id.vm_id:
            # Try to connect.
            if choice := CHAIN_MAP.get(connected_chain):
                with self.network_manager.parse_network_choice(choice):
                    # Run on this network.
                    return super().__getattribute__(attr_name)

            raise AttributeError(
                f"Chain mismatch while accessing '{attr_name}' on {self.name} "
                f"{self._address or '<unset>'}: "
                f"vault's chain_id={self._chain_id.vm_id}, "
                f"currently-connected chain_id={connected_chain} "
                f"(active provider: {active_provider!r}). "
                f"Run inside `with ape.networks.<ecosystem>.<network>.use_provider(...)`."
            )

        return super().__getattr__(attr_name)

    @classmethod
    def from_chain_address(cls, chain_address: ChainAddress) -> "DepositVault":
        return cls(chain_id=chain_address.chain_id, address=chain_address.evm_address)

    @property
    def domain_separator(self) -> HexBytes:
        return HexBytes(self.chain_manager.provider.get_storage(self.address, 2))

    @property
    def approved_settlers(self) -> list["AddressType"]:
        return self.contract.getApprovedSettlers()

    def add_settler_executor(
        self, settler: UserPublicKey, executor: AddressType, **kwargs
    ) -> "ReceiptAPI":
        return self.addSettlerExecutor(settler, executor, **kwargs)

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
        token: "str | AddressType | ContractInstance",
        amount: int,
        **tx_kwargs,
    ) -> "ReceiptAPI":
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
        target: "AddressType",
        valid_until: int,
        epoch_hash: "bytes | HexBytes",
        signatures: "list[bytes | HexBytes]",
        **tx_kwargs,
    ) -> "ReceiptAPI":
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
    ) -> "ReceiptAPI":
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

            elif err_id.startswith("0x06427aeb"):
                raise ContractLogicError("Invalid nonce") from err

            elif err_id == "0x8baa579f":
                raise ContractLogicError("Invalid signature") from err

            elif err_id == "0xc32d1d76":
                raise ContractLogicError("Not executor") from err

            raise  # Error as-is

    @classmethod
    def deploy(cls, *args, sender: "AccountAPI", **kwargs) -> "DepositVault":
        args = list(args)
        address = sender.get_deployment_address()
        instance = super().deploy(*args, sender=sender, **kwargs)

        if instance.address != address:
            # Shouldn't happen - but just in case, as this will cause hard to detect problems.
            raise ValueError("Invalid address in domain separator")

        return instance

    @classmethod
    def deploy_dev(cls, sender: "AccountAPI | None" = None, **kwargs) -> TPlusContract:
        """
        Deploy and set up a development vault.
        """
        if not (credman := kwargs.get("credential_manager")):
            credman = credential_manager.address

        sender = sender or cls.account_manager.test_accounts[0]
        contract = cast(DepositVault, cls.deploy(sender, credman, sender=sender))

        # Set the owner as an admin who can approve settlements/withdrawals.
        # (we only do this in dev mode; irl the roles are different).
        credman_account = cls.account_manager[credman]
        credman_account.balance += int(1e18)
        contract.set_administrators([sender], credman_account)

        return contract

    def set_administrators(
        self,
        administrators: list["AddressType"],
        vault_owner: "AccountAPI",
        withdrawal_quorum: int | None = None,
    ) -> "ReceiptAPI":
        if withdrawal_quorum is None:
            withdrawal_quorum = len(administrators)

        return self.contract.setAdministrators(
            administrators, withdrawal_quorum, sender=vault_owner
        )

    def set_domain_separator(
        self, domain_separator: bytes, *, sender: "AccountAPI"
    ) -> "ReceiptAPI":
        return self.contract.setDomainSeparator(domain_separator, sender=sender)

    def set_credential_manager(
        self, new_credential_manager: "AddressType", *, sender: AccountAPI
    ) -> "ReceiptAPI":
        return self.contract.setCredentialManager(new_credential_manager, sender=sender)


def _decode_erc20_error(err: str) -> str | None:
    if err == "0x7939f424":
        # The sender likely didn't approve, or they don't have the tokens.
        return "TransferFromFailed()"

    elif err == "0x90b8ec18":
        # The sender likely doesn't have the tokens.
        return "TransferFailed()"

    return None


class CredentialManager(TPlusContract):
    """
    Manages Vaults and contract secrets.
    """

    NAME = "CredentialManager"

    @classmethod
    def deploy_dev(cls, **kwargs) -> "ReceiptAPI":
        owner = kwargs.get("sender") or get_dev_default_owner()
        operators = kwargs.get("operators", [owner.address])
        threshold = kwargs.get("quorum_threshold") or len(operators)

        if not (registry_address := kwargs.get("registry")):
            registry_address = registry.address

        measurements = kwargs.get("measurements") or []
        automata_verifier = kwargs.get("automata_verifier") or ZERO_ADDRESS

        return cls.deploy(
            operators,
            threshold,
            owner,
            registry_address,
            measurements,
            automata_verifier,
            sender=owner,
        )

    @property
    def governance_nonce(self) -> int:
        return self.contract.governanceNonce()

    def add_vault(
        self,
        address: ChainAddress,
        config: ChainConfig,
        signers: list[AddressType],
        signatures: list[bytes],
        **kwargs,
    ):
        chain_id = address.chain_id
        return self.contract.addVault(
            chain_id.routing_id,
            chain_id.vm_id,
            address.address,
            config,
            signers,
            signatures,
            **kwargs,
        )

    def get_vaults(self) -> list[DepositVault]:
        return [
            DepositVault(
                address=to_hex(r.vaultAddress[:20]),
                chain_id=ChainID.from_parts(r.routingId, r.vmId),
            )
            for r in self.contract.getVaults(0, 1000)
        ]


registry = Registry()
vault = DepositVault()
credential_manager = CredentialManager()
