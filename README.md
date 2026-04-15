# TPlus Python Client Utilities

Python clients for interacting with tplus.

## Install

To install, use either `pip` or `uv pip`:

```shell
uv pip install -e .
```

## CLI

`tpluspy` installs a `tplus` command for interacting with T+ services from the shell.

### Global options

| Flag / Env | Purpose |
| --- | --- |
| `--account` / `TPLUS_ACCOUNT` | Default local account alias (used by signing/OMS/settle commands). |
| `--orderbook-base-url` / `TPLUS_ORDERBOOK_BASE_URL` | Orderbook service base URL. |
| `--clearing-base-url` / `TPLUS_CLEARING_BASE_URL` | Clearing engine base URL. |

Run `tplus --help` to see the top-level command list.

### `tplus accounts`

Manage local Ed25519 accounts stored under `~/.tplus/users`.

```shell
# Import a private key (prompts for the key if --private-key is omitted).
tplus accounts add alice --private-key <hex>

# Generate a fresh key instead.
tplus accounts add alice --generate

# List and inspect accounts.
tplus accounts list
tplus accounts show alice
```

### `tplus sign`

Sign a payload with a local account:

```shell
tplus sign --account alice -m "hello"
echo "hello" | tplus sign --account alice
```

### `tplus markets`

```shell
tplus markets create <asset_id>
tplus markets get <asset_id>
tplus markets list
tplus markets depth <asset_id>
tplus markets klines <asset_id> [--page N] [--limit N] [--end-timestamp-ns N]
```

### `tplus orders`

```shell
tplus orders place --asset <asset_id> --side buy --type limit --quantity 10 --price 1000
tplus orders place --asset <asset_id> --side sell --type market --quantity 5
tplus orders cancel <order_id> --asset <asset_id>
tplus orders replace <order_id> --asset <asset_id> --price 1050 --quantity 6
tplus orders list [--asset <asset_id>] [--open-only]
tplus orders transfer --source N --target N --asset <asset_id> --amount N
tplus orders close --account N --asset <asset_id>
```

### `tplus balance`

```shell
tplus balance [--asset-id <asset_id>]
```

### `tplus trades`

```shell
tplus trades list [--asset <asset_id>]
```

### `tplus decimals`

```shell
tplus decimals get <address> [<address> ...]
tplus decimals update <address> [<address> ...]
```

### `tplus stream`

WebSocket streams; Ctrl-C to stop.

```shell
tplus stream orders
tplus stream trades
tplus stream depth <asset_id>
tplus stream klines <asset_id>
tplus stream user-trades [--user <pubkey>]
```

### `tplus withdraw` (alias: `tplus wd`) *(requires `[evm]` extras)*

Mirrors `tplus settle`: `init` signs + submits the CE request, `execute`
additionally polls for the CE approval and submits the on-chain `withdraw`.
Both use Ape's `--network` / `--account` for the on-chain signer.

```shell
# CE-only.
tplus withdraw init --network <ape-network> --account <ape-alias> \
  --asset 0x...@42161 --amount 1000000 [--nonce N] [--target <addr>]

# CE init + on-chain withdraw once approved.
tplus withdraw execute --network <ape-network> --account <ape-alias> \
  --asset 0x...@42161 --amount 1000000 \
  [--nonce N] [--target <addr>] [--poll-interval 2] [--poll-timeout 60]

tplus wd cancel --asset 0x... --nonce N
tplus wd list [--user <pubkey>]
tplus wd signatures [--user <pubkey>]
```

### `tplus assets` *(requires `[evm]` extras)*

Registry-owner operations. Uses Ape's `--network` / `--account`.

```shell
# List assets. Defaults to reading from the Registry contract.
tplus assets list [--network ethereum:sepolia:alchemy]

# Query the clearing engine instead:
tplus assets list --ce

tplus assets set <index> <asset_address> \
  --chain-id 42161 --max-deposit 1000000 --max-1hr 100000 --min-weight 1 \
  [--no-wait]

tplus assets set-risk <index> --params '{...}'
tplus assets apply-risk <index>
```

