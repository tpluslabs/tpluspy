from typing import Any

# A minimal standard ERC20 ABI (enough for balanceOf / transfer / approve /
# allowance / decimals / symbol). The t+ contract ABIs come from the bundled
# manifest (see ``tplus.evm._manifest``); ERC20 is standard so it lives here.
_ERC20_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "name",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "string"}],
    },
    {
        "type": "function",
        "name": "symbol",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "string"}],
    },
    {
        "type": "function",
        "name": "decimals",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint8"}],
    },
    {
        "type": "function",
        "name": "totalSupply",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "allowance",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },
    {
        "type": "function",
        "name": "transfer",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "outputs": [{"type": "bool"}],
    },
    {
        "type": "function",
        "name": "transferFrom",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"type": "bool"}],
    },
    {
        "type": "function",
        "name": "approve",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "outputs": [{"type": "bool"}],
    },
    {
        "type": "event",
        "name": "Transfer",
        "anonymous": False,
        "inputs": [
            {"name": "from", "type": "address", "indexed": True},
            {"name": "to", "type": "address", "indexed": True},
            {"name": "value", "type": "uint256", "indexed": False},
        ],
    },
    {
        "type": "event",
        "name": "Approval",
        "anonymous": False,
        "inputs": [
            {"name": "owner", "type": "address", "indexed": True},
            {"name": "spender", "type": "address", "indexed": True},
            {"name": "value", "type": "uint256", "indexed": False},
        ],
    },
]

_MINT_ABI: dict[str, Any] = {
    "type": "function",
    "name": "mint",
    "stateMutability": "nonpayable",
    "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
    "outputs": [],
}


def get_erc20_abi() -> list[dict[str, Any]]:
    """A standard ERC20 ABI."""
    return [dict(e) for e in _ERC20_ABI]


def get_mock_erc20_abi() -> list[dict[str, Any]]:
    """An ERC20 ABI that also exposes ``mint(address,uint256)``."""
    return [*get_erc20_abi(), dict(_MINT_ABI)]


# Back-compat aliases for the older ``*_type`` names.
get_erc20_type = get_erc20_abi
get_test_erc20_type = get_mock_erc20_abi
