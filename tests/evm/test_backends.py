import pytest

# Skip the whole module if the [evm] extra (web3.py + eth-account) or the
# in-process EVM backend (``eth-tester`` from the [test] extra) isn't installed.
web3_module = pytest.importorskip("web3")
eth_account = pytest.importorskip("eth_account")
web3_exceptions = pytest.importorskip("web3.exceptions")
pytest.importorskip("eth_tester")
from eth_account.messages import encode_defunct  # noqa: E402

from tplus.evm import _manifest, backends  # noqa: E402
from tplus.evm import abi as abi_helpers  # noqa: E402
from tplus.evm.backends import resolve_backend  # noqa: E402
from tplus.evm.backends.web3 import Web3Backend, _encode_args, _translate_web3_error  # noqa: E402
from tplus.evm.contracts import (  # noqa: E402
    CredentialManager,
    DepositVault,
    Registry,
    _decode_erc20_error,
)
from tplus.evm.exceptions import ContractLogicError  # noqa: E402


def test_manifest_has_core_contracts():
    types = _manifest.load_manifest()["contractTypes"]
    for name in ("Registry", "DepositVault", "CredentialManager"):
        assert name in types
        assert _manifest.get_abi(name)
        assert _manifest.get_deployment_bytecode(name)


def test_get_abi_unknown_contract():
    with pytest.raises(KeyError, match="not found in the bundled tplus-contracts manifest"):
        _manifest.get_abi("NopeNotAContract")


def test_erc20_abi_helpers():
    erc20 = abi_helpers.get_erc20_abi()
    names = {e.get("name") for e in erc20 if e.get("type") == "function"}
    assert {"balanceOf", "transfer", "approve", "allowance", "decimals"} <= names

    mock_names = {
        e.get("name") for e in abi_helpers.get_mock_erc20_abi() if e.get("type") == "function"
    }
    assert "mint" in mock_names


@pytest.fixture
def web3_instance():
    return web3_module.Web3(web3_module.EthereumTesterProvider())


@pytest.fixture
def web3_backend(web3_instance):
    backends.reset_backend()
    backend = backends.use_web3(web3=web3_instance, is_local=True)
    try:
        yield backend
    finally:
        backends.reset_backend()


def test_use_web3_is_active(web3_backend):
    assert backends.get_backend() is web3_backend
    assert web3_backend.name == "web3"
    assert web3_backend.is_local_network
    assert web3_backend.chain_id == web3_backend.w3.eth.chain_id


def test_pending_timestamp_is_positive(web3_backend):
    assert web3_backend.pending_timestamp > 0


def test_resolve_backend_prefers_explicit(web3_backend):
    assert resolve_backend(web3_backend) is web3_backend
    assert resolve_backend() is web3_backend  # falls back to the active one


def test_resolve_backend_builds_web3_from_rpc_url(web3_backend):
    built = resolve_backend(rpc_url="http://127.0.0.1:8545")
    assert isinstance(built, Web3Backend)
    assert built is not web3_backend


def test_per_object_rpc_url_override(web3_backend):
    registry = Registry(rpc_url="http://127.0.0.1:8545")
    assert isinstance(registry.backend, Web3Backend)
    assert registry.backend is not web3_backend


def test_connect_to_same_chain_yields(web3_backend):
    with web3_backend.connect_to(web3_backend.chain_id) as backend:
        assert backend is web3_backend


def test_connect_to_mismatched_chain_raises(web3_backend):
    with pytest.raises(RuntimeError, match="connected to chain"):
        with web3_backend.connect_to(424242):
            pass


def test_convert_address(web3_backend):
    addr = web3_backend.w3.eth.accounts[0]
    assert web3_backend.convert_address(addr) == addr
    assert web3_backend.convert_address(bytes.fromhex(addr[2:])) == addr
    assert web3_backend.convert_address(web3_backend.default_test_account()) == addr


def test_get_account_from_private_key(web3_backend):
    key_account = eth_account.Account.create()

    resolved = web3_backend.get_account(key_account.key.hex())
    assert resolved.address == key_account.address
    assert resolved.can_sign

    # Raw 32-byte key bytes work too.
    from_bytes = web3_backend.get_account(key_account.key)
    assert from_bytes.address == key_account.address and from_bytes.can_sign


def test_get_account_unlocked_address(web3_backend):
    addr = web3_backend.w3.eth.accounts[1]
    resolved = web3_backend.get_account(addr)
    assert resolved.address == addr
    assert not resolved.can_sign


def test_sign_message_roundtrip(web3_backend):
    acct = eth_account.Account.create()
    signature = web3_backend.sign_message(acct, b"hello tplus")
    assert len(signature) == 65

    recovered = eth_account.Account.recover_message(
        encode_defunct(primitive=b"hello tplus"), signature=signature
    )
    assert recovered == acct.address


def test_sign_message_rejects_unlocked_account(web3_backend):
    unlocked = web3_backend.w3.eth.accounts[0]
    with pytest.raises(ValueError, match="requires an account with a private key"):
        web3_backend.sign_message(unlocked, b"nope")