### `tplus vault` *(requires `[evm]` extras)*

Vault-owner operations. Uses Ape's `--network` / `--account`.

```shell
tplus vault set-domain-separator [--separator <hex>]
tplus vault set-administrators [--admin-key <hex> ...] [--quorum N]
tplus vault register-settler <alias-or-pubkey> --executor <addr> [--wait]
tplus vault register-depositor <addr>
```

### `tplus deposit` *(requires `[evm]` extras)*

Deposit tokens into the vault.

```shell
tplus deposit <token> --amount 1000000000000000000 [--wait]
```

### `tplus settle`

Requires the `[evm]` extras (ape + EIP-712 deps). Commands accept Ape's
`--network` / `--account` options for the on-chain signer.

```shell
# Initialize a settlement on the clearing engine only.
tplus settle init \
  --network arbitrum:mainnet:alchemy --account my-ape-alias \
  --asset-in  <32-byte hex> --amount-in  1000000000000000000 --amount-in-decimals 18 \
  --asset-out <32-byte hex> --amount-out 500000               --amount-out-decimals 6

# Initialize and then execute the settlement on-chain once the CE approves.
tplus settle execute \
  --network arbitrum:mainnet:alchemy --account my-ape-alias \
  --asset-in  <32-byte hex> --amount-in  1000000000000000000 --amount-in-decimals 18 \
  --asset-out <32-byte hex> --amount-out 500000               --amount-out-decimals 6
```

## Usage Example

### REST and WebSocket Client (`tplus.client`)

The `tpluspy` library also provides an asynchronous client (`OrderBookClient`) for interacting with the `tplus-core` REST API and WebSocket streams.

#### Initialization

To use the client, first initialize it with a `User` object (for signing requests) and the base URL of your `tplus-core` instance:

```python
import asyncio
from tplus.client import OrderBookClient
from tplus.utils.user import User

API_BASE_URL = "http://127.0.0.1:8000"  # Replace with your API URL
user = User()

async def run_client():
    # Use async context manager for automatic cleanup
    async with OrderBookClient(user=user, base_url=API_BASE_URL) as client:
        print("Client initialized.")
        # ... use client methods ...

asyncio.run(run_client())
```

#### REST API Usage

The client offers async methods for common REST endpoints:

**Fetching Data:**

```python
# Get Order Book Snapshot for asset index 200
from tplus.model.asset_identifier import AssetIdentifier

example_asset = AssetIdentifier(Index=200)
orderbook = await client.get_orderbook_snapshot(example_asset)
print(f"Snapshot Sequence: {orderbook.sequence_number}")

# Get Klines for an asset
klines = await client.get_klines(example_asset)
print(f"Klines: {klines}")

# Get Market Details for an asset
market_details = await client.get_market(example_asset)
print(f"Market Details: Price Decimals={market_details.book_price_decimals}, Quantity Decimals={market_details.book_quantity_decimals}")

# Get orders for the user
user_orders, _ = await client.get_user_orders()
print(f"User Orders: {user_orders}")

# Get trades for the user and asset
user_asset_trades = await client.get_user_trades_for_asset(example_asset)
print(f"User Asset Trades: {user_asset_trades}")

# Get user inventory
inventory = await client.get_user_inventory()
print(f"Inventory: {inventory}")
```

**Creating Orders:**

