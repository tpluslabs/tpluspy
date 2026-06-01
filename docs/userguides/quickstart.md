# Quickstart

This guide walks through installing `tpluspy`, creating a local user, and
sending your first order to a running T+ stack.

## 1. Install

```{code-block} shell
pip install tpluspy
```

If you also need the on-chain helpers (deposit vault, registry, settlement
signatures), install the `evm` extra:

```{code-block} shell
pip install "tpluspy[evm]"
```

## 2. Create a user

`tpluspy` ships with a small local key manager. Keys are stored as encrypted
Ed25519 keyfiles under `~/.tplus/users/`.

```{code-block} python
from tplus.utils.user import UserManager

manager = UserManager()
user = manager.generate("alice")  # prompts for a password
print(user.public_key)
```

See [Users](./users.md) for the full key-management workflow.

## 3. Connect to the OMS

```{code-block} python
import asyncio

from tplus.client import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.utils.user import load_user


async def main():
    user = load_user("alice")
    asset = AssetIdentifier(200)

    async with OrderBookClient(user, base_url="http://127.0.0.1:8000") as client:
        market = await client.get_market(asset)
        print(market)


asyncio.run(main())
```

## 4. Place an order

See [Orders](./orders.md) for limit, market, replace, cancel, and batch flows.

```{code-block} python
from tplus.model.limit_order import GTC

response = await client.create_limit_order(
    asset_id=asset,
    quantity=5,
    price=1_000,
    side="Sell",
    time_in_force=GTC(),
)
```

## 5. Stream live data

Public market-data streams (depth, klines, public trades) live on
`MarketDataClient`, which talks to the read-only `market-data-service`:

```{code-block} python
from tplus.client import MarketDataClient

async with MarketDataClient("http://127.0.0.1:8011") as md:
    async for diff in md.stream_depth(asset):
        print(diff.sequence_number, len(diff.asks), len(diff.bids))
```

`MarketDataClient` also offers `get_klines` / `get_ticker` / `get_orderbook_snapshot`
and `stream_klines` / `stream_finalized_trades`. Order and user-trade streams
stay on {py:class}`tplus.client.OrderBookClient`.
