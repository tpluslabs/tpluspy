# tpluspy primer — building scripts after onboarding

You (the agent) just onboarded a user. This is the jumping-off point for writing
tpluspy scripts against **their** account. It is a condensed map; the canonical,
always-current reference is `docs/userguides/` in this repo — link the user there
rather than reconstructing behaviour from memory.

## The identity

The user's account is derived from the EVM key in **`TPLUS_PRIVATE_KEY`** (the
single source of truth). The T+ account id is the derived Ed25519 public key.
Re-derive the authenticated `User` at the start of every script — do not persist
the Ed25519 private key:

```python
import hashlib, os
from eth_account import Account
from eth_account.messages import encode_defunct
from tplus.utils.user import User

MASTER_KEY_MESSAGE = (
    "tplus-core: authorize account\n\n"
    "This signature derives your wallet signer key and will never be broadcast to the blockchain."
)

def load_user() -> User:
    evm_pk = os.environ["TPLUS_PRIVATE_KEY"]
    if not evm_pk.startswith("0x"):
        evm_pk = "0x" + evm_pk
    sig = Account.sign_message(encode_defunct(text=MASTER_KEY_MESSAGE), evm_pk).signature
    ed25519_seed = hashlib.sha512(bytes(sig)).digest()[:32]
    return User(private_key="0x" + ed25519_seed.hex())  # .public_key == account id
```

> The `eth_account` call above only reproduces the frontend's wallet-login
> signature **to derive the key**. It is never a T+ request signature. T+
> requests are signed with Ed25519 over compact JSON by `User.sign()` — see the
> "Signing model" section of `claude.md`. Never route T+ requests through
> `eth_account`.

## The clients

```python
from tplus.client import OrderBookClient, MarketDataClient, ClearingEngineClient

BASE_URL = os.environ["TPLUS_API_BASE_URL"]   # the sole T+ URL; others derive from it
HEADERS = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

async with OrderBookClient(base_url=BASE_URL, default_user=load_user(), headers=HEADERS) as client:
    inv = await client.get_user_inventory()
```

- **`OrderBookClient(base_url=…, default_user=…)`** — OMS/orderbook: orders,
  user trades/inventory/positions/margin/solvency, `/market` + `/markets`,
  multisig config, sub-account transfers, and streams. Pass `default_user` (not
  `user`) to the constructor. Per-call `user=` overrides it. Async; use
  `async with` (or call `await client.close()`).
- **`MarketDataClient(base_url=…)`** — public market data (klines, depth, public
  trades, tickers + WS streams). No auth.
- **`ClearingEngineClient(user=…, base_url=…)`** — deposits, withdrawals,
  settlements, vaults, asset registry, decimals. Sub-APIs are cached properties
  (`client.vaults`, `client.assets`, `client.decimals`, …). On-chain pieces need
  `pip install "tpluspy[evm]"`.

## Use the `tplus` CLI (often faster than writing a script)

tpluspy ships a `tplus` CLI. Two gotchas: the `tplus` command only exists after
`pip install -e .` in the package (no install? use `python -m tplus._cli ...`); and
it authenticates from its own local **keystore** (not the EVM key). It honors
`TPLUS_API_BASE_URL` as the single URL (orderbook = that host; market-data derived
by swapping `oms`->`mds`); set a per-service var only to override.

```bash
export TPLUS_API_BASE_URL=https://oms.tplus.cx   # the only URL the CLI needs
# override only if a service is elsewhere: TPLUS_ORDERBOOK_BASE_URL / TPLUS_MARKET_DATA_BASE_URL

# Import the onboarded identity into the CLI keystore (encrypted; key never printed):
python .agents/skills/onboard/scripts/onboard.py --register-cli-account   # keystore account 'onboard'
export TPLUS_ACCOUNT=onboard                                # (or pass --tplus-account onboard)
export TPLUS_PASSWORD=...        # optional: skip the interactive keystore-password prompt
```

Explore the protocol — **no account needed**:

```bash
tplus params list                 # risk parameters (anonymous, orderbook URL)
tplus markets depth <asset_id>    # order-book snapshot     (market-data URL)
tplus markets klines <asset_id>   # candles                 (market-data URL)
tplus stream depth <asset_id>     # live depth stream       (market-data URL)
tplus env                         # what env vars the CLI sees
tplus --help                      # full command tree (markets/orders/trades/accounts/vaults/...)
```