def test_deploy_and_read_registry(web3_backend):
    registry = Registry.deploy_dev()
    assert registry.address
    assert registry.admin() == web3_backend.default_test_account().address
    assert registry.get_assets() == []
    # ABI-driven attribute dispatch: a raw view method goes straight through.
    assert isinstance(registry.getAssets(0, 1000), list)


def test_deploy_credential_manager_and_vault(web3_backend):
    registry = Registry.deploy_dev()
    cm = CredentialManager.deploy_dev(registry=registry.address)
    assert cm.governance_nonce == 0
    assert cm.get_vaults() == []

    owner = web3_backend.default_test_account()
    vault = DepositVault.deploy(owner, cm.address, sender=owner)
    assert vault.approved_settlers == []
    assert len(vault.domain_separator) == 32
    assert DepositVault.from_chain_address(vault.chain_address).address == vault.address


def test_transact_updates_state(web3_backend):
    registry = Registry.deploy_dev()
    owner = web3_backend.default_test_account()  # the deployer == the admin
    new_admin = web3_backend.convert_address(web3_backend.w3.eth.accounts[1])

    receipt = registry.setAdmin(new_admin, sender=owner)
    assert receipt["status"] == 1
    assert registry.admin() == new_admin


def test_unknown_contract_method_is_attribute_error(web3_backend):
    registry = Registry.deploy_dev()
    handle = web3_backend.get_contract("Registry", registry.address)
    with pytest.raises(AttributeError, match="has no method 'definitelyNotAMethod'"):
        handle.definitelyNotAMethod()


def test_struct_results_decode_to_named_tuples(web3_backend):
    registry = Registry.deploy_dev()
    data = registry.getAssetData({"routingId": 0, "vmId": 0}, 0, b"\x00" * 32)
    # Nested struct -> attribute access on both levels.
    assert data.index == 0
    assert data.chainId.routingId == 0
    assert data.chainId.vmId == 0


def _build_calldata(web3_backend, fn_name, args):
    """Encode + ABI-build a DepositVault call (proves args survive web3's strict
    type/checksum validation without needing a deployed contract)."""
    abi = _manifest.get_abi("DepositVault")
    entry = next(
        e
        for e in abi
        if e.get("type") == "function"
        and e.get("name") == fn_name
        and len(e["inputs"]) == len(args)
    )
    contract = web3_backend.w3.eth.contract(abi=abi, address="0x" + "11" * 20)
    encoded = _encode_args(web3_backend, entry["inputs"], args)
    sender = web3_backend.w3.eth.accounts[0]
    contract.functions[fn_name](*encoded).build_transaction(
        {"from": sender, "gas": 300000, "gasPrice": 0, "nonce": 0, "chainId": web3_backend.chain_id}
    )


def test_encode_bare_hex_user_key_for_bytes32(web3_backend):
    # UserPublicKey serializes to 0x-less hex; web3 rejects that for bytes32
    # unless we normalize it. ``deposit(user bytes32, token address, amount)``.
    user = "ab" * 32
    _build_calldata(web3_backend, "deposit", [user, "0x" + "cd" * 20, 1000])


def test_encode_nested_tuple_addresses_are_checksummed(web3_backend):
    # web3 rejects non-checksummed (even all-lowercase) addresses; the settlement
    # order tuple carries nested address fields and a bytes32 user key.
    lower = "0x" + "cd" * 20
    order = {
        "tokenOut": lower,
        "amountOut": 1,
        "tokenIn": "0x" + "ef" * 20,
        "amountIn": 2,
        "mode": 0,
        "user": "ab" * 32,
        "account": 0,
        "nonce": 0,
        "validUntil": 0,
    }
    _build_calldata(web3_backend, "executeAtomicSettlement", [order, "ab" * 32, b"\x00", b"\x00"])


def test_get_deployment_address_predicts_create_address(web3_backend):
    owner = web3_backend.default_test_account()
    predicted = owner.get_deployment_address()
    # Deploying from this account at its current nonce yields exactly that address,
    # which is what DepositVault.deploy's domain-separator check relies on.
    registry = Registry.deploy(owner, 0, sender=owner)
    assert registry.address == predicted


def test_create_address_matches_known_vectors():
    from tplus.evm.backends.web3 import _create_address

    sender = "0x6ac7ea33f8831ea9dcc53393aaa88b25a785dbf0"
    assert _create_address(sender, 0).lower() == "0xcd234a471b72ba2f1ccf0a70fcaba648a5eecd8d"
    assert _create_address(sender, 1).lower() == "0x343c43a37d37dff08ae8c4a11544c718abb4fcf8"


def test_translate_web3_custom_error_to_backend_neutral():
    err = web3_exceptions.ContractCustomError("0x7939f424", data="0x7939f424")
    translated = _translate_web3_error(err)
    assert isinstance(translated, ContractLogicError)
    assert translated.message == "0x7939f424"
    assert translated.data == "0x7939f424"


def test_decode_erc20_error_unchanged():
    assert _decode_erc20_error("0x7939f424") == "TransferFromFailed()"
    assert _decode_erc20_error("0x90b8ec18") == "TransferFailed()"
    assert _decode_erc20_error("0xdeadbeef") is None
