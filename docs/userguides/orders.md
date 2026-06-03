# Orders

The {py:class}`tplus.client.OrderBookClient` is an async REST + WebSocket
client targeting the T+ OMS. Once you have a [user](./users.md) and a
running OMS endpoint you can place, replace, cancel, and stream orders.

## Initialising a client

```{code-block} python
import asyncio

from tplus.client import OrderBookClient
from tplus.utils.user import load_user

async def main():
    user = load_user("alice")
    async with OrderBookClient(user, base_url="http://127.0.0.1:8000") as client:
        ...
```

The async-context-manager form ensures HTTP and WebSocket connections are
closed cleanly. Pass `use_ws_control=True` to route create / replace / cancel
calls over a persistent `/control` WebSocket instead of HTTP.

## Markets

Markets are addressed via {py:class}`tplus.model.asset_identifier.AssetIdentifier`.
This is a t+-specific identifier — either a registry index or an
`address@chain_id` string where `chain_id` is the **9-byte t+ form**, *not* a
raw EVM chain id. There is no symbol/ticker form. See
[Asset identifiers](./asset-identifiers.md) for the full breakdown.

```{code-block} python
from tplus.model.asset_identifier import AssetIdentifier, AssetAddress

asset = AssetIdentifier(200)  # by registry index

# An on-chain token on Arbitrum (chain id 42161 → 9-byte hex 00000000000000a4b1).
# Use AssetAddress.from_evm_address to avoid hand-encoding the chain id:
token = AssetAddress.from_evm_address(
    "0x62622E77D1349Face943C6e7D5c01C61465FE1dc",
    chain_id=42161,
)
```

Create or fetch a market (per-asset cache included):

```{code-block} python
await client.create_market(asset)            # idempotent
market = await client.get_market(asset)
print(market.book_price_decimals, market.book_quantity_decimals)
```

## Limit orders

```{code-block} python
from tplus.model.limit_order import GTC, GTD, IOC

resp = await client.create_limit_order(
    asset_id=asset,
    quantity=5,
    price=1_000,
    side="Buy",
    time_in_force=GTC(),  # or IOC(), GTD(expiry_ns=...)
)
print(resp.order_id)
```

`quantity` and `price` are integers in the book's native units -- divide by
`10 ** book_price_decimals` (or `book_quantity_decimals`) to get the decimal
form.

## Market orders

Market orders accept either a base or quote quantity:

```{code-block} python
resp = await client.create_market_order(
    asset_id=asset,
    side="Sell",
    base_quantity=10,             # XOR with quote_quantity
    fill_or_kill=False,
)
```

## Stop-loss / take-profit triggers

`create_limit_order` and `create_market_order` accept an optional
`trigger=...` that defers activation until the book's price crosses
a threshold. `TriggerAbove` fires when the price crosses up through
the level; `TriggerBelow` fires on the way down. Prices are in book
quote-units, same as `price` everywhere else.

```{code-block} python
from tplus.model.order_trigger import OrderTrigger, TriggerAbove, TriggerBelow

# Stop-loss: fire a market sell when price drops below 95.00.
await client.create_market_order(
    asset_id=asset,
    side="Sell",
    base_quantity=10,
    trigger=OrderTrigger(
        parent_order_id=None,
        trigger=TriggerBelow(price=95_00),
    ),
)

# Take-profit limit: rest a sell at 110.00, activated after price
# crosses up through 105.00.
await client.create_limit_order(
    asset_id=asset,
    quantity=10,
    price=110_00,
    side="Sell",
    trigger=OrderTrigger(
        parent_order_id=None,
        trigger=TriggerAbove(price=105_00),
    ),
)
```

## Replace and cancel

```{code-block} python
await client.replace_order(
    original_order_id=resp.order_id,
    asset_id=asset,
    new_quantity=6,
    new_price=1_050,
)

await client.cancel_order(order_id=resp.order_id, asset_id=asset)
```

## Batch creates

```{code-block} python
from tplus.model.batch_order import BatchCreateOrderRequest

# Build CreateOrderRequest objects via prepare_limit_order_request, then:
batch = await client.send_multiple_orders(create_order_requests=[req1, req2, req3])
```

## Reading state

User-scoped state comes from the OMS `OrderBookClient`; public market data
(klines, order-book depth, public trades, tickers) comes from a separate
`MarketDataClient` that talks to the read-only `market-data-service`:

```{code-block} python
from tplus.client import MarketDataClient

md = MarketDataClient("http://127.0.0.1:8011")   # market-data-service URL
snapshot = await md.get_orderbook_snapshot(asset)
klines = await md.get_klines(asset, limit=200)
ticker = await md.get_ticker(asset)

trades = await client.get_user_trades_for_asset(asset)
orders, _ = await client.get_user_orders()
open_orders = await client.get_open_orders_for_book(asset)
inventory = await client.get_user_inventory()
margin = await client.get_user_margin_info(include_positions=True)
solvency = await client.get_user_solvency()
```

If the user has not yet been seen by the OMS, the listing endpoints return
empty results rather than raising.

## Streaming

Order and user-trade streams are on `OrderBookClient`; market-data streams
(depth, klines, public trades) are on `MarketDataClient`:

```{code-block} python
async for event in client.stream_orders():
    ...

async for trade in client.stream_user_trade_events():
    ...

# market data — via MarketDataClient (the market-data-service)
async for trade in md.stream_finalized_trades():
    ...

async for trade_event in md.stream_all_trades():
    ...

async for diff in md.stream_depth(asset):
    ...

async for kline in md.stream_klines(asset):
    ...
```

## Closing positions

Preview an unsigned set of orders that would close every position in a
sub-account:

```{code-block} python
preview = await client.get_close_all_positions_preview(sub_account_index=1)
for order in preview.orders:
    ...
```

## Sub-account transfers

```{code-block} python
await client.request_transfer_to_subaccount(
    source_index=0,
    target_index=1,
    transfer_asset=asset,
    transfer_amount=1_000_000,
)
```

## Errors

OMS errors are raised as subclasses of {py:class}`tplus.exceptions.OmsError`
(itself a subclass of `httpx.HTTPStatusError`). See [Exceptions](./exceptions.md).