Operate as your account (needs `TPLUS_ACCOUNT` + `TPLUS_API_BASE_URL`):

```bash
tplus markets list                # books, decimals, max leverage, fees
tplus balance                     # your inventory
tplus orders list                 # your orders
tplus orders place --help         # place an order (inspect args first; --side is buy/sell)
tplus orders cancel <order_id> --asset <asset_id>
tplus trades list                 # your fills (no --limit; cap via the SDK)
tplus stream user-trades          # live fills stream
tplus accounts list               # local keystore accounts
```

CLI caveats: `--side` is lowercase (`buy`/`sell`) while the SDK uses `"Buy"`/`"Sell"`;
`tplus trades list` has no `--limit` (use `get_user_trades(limit=…)`); there is **no**
`tplus positions` command — positions are SDK-only (`get_user_positions()`) or in
`onboard.py`'s JSON dump. To find an `asset_id` for any command, run `tplus markets
list` — it includes display symbols from `tplus.asset_metadata` where known, and
the `200` in examples is only a placeholder.

Prefer scripts for anything multi-step or programmatic — re-derive the `User` from
`TPLUS_PRIVATE_KEY` (below) and you skip the keystore entirely.

## Common task → call (verified against source)

| Task | Call |
| --- | --- |
| My inventory | `await client.get_user_inventory()` |
| My margin (with positions) | `await client.get_user_margin_info(include_positions=True)` |
| My solvency | `await client.get_user_solvency()` |
| My positions | `await client.get_user_positions()` |
| All my orders | `orders, raw = await client.get_user_orders()` |
| Open orders for a book | `await client.get_open_orders_for_book(asset_id)` |
| My trades | `await client.get_user_trades(limit=50)` |
| My multisig signers | `await client.get_multisig_config()` |
| Get a market | `await client.get_market(AssetIdentifier(200))` |
| Place a limit order | `await client.create_limit_order(quantity=…, price=…, side="Buy", time_in_force=GTC(), asset_id=…)` |
| Place a market order | `await client.create_market_order(side="Buy", base_quantity=…, asset_id=…)` |
| Cancel / replace | `await client.cancel_order(order_id, asset_id)` / `await client.replace_order(...)` |
| Transfer between sub-accounts | `await client.request_transfer_to_subaccount(source_index, target_index, asset, amount)` |
| Stream my trade events | `async for ev in client.stream_user_trade_events(): ...` |

## A first order, end to end

Quantities and prices are **integers in the book's native units** (decimals come
from `get_market`). Find a real `asset_id` with `tplus markets list`, then:

```python
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.limit_order import GTC

asset = AssetIdentifier("<id from `tplus markets list`>")
await client.get_market(asset)          # inspect book_price_decimals / book_quantity_decimals
resp = await client.create_limit_order(
    quantity=1, price=1, side="Buy", time_in_force=GTC(post_only=True), asset_id=asset,
)
await client.cancel_order(resp.order_id, asset)
```

## Things that bite

- **Asset identifiers are not tickers.** `AssetIdentifier("BTC-PERP")` is invalid.
  Use a registry index (`AssetIdentifier(200)`) or `address@chain_id` with the
  T+ 9-byte chain id (use `AssetAddress.from_evm_address(...)` / `ChainID.evm(...)`).
  For display names only, `tplus.asset_metadata` contains a local risk-params
  snapshot for canonical production indexes and known `address@chain` aliases.
  Read `docs/userguides/asset-identifiers.md`.
- **Quantities & prices are integers in the book's native units.** Convert with
  `tplus.utils.amount` / `tplus.utils.decimals`; decimals come from `get_market`.
- **Time-in-force:** `from tplus.model.limit_order import GTC, GTD, IOC`.
- **Errors:** catch the specific class from `tplus` (`AuthError`, `NotFoundError`,
  `OmsError`, `OrderRejected`, `RateLimitError`, `ServerError`). Many reads return
  empty results for an unknown user rather than raising.
- **Secrets:** `TPLUS_PRIVATE_KEY` stays in `.env` (gitignored). Never print it,
  never commit it, never echo derived private keys. Public keys are fine.

## Where to go next

- Runnable recipes: `examples/rest_usage.py`, `examples/websocket_usage.py`,
  `examples/deposit.py`, `examples/settlement.py`.
- User guides: `docs/userguides/` (quickstart, users, orders, asset-identifiers,
  clearing-engine, withdrawals, contracts, exceptions).
- Full agent guide for this package: `claude.md`.
