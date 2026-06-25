# tpluspy

Python client library for the T+ ecosystem. Provides:

- Async REST + WebSocket clients for `tplus-core`'s order-management system, orderbook, and clearing engine.
- Pydantic v2 models for the t+ wire protocol.
- Ed25519 user-key signing (load/create/manage local keyfiles).
- Optional Ape-based EVM contract layer for on-chain interactions (vaults, registry, deposits, approvals).

The Rust workspace it talks to lives at <https://github.com/tpluslabs/tplus-core> (currently vendored one directory up at `../` while the two trees still cohabit a single repo; eventually `tpluspy` will split into its own repo).

## ⚠ The `[evm]` extras boundary — read this first

`tpluspy` ships in two tiers, and the split matters for **both users and contributors**:

- **Core install (`pip install tpluspy`)** — only the httpx-based REST/WS clients, Pydantic models, and Ed25519 user signing. `ape`, `eth-ape`, `ape-tokens`, `hexbytes` are **not** installed. Anything under `tplus/evm/` and any on-chain / contract code path will fail to import.
- **EVM install (`pip install "tpluspy[evm]"`)** — adds the Ape framework and the typed-message helper deps. Required for: reading or writing t+ contracts (`tplus.evm.contracts`), vault / registry / deposit-vault interactions, anything that needs an Ethereum account.

If the user's task only involves talking to a running `tplus-core` (placing orders, reading inventory, streaming trades, signing requests with their T+ key), the **core install is enough** — don't suggest `[evm]` and don't reach for `ape` imports. If the task touches chain state, require `[evm]`.

When developing the library, treat `tplus/evm/` (and anything that imports `ape`/`hexbytes`) as optional. Never import those at module top-level from non-EVM code paths — guard with local imports inside the EVM-only branches, or keep the dependency contained inside `tplus/evm/`. Adding an unconditional `import ape` to a core module silently breaks every core-install user.

______________________________________________________________________

# For users of the library

This section is what Claude should reach for when a user is **using** `tpluspy` to build something.

## First time here? Run the onboarding skill

If a user has just cloned this repo and wants to get started — connect their
wallet/EVM key to T+, find out whether they already have a T+ account and see
what's in it, or create a new frontend-compatible account — use the onboarding
skill: [`.claude/skills/onboard/SKILL.md`](.claude/skills/onboard/SKILL.md).
Codex CLI discovers the same skill through
[`.agents/skills/onboard`](.agents/skills/onboard); run `/skills` and choose
`onboard`, or type `$onboard onboard me to T+`.

It derives the user's T+ identity from the EVM key in `TPLUS_PRIVATE_KEY` (the
same derivation the T+ frontend does on wallet login), looks it up via
`POST /multisig/signers`, dumps the account state if it exists, and otherwise
generates account-creation scripts.

The flow reads two values from `.env`: `TPLUS_PRIVATE_KEY` (your EVM key) and
`TPLUS_API_BASE_URL` — the T+ OMS base URL. **Production is
`https://oms.tplus.cx`.** This is the *sole* T+ URL; every other T+ service URL
derives from it by host substitution (e.g. market data at `https://mds.tplus.cx`),
so don't introduce per-service base-URL vars.

