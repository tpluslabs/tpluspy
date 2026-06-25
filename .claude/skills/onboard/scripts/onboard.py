#!/usr/bin/env python3
"""First-time T+ onboarding from an EVM private key.

Reads an EVM private key from ``TPLUS_PRIVATE_KEY`` in your ``.env``, derives the
*frontend-compatible* T+ identity from it (the exact key derivation the T+
terminal frontend performs on wallet login), and then:

* If that identity already controls a T+ account, dumps the account state
  (multisig signers, inventory, solvency, margin, positions, open orders,
  recent trades) so your agent has full context.
* Otherwise, reports that no account exists yet and points you at
  ``create_account.py`` to create a frontend-compatible account.

Nothing here moves funds and nothing is written on-chain. The wallet signature
used for derivation is *never broadcast* — it only seeds the key derivation.

NOTE ON SIGNING: this script calls ``eth_account`` personal-sign **only to
reproduce the frontend's wallet-login signature for key derivation**. This is
NOT a T+ request-signing path. T+ requests are signed with Ed25519 over compact
JSON via ``User.sign()`` (see tpluspy's ``claude.md`` → "Signing model"). Do not
copy this ``eth_account`` usage into T+ request flows.

Requires: ``pip install eth-account eth-keys`` (plus tpluspy itself).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_keys import keys

# --- Import THIS repo's tpluspy, not a stale `pip install tpluspy` -----------
# Running `python3 path/to/onboard.py` puts the SCRIPT's directory on sys.path[0]
# (not the cwd), so a globally-installed — possibly older — tpluspy would shadow
# the source that ships with this repo and whose client API this skill targets.
# (E.g. PyPI tpluspy 0.0.7 exposes `OrderBookClient(user=...)`; the repo source
# exposes `OrderBookClient(base_url=..., default_user=...)` — incompatible.)
# This file lives at <tpluspy>/.claude/skills/onboard/scripts/onboard.py, so
# parents[4] is the package root containing `tplus/`. Prepend it.
_REPO_TPLUSPY = Path(__file__).resolve().parents[4]
if (_REPO_TPLUSPY / "tplus" / "__init__.py").exists():
    sys.path.insert(0, str(_REPO_TPLUSPY))

from tplus.asset_metadata import asset_metadata_dict  # noqa: E402
from tplus.client.orderbook import OrderBookClient  # noqa: E402
from tplus.utils.user import User  # noqa: E402

# Absolute paths so commands we print are copy-pasteable from any cwd.
_THIS = Path(__file__).resolve()
_CREATE_ACCOUNT = _THIS.parent / "create_account.py"

# The exact message the T+ frontend signs on wallet login. Must match byte-for-byte.
MASTER_KEY_MESSAGE = (
    "tplus-core: authorize account\n\n"
    "This signature derives your wallet signer key and will never be broadcast to the blockchain."
)

EVM_KEY_ENV = "TPLUS_PRIVATE_KEY"
BASE_URL_ENV = "TPLUS_API_BASE_URL"

# Public derived keys written back to .env (never private material).
PUBLIC_KEY_ENV = "TPLUS_PUBLIC_KEY"
SIGNER_PUBKEY_ENV = "TPLUS_FRONTEND_SECP256K1_PUBLIC_KEY"

# Marker the calling agent can scan for to find the machine-readable result.
RESULT_MARKER = "=== ONBOARD_RESULT_JSON ==="

# Some gateways reject the default httpx/urllib User-Agent.
BROWSERISH_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="First-time T+ onboarding from an EVM key.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--key-env", default=EVM_KEY_ENV, help="Env var holding the EVM private key."
    )
    parser.add_argument(
        "--base-url-env", default=BASE_URL_ENV, help="Env var holding the T+ API base URL."
    )
    parser.add_argument(
        "--write-env",
        dest="write_env",
        action="store_true",
        default=True,
        help="Write the *public* derived keys back to .env (default).",
    )
    parser.add_argument("--no-write-env", dest="write_env", action="store_false")
    parser.add_argument("--trades-limit", type=int, default=20)
    parser.add_argument(
        "--register-cli-account",
        nargs="?",
        const="onboard",
        default=None,
        metavar="ALIAS",
        help=(
            "Import the derived T+ key into the local `tplus` CLI keystore under ALIAS "
            "(default 'onboard') so `tplus --tplus-account ALIAS ...` authenticates as this "
            "account. The private key is never printed. Set TPLUS_PASSWORD to import without "
            "an interactive keystore-password prompt."
        ),
    )
    return parser.parse_args()


# --------------------------------------------------------------------------- #
# env handling
# --------------------------------------------------------------------------- #
def load_env_file(path: Path) -> dict[str, str]:
    """Load values from a .env file. Uses python-dotenv if available, else a
    minimal parser. os.environ takes precedence at the call site (see resolve)."""
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


def update_env_file(path: Path, updates: dict[str, str]) -> list[str]:
    """Idempotently set KEY=VALUE lines in .env. Returns the keys written."""
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
        existing.append("# T+ onboarding — public derived keys (no secrets)")
        existing.extend(f"{k}={updates[k]}" for k in missing)

    path.write_text("\n".join(existing) + "\n")
    return list(updates.keys())


# --------------------------------------------------------------------------- #
# derivation
# --------------------------------------------------------------------------- #
def normalize_hexkey(value: str) -> str:
    value = value.strip()
    return value if value.startswith("0x") else "0x" + value


def derive_identity(evm_private_key: str) -> dict[str, Any]:
    """Derive the frontend-compatible T+ identity from an EVM private key.

    Returns only public material plus the in-memory ``User`` for auth. The
    Ed25519 private seed is intentionally never returned or printed.
    """
    evm_private_key = normalize_hexkey(evm_private_key)
    evm_account = Account.from_key(evm_private_key)
    signed = Account.sign_message(encode_defunct(text=MASTER_KEY_MESSAGE), evm_private_key)

    digest = hashlib.sha512(bytes(signed.signature)).digest()
    ed25519_seed = digest[:32]
    secp256k1_seed = digest[32:64]

    tplus_user = User(private_key="0x" + ed25519_seed.hex())
    secp_pub = keys.PrivateKey(secp256k1_seed).public_key.to_compressed_bytes()

    return {
        "evm_address": evm_account.address,
        "tplus_user": tplus_user,  # in-memory only
        "tplus_public_key": tplus_user.public_key,  # bare hex == T+ account id
        "frontend_secp256k1_public_key": "0x" + secp_pub.hex(),
        "frontend_secp256k1_public_key_bytes": list(secp_pub),  # 33 compressed bytes
    }


# --------------------------------------------------------------------------- #
# /multisig/signers lookup
# --------------------------------------------------------------------------- #
def post_json(base_url: str, path: str, payload: Any) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310 - scheme is operator-supplied TPLUS_API_BASE_URL
        base_url.rstrip("/") + path, data=body, method="POST", headers=BROWSERISH_HEADERS
    )
    with urllib.request.urlopen(req, timeout=20) as response:  # noqa: S310
        return json.load(response)


def accounts_for_signer(base_url: str, secp_bytes: bytes) -> list[str]:
    """POST /multisig/signers with the 33-byte compressed secp key; return the
    T+ account public key(s) this signer controls."""
    response = post_json(base_url, "/multisig/signers", {"Secp256k1": list(secp_bytes)})
    if isinstance(response, dict):
        accounts = response.get("accounts", response.get("master_keys", response.get("users", [])))
    else:
        accounts = response
    return [str(a) for a in accounts] if isinstance(accounts, list) else []


def _norm_pk(pubkey: str) -> str:
    return pubkey.lower().removeprefix("0x")


# --------------------------------------------------------------------------- #
# account inspection
# --------------------------------------------------------------------------- #
def to_jsonable(obj: Any) -> Any:
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:
            return dump()
    if isinstance(obj, list):
        return [to_jsonable(o) for o in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj


def enrich_market_metadata(market: Any) -> Any:
    rec = to_jsonable(market)
    if not isinstance(rec, dict):
        return rec

    asset_metadata = asset_metadata_dict(rec.get("asset_id"))
    if asset_metadata is None:
        rec.setdefault("symbol", None)
        rec.setdefault("asset_class", None)
        rec.setdefault("representations", None)
        return rec

    rec.update(asset_metadata)
    return rec


async def inspect_account(base_url: str, user: User, trades_limit: int) -> dict[str, Any]:
    """Read-only dump of everything useful about the account."""
    client = OrderBookClient(
        base_url=base_url, default_user=user, log_level=logging.WARNING, headers=BROWSERISH_HEADERS
    )
    out: dict[str, Any] = {}

    async def safe(name: str, coro: Any) -> None:
        try:
            out[name] = to_jsonable(await coro)
        except Exception as err:  # noqa: BLE001 - resilient per-section dump
            out[name] = {"error": f"{type(err).__name__}: {err}"}

    try:
        await safe("multisig_config", client.get_multisig_config(user=user))
        await safe("inventory", client.get_user_inventory(user=user))
        await safe("solvency", client.get_user_solvency(user=user))
        await safe("margin", client.get_user_margin_info(include_positions=True, user=user))
        await safe("positions", client.get_user_positions(user=user))
        try:
            orders, _raw = await client.get_user_orders(user=user)
            out["open_orders"] = to_jsonable(orders)
        except Exception as err:  # noqa: BLE001
            out["open_orders"] = {"error": f"{type(err).__name__}: {err}"}
        await safe("recent_trades", client.get_user_trades(user=user, limit=trades_limit))
        try:
            markets = await client._request("GET", "/markets", requires_auth=False)
            if isinstance(markets, list):
                out["markets"] = [enrich_market_metadata(market) for market in markets]
            else:
                out["markets"] = to_jsonable(markets)
        except Exception as err:  # noqa: BLE001
            out["markets"] = {"error": f"{type(err).__name__}: {err}"}
    finally:
        await client.close()

    return out


def _count(value: Any) -> str:
    if isinstance(value, list):
        return str(len(value))
    if isinstance(value, dict) and "error" in value:
        return f"error ({value['error']})"
    return "n/a"


def print_account_summary(account: dict[str, Any]) -> None:
    cfg = account.get("multisig_config")
    if isinstance(cfg, dict) and "error" not in cfg:
        signers = cfg.get("signers")
        n_signers = len(signers) if isinstance(signers, list) else "?"
        thresholds = {
            k: cfg.get(k)
            for k in ("master_weight", "low_threshold", "medium_threshold", "high_threshold")
            if k in cfg
        }
        print(f"  multisig      : {n_signers} signer(s), thresholds={thresholds or 'n/a'}")
    print(f"  positions     : {_count(account.get('positions'))}")
    print(f"  open_orders   : {_count(account.get('open_orders'))}")
    print(f"  recent_trades : {_count(account.get('recent_trades'))}")
    markets = account.get("markets")
    print(f"  markets       : {_count(markets)}")
    if isinstance(markets, list):
        for market in markets:
            if not isinstance(market, dict):
                continue
            asset_id = market.get("asset_id")
            symbol = market.get("symbol") or "symbol unavailable"
            price_decimals = market.get("book_price_decimals")
            quantity_decimals = market.get("book_quantity_decimals")
            print(
                f"    - {asset_id}: {symbol}, price_decimals={price_decimals}, "
                f"quantity_decimals={quantity_decimals}"
            )
    inv = account.get("inventory")
    if isinstance(inv, dict) and "error" not in inv:
        print(f"  inventory keys: {', '.join(inv.keys()) or '(empty)'}")
    print("  (full detail in the JSON block below)")


# --------------------------------------------------------------------------- #
# entry
# --------------------------------------------------------------------------- #
def emit(result: dict[str, Any]) -> None:
    print("\n" + RESULT_MARKER)
    print(json.dumps(result, indent=2, default=str))


def register_cli_account(user: User, alias: str) -> str:
    """Import the derived Ed25519 key into the local `tplus` CLI keystore (encrypted).

    Lets `tplus --tplus-account <alias> ...` authenticate as this account. The private
    key is never printed. Skips (rather than hangs) when no keystore password is
    available non-interactively.
    """
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

    from tplus.utils.user.manager import UserManager

    mgr = UserManager()
    if alias in set(mgr.usernames):
        return f"CLI account '{alias}' already exists — skipping import."
    if not os.environ.get("TPLUS_PASSWORD") and not sys.stdin.isatty():
        return (
            f"Skipped CLI key import for '{alias}': set TPLUS_PASSWORD to import "
            f"non-interactively, then re-run with --register-cli-account {alias}."
        )
    seed = user.sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    mgr.add(alias, seed)  # encrypts to ~/.tplus/users/<alias>; uses TPLUS_PASSWORD or prompts
    return f"Imported your T+ key into the CLI keystore as '{alias}'."


def _verify_client_api() -> None:
    """Fail loudly if an incompatible tpluspy (e.g. stale PyPI build) was imported."""
    import inspect

    import tplus
    from tplus.client.base import BaseClient

    if "default_user" not in inspect.signature(BaseClient.__init__).parameters:
        raise SystemExit(
            f"Incompatible tpluspy imported from {getattr(tplus, '__file__', None)!r}.\n"
            f"This skill targets the tpluspy in this repo: {_REPO_TPLUSPY}\n"
            f"Install it with `pip install -e '{_REPO_TPLUSPY}'` (or run with that "
            f"environment active) and re-run."
        )


def main() -> None:
    args = parse_args()
    _verify_client_api()
    file_values = load_env_file(args.env_file)

    def resolve(name: str) -> str:
        return (os.environ.get(name) or file_values.get(name) or "").strip()

    base_url = resolve(args.base_url_env)
    evm_key = resolve(args.key_env)

    result: dict[str, Any] = {
        "status": None,
        "env_file": str(args.env_file),
        "key_env": args.key_env,
        "base_url_env": args.base_url_env,
    }

    if not evm_key:
        print(
            f"No EVM private key found in {args.key_env} (checked {args.env_file} and the environment)."
        )
        print(f"\nAdd this line to {args.env_file} — a 0x-prefixed 32-byte hex EVM private key:")
        print(f"  {args.key_env}=0x<your-evm-private-key>")
        print("\nThis is the same wallet key the T+ frontend uses on login; the script derives")
        print("your T+ keys from it. The key is never broadcast and never printed.")
        result["status"] = "missing_key"
        emit(result)
        sys.exit(3)

    if not base_url:
        print(
            f"No T+ API base URL found in {args.base_url_env} (checked {args.env_file} and the environment)."
        )
        print(f"\nAdd this line to {args.env_file}:")
        print(f"  {args.base_url_env}=https://<your-tplus-oms-host>")
        result["status"] = "missing_base_url"
        emit(result)
        sys.exit(4)

    ident = derive_identity(evm_key)
    result.update(
        {
            "evm_address": ident["evm_address"],
            "tplus_public_key": ident["tplus_public_key"],
            "frontend_secp256k1_public_key": ident["frontend_secp256k1_public_key"],
            "base_url": base_url,
        }
    )

    print("Derived your frontend-compatible T+ identity (no private keys shown):")
    print(f"  evm_address                   = {ident['evm_address']}")
    print(f"  tplus_public_key (account id) = {ident['tplus_public_key']}")
    print(f"  frontend_secp256k1_public_key = {ident['frontend_secp256k1_public_key']}")

    if args.register_cli_account:
        try:
            print(register_cli_account(ident["tplus_user"], args.register_cli_account))
            result["cli_account"] = args.register_cli_account
        except Exception as err:  # noqa: BLE001
            print(f"warning: CLI key import failed ({type(err).__name__}: {err})")

    lookup_failed = False
    try:
        accts = accounts_for_signer(base_url, bytes(ident["frontend_secp256k1_public_key_bytes"]))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as err:
        accts = []
        lookup_failed = True
        print(f"\nwarning: /multisig/signers lookup failed ({type(err).__name__}: {err}).")

    exists = any(_norm_pk(a) == _norm_pk(ident["tplus_public_key"]) for a in accts)

    if exists:
        result["status"] = "existing_account"
        print("\nThis key already controls a T+ account. Fetching account state...\n")
        account = asyncio.run(inspect_account(base_url, ident["tplus_user"], args.trades_limit))
        result["account"] = account
        print_account_summary(account)
        print(
            "\nNext: open reference/tpluspy-primer.md to start building scripts against this account."
        )
    elif lookup_failed:
        result["status"] = "lookup_failed"
        result["account"] = None
        print(
            "\nCould not verify whether this key has a T+ account — the lookup failed.\n"
            f"Check that {args.base_url_env} ({base_url}) is reachable and correct, then re-run.\n"
            "Not creating an account: a transient lookup failure can look like 'no account'."
        )
    else:
        result["status"] = "no_account"
        result["account"] = None
        print("\nNo T+ account is associated with this key yet.")
        if args.write_env:
            try:
                written = update_env_file(
                    args.env_file,
                    {
                        PUBLIC_KEY_ENV: ident["tplus_public_key"],
                        SIGNER_PUBKEY_ENV: ident["frontend_secp256k1_public_key"],
                    },
                )
                print(
                    f"Wrote public derived keys to {args.env_file}: {', '.join(written)} (no private keys written)."
                )
            except OSError as err:
                print(
                    f"warning: could not write {args.env_file} ({err}). Add these lines yourself:"
                )
                print(f"  {PUBLIC_KEY_ENV}={ident['tplus_public_key']}")
                print(f"  {SIGNER_PUBKEY_ENV}={ident['frontend_secp256k1_public_key']}")
        print("\nTo create a frontend-compatible account (on-chain USDC deposit on Arbitrum):")
        print(
            "  1) pip install web3, and fund your EVM address with USDC AND ETH (gas) on Arbitrum,"
        )
        print("     and have it allow-listed as a depositor (canDeposit) — see SKILL.md Step 3b.")
        print(f"  2) Preview:  python {_CREATE_ACCOUNT}")
        print(f"  3) Execute:  python {_CREATE_ACCOUNT} --execute")
        print(f"  4) Re-run:   python {_THIS}   (to confirm the account is live)")

    if result["status"] in ("existing_account", "no_account"):
        print(
            "\nUse the `tplus` CLI against this deployment (run `pip install -e .` in the tpluspy\n"
            "package to get the `tplus` command; otherwise use `python -m tplus._cli ...`):\n"
            f"  export TPLUS_API_BASE_URL={base_url}   # the only URL the CLI needs (market-data derived: oms->mds)\n"
            f"  python {_THIS} --register-cli-account   # one-time: import key into CLI keystore (encrypted)\n"
            "  # no account needed: tplus params list | tplus markets depth <asset> | tplus markets klines <asset>\n"
            "  # as your account:   tplus --tplus-account onboard balance | orders list | trades list | stream user-trades\n"
            "See reference/tpluspy-primer.md for the full CLI + SDK cheatsheet."
        )

    emit(result)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"error={type(exc).__name__}: {exc}", file=sys.stderr)
        raise
