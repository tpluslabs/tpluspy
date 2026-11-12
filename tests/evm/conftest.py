import importlib.util

import pytest

from tplus.evm import backends
from tplus.evm.contracts import DEV_UNIVERSE_ID, CredentialManager, MeasurementProfile, Registry
from tplus.evm.governance import OperatorKey, compute_domain_separator
from tplus.utils.universe import compute_universe_id

# Auto-detect the backend: use Ape if installed (it brings its own pytest plugin
# with a local provider), otherwise spin up the web3 backend on eth-tester.
_APE_AVAILABLE = importlib.util.find_spec("ape") is not None


def build_eth_tester_web3():
    web3 = pytest.importorskip("web3")
    # The web3 backend runs on eth-tester's in-process EVM, which only the [test] extra installs.
    pytest.importorskip("eth_tester")
    return web3.Web3(web3.EthereumTesterProvider())


@pytest.fixture(scope="session")
def evm_backend():
    """An EVM backend connected to a local dev chain."""
    if _APE_AVAILABLE:
        import ape

        from tplus.evm.backends.ape import ApeBackend

        with ape.networks.ethereum.local.use_provider("test"):
            backends.reset_backend()
            backend = ApeBackend()
            backends.set_backend(backend)
            try:
                yield backend
            finally:
                backends.reset_backend()
        return

    backends.reset_backend()
    backend = backends.use_web3(web3=build_eth_tester_web3(), is_local=True)
    try:
        yield backend
    finally:
        backends.reset_backend()


@pytest.fixture
def web3_instance():
    return build_eth_tester_web3()


@pytest.fixture
def web3_backend(web3_instance):
    backends.reset_backend()
    backend = backends.use_web3(web3=web3_instance, is_local=True)
    try:
        yield backend
    finally:
        backends.reset_backend()


@pytest.fixture
def manager_factory(web3_backend):
    def build_manager(operator_keys, committee_threshold, universe_id=DEV_UNIVERSE_ID):
        owner = web3_backend.default_test_account()
        registry = Registry.deploy_dev(sender=owner)
        manager = CredentialManager.deploy_dev(
            sender=owner,
            operators=operator_keys,
            committee_threshold=committee_threshold,
            registry=registry.address,
            universe_id=universe_id,
        )
        return owner, registry, manager

    return build_manager


@pytest.fixture
def measurement_profile():
    return MeasurementProfile(*(bytes([register]) * 32 for register in range(1, 6)))


@pytest.fixture
def test_accounts(evm_backend):
    """A list of funded test accounts on the active backend (``.address`` per item)."""
    if evm_backend.name == "ape":
        from ape.utils.basemodel import ManagerAccessMixin

        return list(ManagerAccessMixin.account_manager.test_accounts)

    return [evm_backend.get_account(addr) for addr in evm_backend.w3.eth.accounts]


@pytest.fixture
def signer(test_accounts):
    return test_accounts[0]


# The attestation packet fixtures below match lib/test-utils `attestation_vector`.
@pytest.fixture(scope="session")
def attestation_universe_id() -> bytes:
    return bytes(compute_universe_id("tplus-dev-example"))


@pytest.fixture(scope="session")
def domain_separator(attestation_universe_id: bytes) -> bytes:
    return compute_domain_separator(attestation_universe_id)


@pytest.fixture(scope="session")
def ape_test_accounts():
    ape = pytest.importorskip("ape")
    return ape.accounts.test_accounts


@pytest.fixture(scope="session")
def operator_key(ape_test_accounts) -> OperatorKey:
    return OperatorKey(ape_test_accounts[1].private_key)


@pytest.fixture(scope="session")
def attestation_quote(ape_test_accounts) -> bytes:
    """The signer's address, then the operator's."""
    signer, operator = ape_test_accounts[2], ape_test_accounts[1]
    return bytes.fromhex(signer.address[2:]) + bytes.fromhex(operator.address[2:])


@pytest.fixture(scope="session")
def attestation_sequence() -> int:
    return 1_730_000_000


@pytest.fixture(scope="session")
def expected_packet_digest() -> bytes:
    return bytes.fromhex("e1ad2fd28ae151c1a7c4fc8e179aa8274e566a3addb2d7790c4a23bc85e52b3c")


@pytest.fixture(scope="session")
def expected_packet_signature() -> bytes:
    return bytes.fromhex(
        "e1b55929f7b7c7f3cdfc5272f2f1c91f24fc9f95554534fa61feb3c27fca3dae"
        "4713eba7c372a28454a952b843ee9c8e5fe0d965f1c2056d24941d11f9c27ae31c"
    )


@pytest.fixture
def deploy_governed_registry(operator_account):
    def deploy(**registry_kwargs):
        registry = Registry.deploy_dev(sender=operator_account, **registry_kwargs)
        credential_manager = CredentialManager.deploy_dev(
            sender=operator_account, registry=registry.address
        )
        registry.initialize_risk_council(
            credential_manager.address,
            DEV_UNIVERSE_ID,
            [operator_account.address],
            1,
            sender=operator_account,
        )
        return registry, credential_manager, [OperatorKey(operator_account.local)]

    return deploy
