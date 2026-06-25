#!/usr/bin/env python3
"""Create a frontend-compatible T+ account from your EVM key.

A T+ account is bootstrapped on-chain: you deposit USDC into the T+ vault, and
that deposit registers your account's master key + initial signer config. This
script derives the same keys the T+ frontend would (from ``TPLUS_PRIVATE_KEY``)
and submits the vault ``deposit`` so the account is usable from BOTH the frontend
(secp256k1 wallet signer) and tpluspy (Ed25519 master key).

It is a generated template — copy it into your own workspace and adapt the
amount / multisig thresholds as needed.

Safety: dry-run by default. It only reads chain + registry state and prints a
plan. Pass ``--execute`` to actually broadcast the approve + deposit txs.

Prerequisites for ``--execute``:
  * Your EVM address (from TPLUS_PRIVATE_KEY) holds USDC on Arbitrum.
  * Your EVM address is allow-listed as a depositor (``vault.canDeposit`` true).
    Allow-listing is an operator action (tpluslabs/harness "Set Depositor
    Status"); ask whoever runs your T+ deployment if canDeposit is false.

NOTE ON SIGNING: ``eth_account`` personal-sign here only reproduces the
frontend's wallet-login signature for *key derivation*. The T+ master-config
signature is Ed25519 via ``User.sign()`` — the protocol's own scheme.

Requires: ``pip install web3 eth-account eth-keys`` (plus tpluspy itself).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any

# --- Import THIS repo's tpluspy first (see onboard.py for the full rationale).
# This file is at <tpluspy>/.claude/skills/onboard/scripts/create_account.py →
# parents[4] is the package root containing `tplus/`. Prepend it so the
# master-config signing uses the repo's User implementation.
_REPO_TPLUSPY = Path(__file__).resolve().parents[4]
if (_REPO_TPLUSPY / "tplus" / "__init__.py").exists():
    sys.path.insert(0, str(_REPO_TPLUSPY))

# Import heavy/optional deps tolerantly so `--help` (and clear errors) work even
# when web3 / eth-account / eth-keys aren't installed; main() reports the gap.
try:
    from eth_account import Account  # noqa: E402
    from eth_account.messages import encode_defunct  # noqa: E402
    from eth_keys import keys  # noqa: E402
    from web3 import Web3  # noqa: E402

    from tplus.utils.user import User  # noqa: E402

    _MISSING_DEP: ModuleNotFoundError | None = None
except ModuleNotFoundError as err:  # noqa: E402
    _MISSING_DEP = err

# Must match onboard.py and the T+ frontend byte-for-byte.
MASTER_KEY_MESSAGE = (
    "tplus-core: authorize account\n\n"
    "This signature derives your wallet signer key and will never be broadcast to the blockchain."
)

EVM_KEY_ENV = "TPLUS_PRIVATE_KEY"
BASE_URL_ENV = "TPLUS_API_BASE_URL"
DEFAULT_RPC_URL = "https://arb1.arbitrum.io/rpc"

VAULT_ABI = [
    {
        "inputs": [{"name": "", "type": "address"}],
        "name": "canDeposit",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "", "type": "bytes32"}],
        "name": "depositCounts",
        "outputs": [{"name": "", "type": "uint64"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "user", "type": "bytes32"},
            {"name": "tokenAddress", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "masterWeight", "type": "uint32"},
            {"name": "lowThreshold", "type": "uint32"},
            {"name": "mediumThreshold", "type": "uint32"},
            {"name": "highThreshold", "type": "uint32"},
            {
                "name": "signers",
                "type": "tuple[]",
                "components": [
                    {"name": "key", "type": "bytes32"},
                    {"name": "keyType", "type": "uint8"},
                    {"name": "keyPrefix", "type": "uint8"},
                    {"name": "weight", "type": "uint32"},
                    {"name": "expiresAtNs", "type": "uint64"},
                    {"name": "maxSigningWindowNs", "type": "uint64"},
                ],
            },
            {"name": "masterConfigSignature", "type": "bytes"},
        ],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

ERC20_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a frontend-compatible T+ account.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--key-env", default=EVM_KEY_ENV)
    parser.add_argument("--base-url-env", default=BASE_URL_ENV)
    parser.add_argument("--rpc-url", default="")
    parser.add_argument("--amount-usdc", default="10")
    parser.add_argument("--chain-id", type=int, default=42161)
    # 1/1/1/1 = the frontend secp signer (weight 1) can act on its own, matching
    # the frontend-compatible demo provisioning defaults.
    parser.add_argument("--master-weight", type=int, default=1)
    parser.add_argument("--low-threshold", type=int, default=1)
    parser.add_argument("--medium-threshold", type=int, default=1)
    parser.add_argument("--high-threshold", type=int, default=1)
    parser.add_argument(
        "--execute", action="store_true", help="Broadcast approve + deposit (default: dry-run)."
    )
    return parser.parse_args()


def load_env_file(path: Path) -> dict[str, str]:
    try:
        from dotenv import dotenv_values

        return {k: v for k, v in dotenv_values(path).items() if v is not None}
    except ModuleNotFoundError:
        values: dict[str, str] = {}
        if path.exists():
            for raw in path.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                line = line.removeprefix("export ").strip()
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip().strip('"').strip("'")
        return values


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    existing = path.read_text().splitlines() if path.exists() else []
    replaced: set[str] = set()
    key_re = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
    for idx, line in enumerate(existing):
        match = key_re.match(line)
        if match and match.group(1) in updates:
            existing[idx] = f"{match.group(1)}={updates[match.group(1)]}"
            replaced.add(match.group(1))
    missing = [k for k in updates if k not in replaced]
    if missing:
        if existing and existing[-1].strip():
            existing.append("")
        existing.append("# T+ account creation")
        existing.extend(f"{k}={updates[k]}" for k in missing)
    path.write_text("\n".join(existing) + "\n")


def normalize_hexkey(value: str) -> str:
    value = value.strip()
    return value if value.startswith("0x") else "0x" + value


def derive_identity(evm_private_key: str) -> dict[str, Any]:
    evm_private_key = normalize_hexkey(evm_private_key)
    evm_account = Account.from_key(evm_private_key)
    signed = Account.sign_message(encode_defunct(text=MASTER_KEY_MESSAGE), evm_private_key)
    digest = hashlib.sha512(bytes(signed.signature)).digest()
    tplus_user = User(private_key="0x" + digest[:32].hex())
    secp_pub = keys.PrivateKey(digest[32:64]).public_key.to_compressed_bytes()
    return {
        "evm_address": evm_account.address,
        "tplus_user": tplus_user,
        "tplus_public_key": tplus_user.public_key,
        "secp_public_key": secp_pub,
        "secp_public_key_hex": "0x" + secp_pub.hex(),
    }


def fetch_json(base_url: str, path: str) -> Any:
    req = urllib.request.Request(  # noqa: S310 - scheme is operator-supplied TPLUS_API_BASE_URL
        base_url.rstrip("/") + path,
        headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:  # noqa: S310
        return json.load(response)


def registry_addresses(base_url: str, chain_id: int) -> tuple[str, str]:
    """Resolve (vault, USDC) addresses for ``chain_id`` from the T+ registry."""
    vaults = fetch_json(base_url, "/registry/vaults")
    assets = fetch_json(base_url, "/registry/assets")

    vault = None
    for item in vaults:
        address_part, chain_part = item.split("@", 1)
        if int(chain_part, 16) == chain_id:
            vault = Web3.to_checksum_address("0x" + address_part[:40])
            break
    if vault is None:
        raise RuntimeError(f"No vault registered for chain {chain_id}")

    usdc = None
    for key in assets.get("0", {}):
        address_part, chain_part = key.split("@", 1)
        if int(chain_part, 16) == chain_id:
            usdc = Web3.to_checksum_address("0x" + address_part[:40])
            break
    if usdc is None:
        raise RuntimeError(f"No USD asset registered for chain {chain_id}")

    return vault, usdc


def build_signer_config(
    pubkey_hex: str,
) -> tuple[list[dict[str, Any]], list[tuple[bytes, int, int, int, int, int]]]:
    raw = bytes.fromhex(pubkey_hex.removeprefix("0x"))
    if len(raw) != 33 or raw[0] not in (2, 3):
        raise ValueError("frontend signer must be a 33-byte compressed secp256k1 key")
    # key_type 1 == secp256k1; key_prefix is the compression byte (0x02/0x03).
    signable = [
        {
            "key": list(raw[1:]),
            "key_type": 1,
            "key_prefix": raw[0],
            "weight": 1,
            "expires_at_ns": 0,
            "max_signing_window_ns": 0,
        }
    ]
    onchain = [(raw[1:], 1, raw[0], 1, 0, 0)]
    return signable, onchain


def initial_config_payload(
    master_weight: int, low: int, medium: int, high: int, signers: list[dict[str, Any]]
) -> str:
    payload = {
        "master_weight": master_weight,
        "low_threshold": low,
        "medium_threshold": medium,
        "high_threshold": high,
        "signers": signers,
    }
    return json.dumps(payload, separators=(",", ":"))


def with_fees(w3: Web3, tx: dict[str, Any]) -> dict[str, Any]:
    if "gasPrice" in tx or "maxFeePerGas" in tx:
        return tx
    try:
        priority = w3.eth.max_priority_fee
    except Exception:  # noqa: BLE001
        priority = w3.to_wei(0.01, "gwei")
    gas_price = w3.eth.gas_price
    tx["maxPriorityFeePerGas"] = priority
    tx["maxFeePerGas"] = max(gas_price * 2, priority * 2)
    return tx


def sign_and_send(w3: Web3, account: Any, tx: dict[str, Any]) -> str:
    tx = dict(tx)
    tx.setdefault("chainId", w3.eth.chain_id)
    tx.setdefault("from", account.address)
    tx.setdefault("nonce", w3.eth.get_transaction_count(account.address))
    tx = with_fees(w3, tx)
    if "gas" not in tx:
        tx["gas"] = int(w3.eth.estimate_gas(tx) * Decimal("1.25"))
    signed = account.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
    if receipt.status != 1:
        raise RuntimeError(f"Transaction failed: {tx_hash.hex()}")
    return tx_hash.hex()


def main() -> None:
    args = parse_args()
    if _MISSING_DEP is not None:
        raise SystemExit(
            f"create_account.py needs extra deps (missing: {_MISSING_DEP.name}). Install them:\n"
            "  pip install web3 eth-account eth-keys\n"
            "Creating an account also requires USDC AND ETH (gas) on Arbitrum, and your EVM "
            "address allow-listed as a depositor (canDeposit). See SKILL.md Step 3b."
        )
    env = load_env_file(args.env_file)

    def resolve(name: str) -> str:
        return (os.environ.get(name) or env.get(name) or "").strip()

    evm_key = resolve(args.key_env)
    if not evm_key:
        raise RuntimeError(f"{args.key_env} is required (the EVM private key; see onboard.py).")
    base_url = resolve(args.base_url_env)
    if not base_url:
        raise RuntimeError(f"{args.base_url_env} is required")

    ident = derive_identity(evm_key)
    # The EVM key is both the derivation source and the depositor/tx signer.
    depositor = Account.from_key(normalize_hexkey(evm_key))

    rpc_url = (
        args.rpc_url
        or resolve("TPLUS_ONCHAIN_ARBITRUM_RPC_URL")
        or resolve("ARBITRUM_RPC_URL")
        or resolve("RPC_URL")
        or DEFAULT_RPC_URL
    )
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise RuntimeError(f"RPC not connected: {rpc_url}")
    if w3.eth.chain_id != args.chain_id:
        raise RuntimeError(f"RPC chain_id={w3.eth.chain_id}, expected {args.chain_id}")

    vault_address, usdc_address = registry_addresses(base_url, args.chain_id)
    vault = w3.eth.contract(address=vault_address, abi=VAULT_ABI)
    token = w3.eth.contract(address=usdc_address, abi=ERC20_ABI)
    decimals = token.functions.decimals().call()
    symbol = token.functions.symbol().call()
    amount_atomic = int(Decimal(args.amount_usdc) * (10**decimals))
    if amount_atomic <= 0:
        raise RuntimeError("Deposit amount must be positive")

    signable_signers, onchain_signers = build_signer_config(ident["secp_public_key_hex"])
    config_payload = initial_config_payload(
        args.master_weight,
        args.low_threshold,
        args.medium_threshold,
        args.high_threshold,
        signable_signers,
    )
    master_signature = ident["tplus_user"].sign(config_payload)

    user_b32 = bytes.fromhex(ident["tplus_public_key"])
    deposit_count = vault.functions.depositCounts(user_b32).call()
    can_deposit = vault.functions.canDeposit(depositor.address).call()
    balance = token.functions.balanceOf(depositor.address).call()
    allowance = token.functions.allowance(depositor.address, vault_address).call()

    print(f"evm_address (depositor)      = {depositor.address}")
    print(f"tplus_public_key (account id)= {ident['tplus_public_key']}")
    print(f"frontend_secp256k1_signer    = {ident['secp_public_key_hex']}")
    print(f"vault={vault_address} token={symbol}:{usdc_address} decimals={decimals}")
    print(
        f"config = master_weight:{args.master_weight} low:{args.low_threshold} "
        f"medium:{args.medium_threshold} high:{args.high_threshold} signer_weight:1"
    )
    print(
        f"deposit_count={deposit_count} can_deposit={can_deposit} "
        f"balance_atomic={balance} allowance_atomic={allowance} amount_atomic={amount_atomic}"
    )

    if deposit_count != 0:
        raise RuntimeError(
            "This account already has deposits; the initial config cannot be replayed. Run onboard.py."
        )
    if not can_deposit:
        raise RuntimeError(
            f"{depositor.address} is not allow-listed for deposit (canDeposit=false). "
            "Ask your T+ operator to set depositor status for this address."
        )
    if balance < amount_atomic:
        raise RuntimeError(f"Insufficient {symbol}: balance {balance}, need {amount_atomic}")

    if not args.execute:
        print("\ndry_run=true — re-run with --execute to broadcast approve + deposit.")
        return

    if allowance < amount_atomic:
        approve_tx = token.functions.approve(vault_address, amount_atomic).build_transaction(
            {"from": depositor.address}
        )
        approve_hash = sign_and_send(w3, depositor, approve_tx)
        print(f"approve_tx={approve_hash}")
    else:
        print("approve_tx=skipped_existing_allowance")

    deposit_tx = vault.functions.deposit(
        user_b32,
        usdc_address,
        amount_atomic,
        args.master_weight,
        args.low_threshold,
        args.medium_threshold,
        args.high_threshold,
        onchain_signers,
        master_signature,
    ).build_transaction({"from": depositor.address})
    deposit_hash = sign_and_send(w3, depositor, deposit_tx)
    print(f"deposit_tx={deposit_hash}")
    print(f"post_deposit_count={vault.functions.depositCounts(user_b32).call()}")

    update_env_file(
        args.env_file,
        {
            "TPLUS_PUBLIC_KEY": ident["tplus_public_key"],
            "TPLUS_FRONTEND_SECP256K1_PUBLIC_KEY": ident["secp_public_key_hex"],
        },
    )
    print("\nAccount created. Run onboard.py to confirm and inspect state.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        raise