```python
# Ensure example_asset is defined (e.g., from "Fetching Data" section)
from tplus.model.asset_identifier import AssetIdentifier
example_asset = AssetIdentifier(200)

# Create a Market for an asset (idempotent)
market_creation_response = await client.create_market(asset_id=example_asset)
print(f"Market Creation Response: {market_creation_response}")

# Create a Market Order for a specific asset
market_response = await client.create_market_order(
    asset_id=example_asset,
    quantity=10,  # integer quantity
    side="Buy",
    fill_or_kill=False,
)
print(f"Market Order Response: {market_response}")

# Create a Limit Order for a specific asset
# Good-Till-Cancelled limit order
from tplus.model.limit_order import GTC
limit_response = await client.create_limit_order(
    asset_id=example_asset,
    quantity=5,
    price=1_000,
    side="Sell",
    time_in_force=GTC(),
)
print(f"Limit Order Response: {limit_response}")

# Cancel an Order
# Order ID should be obtained from an order creation response.
order_id_to_cancel = "actual-order-id-from-api"  # Replace with a real order ID
cancel_response = await client.cancel_order(
    order_id=order_id_to_cancel,
    asset_id=example_asset
)
print(f"Cancel Order Response: {cancel_response}")

# Replace an Order
# Original Order ID should be from an existing, open order.
original_order_id_to_replace = "actual-original-order-id"  # Replace with a real order ID
replace_response = await client.replace_order(
    original_order_id=original_order_id_to_replace,
    asset_id=example_asset,
    new_quantity=6, # Optional: New integer quantity
    new_price=1050   # Optional: New integer price
)
print(f"Replace Order Response: {replace_response}")
```

See `examples/rest_usage.py` for a runnable demonstration.

#### WebSocket Streaming

The client provides async iterators to stream real-time data:

```python
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.orderbook import OrderBookDiff
from tplus.model.trades import Trade

example_asset = AssetIdentifier(200)

# Stream Order Book Diffs
async for diff_update in client.stream_depth(example_asset):
    if isinstance(diff_update, OrderBookDiff):
        print(f"[Depth] Seq={diff_update.sequence_number}, Asks={len(diff_update.asks)}, Bids={len(diff_update.bids)}")
    # Add logic to handle the update, e.g., update a local order book

# Stream Finalized Trades
async for trade in client.stream_finalized_trades():
     if isinstance(trade, Trade):
        print(f"[Trade] ID: {trade.trade_id}, Price: {trade.price}, Qty: {trade.quantity}")
    # Add logic to handle the trade

# Other available streams:
# client.stream_orders() -> OrderEvent
# client.stream_all_trades() -> TradeEvent
# client.stream_klines(asset_id) -> KlineUpdate
```

See `examples/websocket_usage.py` for a runnable demonstration using `asyncio.gather` to run multiple streams concurrently.

### Contracts

To interact with the contracts or sign T+ specific EIP-712 messages, ensure you have installed the `evm` extra:

```shell
pip install tpluspy[evm]
```

Use the `tplusp.contracts` module to read data from t+ contracts.
For example, launch a Sepolia-connected Ape console:

```shell
ape console --network ethereum:sepolia:alchemy
```

**Note**: You can use any provider you want or a RPC directly, it doesn't have to be Alchemy.

Then, once in the console, you will already have access to contracts that you can call methods on:

```python
In [1]: registry.getAssets()
Out[1]: [getAssets_return(assetAddress=HexBytes('0x000000000000000000000000f08a50178dfcde18524640ea6618a1f965821715'), chainId=11155111, maxDeposits=100)]
In [2]: registry.admin()
Out[2]: '0x467a95fC5359edE5d5dDc4f10A1F4B680694858E'
```

#### EIP-712

Sign EIP-712 messages, such as settlements, using the `eip712` library.

```python
from ape import accounts, convert, chain
from tplus.utils.domain import Order
from tplus.evm.contracts import vault
from tplus.utils.user import UserManager

# Load your Ethereum account for t+.
tplus_user = accounts.load("tplus-account")

# Load your t+ user (public key).
user_id = UserManager.load("my_user").public_key

# Get the nonce from t+ or the contracts directly.
nonce = vault.getDepositNonce(tplus_user)

order = Order(
    tokenOut="0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
    amountOut=convert("1 ether", int),
    tokenIn="0x58372ab62269A52fA636aD7F200d93999595DCAF",
    amountIn=convert("1 ether", int),
    userId=user_id,
    nonce=nonce,
    validUntil=chain.pending_timestamp,
)

# Use this signature for the settlement.
signature = tplus_user.sign_message(order).encode_rsv()
print(signature)
```