After onboarding, the agent-facing primer at
[`.claude/skills/onboard/reference/tpluspy-primer.md`](.claude/skills/onboard/reference/tpluspy-primer.md)
is the jumping-off point for building scripts against the account. (The onboarding
key derivation uses `eth_account` personal-sign **only** to reproduce the
frontend's login signature — it is not a T+ request-signing path; see "Signing
model" below.)

## Where the canonical docs live

Before answering anything non-trivial, prefer the user guides in `docs/userguides/` over reconstructing behaviour from memory. They are the source of truth and stay current with the code. Always cite or link the relevant page so users can read more.

| Topic                                                | Read first                                                                     |
| ---------------------------------------------------- | ------------------------------------------------------------------------------ |
| Install + first order                                | [`docs/userguides/quickstart.md`](docs/userguides/quickstart.md)               |
| User keys, signing, sub-accounts                     | [`docs/userguides/users.md`](docs/userguides/users.md)                         |
| **Asset identifiers — index vs. `address@chain_id`** | [`docs/userguides/asset-identifiers.md`](docs/userguides/asset-identifiers.md) |
| Placing / replacing / cancelling / streaming orders  | [`docs/userguides/orders.md`](docs/userguides/orders.md)                       |
| Clearing engine (deposits, settlements, etc.)        | [`docs/userguides/clearing-engine.md`](docs/userguides/clearing-engine.md)     |
| Withdrawals                                          | [`docs/userguides/withdrawals.md`](docs/userguides/withdrawals.md)             |
| EVM contracts (requires `[evm]`)                     | [`docs/userguides/contracts.md`](docs/userguides/contracts.md)                 |
| Exception hierarchy                                  | [`docs/userguides/exceptions.md`](docs/userguides/exceptions.md)               |

API reference pages live in `docs/methoddocs/` (autodoc'd from the source).

## Install

```shell
pip install tpluspy              # core: REST/WS clients + Ed25519 signing only
pip install "tpluspy[evm]"       # adds Ape + hexbytes for on-chain work
```

Pick the core install for pure tplus API work. Pick `[evm]` whenever the task involves t+ contracts, vaults, the asset registry, or deposits/withdrawals that touch chain. Without `[evm]` installed, importing anything from `tplus.evm` will fail with `ModuleNotFoundError` on `ape`.

## The anchor objects

Almost every workflow starts by constructing one of these:

```python
from tplus.utils.user import User, load_user, UserManager
from tplus.client import OrderBookClient, ClearingEngineClient, MarketDataClient
```

- `User` — the signing identity. `User()` mints an ephemeral keypair; `load_user("name")` loads a stored, password-encrypted keyfile; `UserManager` enumerates / saves / sets defaults.
- `OrderBookClient(base_url=..., default_user=...)` — talks to the OMS/orderbook (orders, user trades/inventory/positions/margin, `/market` + `/markets`, order/user-trade streams). The signing identity is `default_user=` (keyword); per-call `user=` overrides it.
- `MarketDataClient(base_url=...)` — read-only client for the `market-data-service` (public market data: klines, order-book depth, public trades, 24h tickers, and their WS streams). No auth. Default base URL `http://localhost:8011`.
- `ClearingEngineClient(base_url=..., default_user=...)` — talks to the CE directly (deposits, withdrawals, settlements, vaults, asset registry, decimals, admin). Sub-APIs are exposed as cached properties: `client.deposits`, `client.withdrawals`, `client.settlements`, `client.vaults`, `client.assets`, `client.decimals`, `client.admin`. There's also `ClearingEngineClient.from_local(user)` for `127.0.0.1:3032`.

Both clients are async; use `async with` to get automatic cleanup:

```python
async with OrderBookClient(base_url="http://127.0.0.1:8000", default_user=user) as client:
    ...
```

## Common task → call

| Task                          | Call                                                                                                           |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Load my stored user           | `user = load_user("alice")` (prompts for password if needed)                                                   |
| Create an ephemeral user      | `user = User()`                                                                                                |
| List stored users             | `UserManager().list()`                                                                                         |
| Get a market                  | `await client.get_market(AssetIdentifier(200))`                                                                |
| Fetch the book                | `await md_client.get_orderbook_snapshot(asset_id)` *(MarketDataClient)*                                         |
| K-lines / 24h ticker          | `await md_client.get_klines(asset_id)` / `await md_client.get_ticker(asset_id)` / `get_tickers()`              |
| Public trades                 | `await md_client.get_trades()` / `get_trades_for_asset(asset_id)`                                              |
| Place a limit order           | `await client.create_limit_order(quantity=5, price=1000, side="Sell", time_in_force=GTC(), asset_id=asset_id)` |
| Place a market order          | `await client.create_market_order(side="Buy", base_quantity=10, asset_id=asset_id)`                            |
| Cancel an order               | `await client.cancel_order(order_id, asset_id)`                                                                |
| Replace an order              | `await client.replace_order(original_order_id, asset_id, new_quantity=..., new_price=...)`                     |
| Batch send                    | `await client.send_multiple_orders([req1, req2, ...])`                                                         |
| My open orders for a book     | `await client.get_open_orders_for_book(asset_id)`                                                              |
| All my orders                 | `orders, raw = await client.get_user_orders()`                                                                 |
| My trades                     | `await client.get_user_trades()` / `get_user_trades_for_asset(asset_id)`                                       |
| My inventory                  | `await client.get_user_inventory()`                                                                            |
| My margin breakdown           | `await client.get_user_margin_info(include_positions=True)`                                                    |
| My solvency                   | `await client.get_user_solvency()`                                                                             |
| Preview "close all positions" | `await client.get_close_all_positions_preview(sub_account_index=1)`                                            |
| Transfer between sub-accounts | `await client.request_transfer_to_subaccount(source_index, target_index, asset, amount)`                       |
| Stream order events           | `async for ev in client.stream_orders(): ...`                                                                  |
| Stream finalized trades       | `async for t in md_client.stream_finalized_trades(): ...` *(MarketDataClient)*                                  |
| Stream depth diffs            | `async for d in md_client.stream_depth(asset_id): ...` *(MarketDataClient)*                                     |
| Stream klines                 | `async for k in md_client.stream_klines(asset_id): ...` *(MarketDataClient)*                                    |
| Stream **my** trade events    | `async for t in client.stream_user_trade_events(): ...`                                                        |
| Deposit (CE)                  | `ClearingEngineClient(...).deposits...` (see `examples/deposit.py`)                                            |
| Withdraw (CE)                 | `ClearingEngineClient(...).withdrawals...`                                                                     |
| Settle (CE)                   | `ClearingEngineClient(...).settlements...` (see `examples/settlement.py`)                                      |

## Asset identifiers

**Read [`docs/userguides/asset-identifiers.md`](docs/userguides/asset-identifiers.md) for the canonical reference, and prefer pointing users there.**

Quick rules so Claude doesn't get this wrong:

- `AssetIdentifier` is a t+-specific format — **not** a ticker/symbol. `AssetIdentifier("BTC-PERP")` does not work. Never invent a symbol form.

- Accepted forms:

  1. **Registry index** — `AssetIdentifier(200)` or `AssetIdentifier("200")`.
  2. **`address@chain_id` string** — where `chain_id` is the **t+ 9-byte chain ID (18 hex chars)**, *not* a raw EVM chain id like `42161`. The format is `<routing_id:1B><vm_id:8B>`. So Arbitrum (`42161` = `0xa4b1`) is `00000000000000a4b1`. Hand-encoding is error-prone — use the helpers below.

  Over JSON the backend sends both forms as plain strings (`"200"` or `"<address>@<chain>"`).

- Helpers (use these):

  ```python
  from tplus.model.asset_identifier import AssetIdentifier, AssetAddress
  from tplus.model.types import ChainID

  AssetIdentifier(200)
  AssetAddress.from_evm_address("0xToken...", chain_id=42161)   # builds the @<9-byte hex> for you
  ChainID.evm(42161)                                            # ChainID('00000000000000a4b1')
  ChainID.from_parts(routing_id=1, vm_id=101)                   # non-EVM routing
  ```

- **Use `AssetAddress` vs. `ChainAddress` by semantic role**, not by typing convenience. They are the same type (`AssetAddress` is a `TypeAlias` for `ChainAddress` re-exported from `tplus.model.asset_identifier`), but the name carries meaning at the call site:

  - `AssetAddress` — anywhere the value is a tradable asset (constructing `AssetIdentifier`, identifying tokens in settlement requests, decimals lookups, etc.).
  - `ChainAddress` — anywhere the value is a non-asset chain-scoped address: registered deposit vaults, the asset registry, the credential manager, MM/settler EOAs. Concrete signals: `ClearingEngineClient.vaults.get()` returns `list[ChainAddress]`; `set_credential_manager_address(...)` takes `ChainAddress`. Don't rename these to `AssetAddress`.

  When in doubt, ask "is this thing tradable?" — yes → `AssetAddress`, no → `ChainAddress`. Apply this in code, docs, and examples consistently.

- Most client methods accept `AssetIdentifier | str` and coerce; the string must still be one of the forms above. Build the identifier once and pass the object through, rather than re-stringifying it on each call.

## Quantities, prices, decimals

All on-the-wire quantities and prices are **integers in the book's native units**. The book's price/quantity decimals come from `Market` (`book_price_decimals`, `book_quantity_decimals`) and `OrderBookClient` caches them per asset. To convert human-readable amounts to book units, use helpers in `tplus.utils.amount` and `tplus.utils.decimals`. Internal inventory values are normalized to 1e18 (`INVENTORY_DECIMALS`).

## Time-in-force

`from tplus.model.limit_order import GTC, GTD, IOC` — pass an instance to `create_limit_order(..., time_in_force=GTC())`.

## Signing model

T+ uses its own **contract-defined signing scheme** across the board: Ed25519 over compact JSON (no spaces, sorted keys), produced by `User.sign()`. Every order, cancel, replace, transfer, approval, and settlement request carries this signature. On-chain payloads use a t+-specific structured-message variant of the same idea, also defined by the t+ contracts. There is no separate "wallet signing" path.

## Ape / EVM extra

**Requires `pip install "tpluspy[evm]"`.** Without that extra, `tplus.evm` is unimportable and the library is effectively "httpx clients for tplus only".

```python
# Requires `pip install "tpluspy[evm]"` and an active Ape network.
from tplus.evm.contracts import vault, registry
registry.getAssets()
```

Use Ape's network chooser, e.g. `ape console --network ethereum:sepolia:alchemy`. Any flow that loads an Ethereum account, reads/writes a vault, or interacts with the asset registry also requires this extra.

## Examples to point users at

`examples/` contains runnable scripts:

- `rest_usage.py` — REST client end-to-end.
- `websocket_usage.py` — multi-stream WS via `asyncio.gather`.
- `deposit.py`, `vaults.py`, `settlement.py`, `decimals.py`, `two_users_trade.py` — focused recipes.

## Errors to catch

```python
from tplus import (
    AuthError, NotFoundError, OmsError, OrderRejected, RateLimitError, ServerError,
)
```

These are re-exported from `tplus.exceptions`. Catch the specific one — many client methods already convert `404` into empty results where that's the natural outcome (e.g. `get_user_orders` returns `([], {})` for an unknown user).

______________________________________________________________________

# For developers of the library

## Layout

- `tplus/client/` — async clients.
  - `base.py` — shared HTTP/WS plumbing (`BaseClient`).
  - `orderbook.py` — `OrderBookClient` (OMS REST + WS: orders, user trades/inventory/positions/margin, `/market` + `/markets`; optional persistent `/control` WS for create/replace/cancel via `use_ws_control=True`).
  - `market_data.py` — `MarketDataClient` (read-only `market-data-service`: klines, order-book depth, public trades, 24h tickers + their WS streams). No auth.
  - `clearingengine/` — `ClearingEngineClient` and its sub-clients (deposits, withdrawals, settlements, vaults, asset registry, decimals, admin).
  - `oms/` — OMS-admin endpoints.
- `tplus/model/` — Pydantic v2 models mirroring the Rust wire types in `../messages/`. When adding a new one, mirror field names, order, and optionality exactly.
- `tplus/utils/` — `signing.py`, `user/` (keyfile manager, Ed25519 model), `amount.py`, `decimals.py`, `domain.py` (t+ structured-message types used by on-chain payloads), order-payload builders (`limit_order.py`, `market_order.py`, `replace_order.py`).
- `tplus/evm/` — Ape integration: contract wrappers, manifests, address helpers. Mypy is intentionally disabled here (`pyproject.toml` overrides).
- `tplus/managers/` — manager base classes used by higher-level orchestration.
- `tplus/_cli/`, `tplus/cli_tools/` — CLI entry points.
- `tests/` — `pytest` suite mirroring the package layout. `tests/integration/` hits live services.
- `docs/` — Sphinx + MyST. Build via `cd docs && make html`; live preview via `make livehtml`.

## Dev workflow

```shell
uv pip install -e ".[test,lint,evm,docs]"
ruff check tplus tests
ruff format --check tplus tests
mypy tplus
pytest
```

The user runs tests; **don't invoke `pytest` from agent sessions** unless explicitly asked.

## Conventions

- **Python 3.10+**.
- **Pydantic v2** — `model_config`, `model_validate`, `model_dump`. No v1 idioms.
- **Async-first** for client code: `httpx.AsyncClient`, `websockets`. Don't add sync wrappers unless asked.
- **Ruff** config in `pyproject.toml`: `line-length = 100`, double quotes, Google-style docstrings. Many `B/SIM/C/RET/TC` rules are intentionally off — don't reintroduce them.
- **Imports**: `tplus` is first-party for isort.
- **Errors**: raise the specific exception from `tplus.exceptions`. Don't swallow into generic `Exception`.
- **`evm` extra is optional and load-bearing** — `ape`, `eth-ape`, `ape-tokens`, `hexbytes` are **not** installed for core users. Never import them at module top-level outside `tplus/evm/`. If a non-EVM module needs to *optionally* invoke EVM code, do a local import inside the function and either let the `ImportError` propagate with a clear message, or surface a check that tells the caller to `pip install "tpluspy[evm]"`. Adding an unconditional EVM import to `tplus/client/`, `tplus/model/`, or `tplus/utils/` silently breaks the core install.
- **Naming**: prefer `err` over `e` in `except` clauses.

## Style

- Terse over verbose. Don't add docstrings that just echo the signature, and don't add comments that restate the code.
- Prefer single-line signatures where possible.
- Prefer editing existing files; the structure is settled.
- A blank line above `return` only when the previous line is at deeper indentation (block-exit cue).

## When adding a wire-protocol model

1. Find the Rust counterpart in [`tplus-core`](https://github.com/tpluslabs/tplus-core) — `messages/` for the wire types, or the producing crate under `bin/` / `lib/`. While the trees still cohabit, this is `../messages/` etc.
2. Mirror field names (snake_case both sides), order, optionality, and tagging exactly.
3. Add a `parse_*` helper in the same file if upstream code parses lists/streams of it.
4. If it appears in a stream, wire it into the matching `stream_*` method — on `OrderBookClient` for OMS streams (orders, user trades), or on `MarketDataClient` for `market-data-service` streams (depth, klines, public trades).

## Don't

- Don't reach for generic Ethereum typed-data tooling (`eth_account.sign_typed_data`, etc.) for t+ flows. T+ defines its own contract-level signing scheme — Ed25519 over compact JSON for off-chain requests and a t+-specific structured-message variant for on-chain payloads. Use `User.sign()` and the helpers in `tplus.utils.signing` / `tplus.utils.domain`.
- Don't break the optional-extra boundary by importing EVM deps at module top-level outside `tplus/evm/`.
- Don't run tests in agent sessions; the user runs them.
