---
myst:
  html_meta:
    description lang=en: Python client utilities for the T+ leverage trading protocol.
---

# tpluspy

`tpluspy` is the Python client library for the [T+ protocol](https://github.com/tpluslabs).
It bundles:

- An async REST + WebSocket client for the order book / OMS (`tplus.client.OrderBookClient`).
- An async client for the clearing engine (`tplus.client.ClearingEngineClient`).
- A local user-key manager backed by encrypted keyfiles (`tplus.utils.user`).
- An optional EVM extra (`tpluspy[evm]`) wrapping the on-chain T+ contracts via [Ape](https://docs.apeworx.io/ape).

## Install

```{code-block} shell
pip install tpluspy
```

To use the contract helpers, install the `evm` extra:

```{code-block} shell
pip install "tpluspy[evm]"
```

## At a glance

```{code-block} python
import asyncio

from tplus.client import MarketDataClient, OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.utils.user import load_user


async def main():
    user = load_user()  # uses your default ~/.tplus/users key
    asset = AssetIdentifier(200)

    async with (
        OrderBookClient(user, base_url="http://127.0.0.1:8000") as client,
        MarketDataClient("http://127.0.0.1:8011") as md,
    ):
        snapshot = await md.get_orderbook_snapshot(asset)   # public market data: market-data-service
        print(snapshot.sequence_number)
        orders, _ = await client.get_user_orders()          # user state: OMS
        print(len(orders))


asyncio.run(main())
```

## User Guides

```{toctree}
:maxdepth: 1
:caption: User Guides

userguides/quickstart
userguides/users
userguides/asset-identifiers
userguides/orders
userguides/clearing-engine
userguides/withdrawals
userguides/contracts
userguides/exceptions
```

## API Reference

```{toctree}
:maxdepth: 1
:caption: API Reference

methoddocs/client
methoddocs/clearingengine
methoddocs/user
methoddocs/model
methoddocs/evm
methoddocs/exceptions
```
