---
name: onboard
description: First-time onboarding for a tpluspy user who has an EVM private key. Use when someone has cloned tpluspy and wants to get started, connect their wallet/EVM key to T+, check whether they already have a T+ account and see what's in it, or create a new frontend-compatible T+ account. Derives the T+ identity from the EVM key in TPLUS_PRIVATE_KEY, looks it up via the /multisig/signers endpoint, dumps account state if it exists, and otherwise guides account creation. Common triggers include "onboard me", "set up tplus", "do I have a tplus account", and "get me started with tpluspy".
---

# T+ onboarding

Walk a first-time user from "I have an EVM private key" to either (a) a full view
of their existing T+ account plus the context to start building, or (b) a guided
path to create a new frontend-compatible account.

The EVM key in `TPLUS_PRIVATE_KEY` is the single source of truth. The T+ identity
(Ed25519 master key = account id, plus a secp256k1 frontend signer) is **derived**
from it — the same derivation the T+ terminal frontend does on wallet login — so
the account is usable from both the frontend and tpluspy.

## Secret-handling rules (do this every time)

- **Never** read, print, echo, or commit `TPLUS_PRIVATE_KEY` or any derived
  *private* key. The scripts consume `.env` themselves; you do not need to open it.
- If you must confirm a value exists, check presence only (e.g. `grep -q`), never
  print the value.
- Public keys (T+ account id, secp signer pubkey) and addresses are safe to show.

## Prerequisites

- Run from a directory that has the user's `.env` (usually the repo root), or pass
  `--env-file` to the scripts. `.env` must contain `TPLUS_API_BASE_URL`.
