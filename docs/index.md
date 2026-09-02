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
- An optional EVM extra wrapping the on-chain T+ contracts — on [web3.py](https://web3py.readthedocs.io/) (`tpluspy[evm]`) or [Ape](https://docs.apeworx.io/ape) (`tpluspy[evm-ape]`).

## Install

```{code-block} shell
pip install tpluspy
```

To use the contract helpers, install an EVM extra (see the [Contracts guide](userguides/contracts.md)):

```{code-block} shell
pip install "tpluspy[evm]"        # web3.py backend
pip install "tpluspy[evm-ape]"    # adds the Ape backend
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
userguides/cli
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
methoddocs/cli
methoddocs/exceptions
```
