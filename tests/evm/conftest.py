import importlib.util

import pytest

# Auto-detect the backend: use Ape if installed (it brings its own pytest plugin
# with a local provider), otherwise spin up the web3 backend on eth-tester.
_APE_AVAILABLE = importlib.util.find_spec("ape") is not None


@pytest.fixture(scope="session")
def evm_backend():
    """An EVM backend connected to a local dev chain."""
    from tplus.evm import backends

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

    web3 = pytest.importorskip("web3")
    pytest.importorskip("eth_tester")
    w3 = web3.Web3(web3.EthereumTesterProvider())
    backends.reset_backend()
    backend = backends.use_web3(web3=w3, is_local=True)
    try:
        yield backend
    finally:
        backends.reset_backend()


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