- Install the derivation deps once: `pip install eth-account eth-keys`
  (add `web3` only if you'll create an account: `pip install web3`).
- `tpluspy` itself must be importable (`pip install -e .` from the package root,
  or run with the package on `PYTHONPATH`).

Scripts live next to this file under `scripts/`. Resolve the skill directory
first, then invoke scripts through that path. In this repo, Codex CLI exposes it
at `.agents/skills/onboard`; if the skill is loaded from another location,
substitute that directory for `SKILL_DIR`.

## Step 1 — make sure the EVM key is present

If `TPLUS_PRIVATE_KEY` is not set, tell the user to add it to `.env`:

```
TPLUS_PRIVATE_KEY=0x<your 32-byte hex EVM private key>
```

Explain: this is the wallet key the T+ frontend would use; the script derives the
T+ keys from it and never broadcasts or prints it. Then continue.

## Step 2 — derive + look up the account

```bash
SKILL_DIR=.agents/skills/onboard
python "$SKILL_DIR/scripts/onboard.py"  # add --env-file <path> if .env isn't in cwd
```

On the `no_account` path, `onboard.py` appends the **public** derived keys to `.env`
by default (never private keys) — pass `--no-write-env` to leave `.env` untouched.

This derives the identity, calls `POST /multisig/signers` with the 33-byte
compressed secp key, prints a human summary, and ends with a machine-readable
block after the line `=== ONBOARD_RESULT_JSON ===`. Parse that JSON; branch on
`status`:

| `status` | Meaning | What you do |
| --- | --- | --- |
| `missing_key` | `TPLUS_PRIVATE_KEY` not set | Go back to Step 1. |
| `missing_base_url` | `TPLUS_API_BASE_URL` not set | Ask the user for their T+ OMS URL; add it to `.env`. |
| `existing_account` | Key already controls a T+ account | Go to **Step 3a**. |
| `no_account` | No account yet | Go to **Step 3b**. |

## Step 3a — existing account

The JSON's `account` field holds `multisig_config`, `inventory`, `solvency`,
`margin`, `positions`, `open_orders`, and `recent_trades` (each may be an
`{"error": …}` object if that read failed — report those honestly).

Before writing the summary, resolve market metadata:

- Run `tplus markets list` if the CLI is available; otherwise use
  `python -m tplus._cli markets list`. If neither is available, call
  `GET /markets` through `OrderBookClient` or fetch per-asset metadata with
  `await client.get_market(AssetIdentifier(...))` for every asset id seen in
  inventory, positions, open/recent orders, and recent trades.
- Resolve symbols with `tplus.asset_metadata` for every market/index and every
  asset id seen in account state. This is a local display-only snapshot from the
  risk-params repo; it covers canonical production indexes and known
  `address@chain` aliases. Do not infer symbols from prices.
- Include a compact "Markets / indexes" section in the user-facing report that
  lists every market index / asset id returned, plus symbol, asset class,
  representations, price decimals, quantity decimals, max leverage, tick size,
  and minimum order size.
- Use the resolved metadata to label balances, positions, orders, and trades.
  If a symbol/name is not present, keep the asset label as `asset <id>` and say
  the symbol was not available.

1. Give the user a plain-language summary: balances/inventory, open positions and
   orders, margin/solvency health, who can sign (multisig signers + thresholds),
   and the resolved markets/indexes.
2. Open `reference/tpluspy-primer.md` and use it to help them build whatever they
   need next — re-deriving the `User`, constructing `OrderBookClient`, and the
   verified task→call table are all there.
3. Offer concrete next steps based on what they want (e.g. a script to stream
   their fills, place/cancel an order, or report PnL). Build those on the primer,
   and surface ready-to-run `tplus` CLI commands too (see "Also offer the `tplus`
   CLI" below) — for many goals the CLI is faster than a script.

## Step 3b — no account yet

Creating a frontend-compatible account is an on-chain USDC deposit on Arbitrum
that registers the account's master key + the secp signer. `onboard.py` has
already written the **public** derived keys to `.env`.

Explain the prerequisites, then drive `scripts/create_account.py`:

1. Prerequisites: `pip install web3`; the EVM address must hold **USDC** (the
   deposit) **and ETH for gas** on Arbitrum, **and** be allow-listed as a depositor
   (`vault.canDeposit` true). Allow-listing is an operator action (tpluslabs/harness
   "Set Depositor Status") — if `canDeposit` is false, tell the user to ask whoever
   runs their T+ deployment. (`create_account.py` validates these and prints a clear
   message if web3 is missing.)
2. Preview (no funds move): `python "$SKILL_DIR/scripts/create_account.py"`
   — it prints the plan and the `canDeposit` / balance / allowance checks.
3. Execute when ready: `python "$SKILL_DIR/scripts/create_account.py" --execute`
   (defaults: 10 USDC, multisig 1/1/1/1 so the frontend signer can act alone;
   adjust with `--amount-usdc`, `--master-weight`, `--*-threshold`).
4. Confirm: re-run `python "$SKILL_DIR/scripts/onboard.py"` — it should now report
   `existing_account`. Then continue with Step 3a.

## Also offer the `tplus` CLI

For many goals the `tplus` CLI is faster than a script — surface ready-to-run
commands to the user. Two setup gotchas: the `tplus` command only exists after
`pip install -e .` in the tpluspy package (otherwise use `python -m tplus._cli ...`),
and it authenticates from its own keystore. It honors `TPLUS_API_BASE_URL` as the
single URL (orderbook = that host; market-data derived by swapping `oms`->`mds`).

```bash
# 1) The CLI needs only TPLUS_API_BASE_URL (per-service vars override if ever needed):
export TPLUS_API_BASE_URL=https://oms.tplus.cx
# 2) Import the onboarded identity into the CLI keystore (key never printed):
SKILL_DIR=.agents/skills/onboard
python "$SKILL_DIR/scripts/onboard.py" --register-cli-account  # account 'onboard'; set TPLUS_PASSWORD to skip the prompt
export TPLUS_ACCOUNT=onboard
```

- No account needed: `tplus params list`, `tplus markets depth <asset>`, `tplus markets klines <asset>`, `tplus stream depth <asset>`, `tplus --help`.
- As the account: `tplus markets list`, `tplus balance`, `tplus orders list`, `tplus orders place --help`, `tplus trades list`, `tplus stream user-trades`.

Full cheatsheet: `reference/tpluspy-primer.md`. (`onboard.py` also prints these export lines on every run.)

## Notes

- `onboard.py` needs only `eth-account` + `eth-keys` (no chain access).
  `create_account.py` additionally needs `web3` and on-chain USDC + gas.
- If `/multisig/signers` is unreachable, `onboard.py` warns and falls back to
  `no_account`; double-check `TPLUS_API_BASE_URL` before creating an account.
