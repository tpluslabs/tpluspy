# Clearing Engine

The {py:class}`tplus.client.ClearingEngineClient` talks directly to a clearing
engine ("CE") instance. Most CE endpoints are permission-less, but
settlement and withdrawal flows require a signed payload.

## Connecting

```{code-block} python
from tplus.client import ClearingEngineClient
from tplus.utils.user import load_user

user = load_user("alice")
ce = ClearingEngineClient(user, base_url="http://127.0.0.1:3032")

# Or, for a local development instance running on the default port:
ce = ClearingEngineClient.from_local(user)
```

The CE client groups its API into sub-clients exposed as cached properties:

| Property         | Wraps                                                                     | Purpose                                                                  |
| ---------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `ce.settlements` | {py:class}`tplus.client.clearingengine.settlement.SettlementClient`       | Atomic + batch settlement init, signature retrieval, approval streaming. |
| `ce.deposits`    | {py:class}`tplus.client.clearingengine.deposit.DepositClient`             | Triggering deposit-vault rescans.                                        |
| `ce.withdrawals` | {py:class}`tplus.client.clearingengine.withdrawal.WithdrawalClient`       | Cancel / queue / signatures.                                             |
| `ce.assets`      | {py:class}`tplus.client.clearingengine.assetregistry.AssetRegistryClient` | Asset registry queries.                                                  |
| `ce.decimals`    | {py:class}`tplus.client.clearingengine.decimal.DecimalClient`             | Decimal normalization helpers.                                           |
| `ce.vaults`      | {py:class}`tplus.client.clearingengine.vault.VaultClient`                 | Vault registration + balance refresh.                                    |
| `ce.admin`       | {py:class}`tplus.client.clearingengine.admin.AdminClient`                 | Admin/test-only endpoints.                                               |

## Deposits

The CE ingests deposit-vault events via subscriptions, so a deposit shows up in
your inventory automatically once the on-chain transaction is mined — no client
action is required.

## Withdrawals

The withdrawal flow has two phases: initiation and signature retrieval.

```{code-block} python
from tplus.client import WithdrawalClient
from tplus.model.withdrawal import WithdrawalRequest

withdrawals = WithdrawalClient(user, base_url="http://127.0.0.1:8000")
request = WithdrawalRequest(...)               # build/sign as appropriate
await withdrawals.init_withdrawal(request)

# Later, fetch approving signatures
approvals = await withdrawals.get_withdrawal_signatures(user.public_key)
```

You can also list a user's queued withdrawals or cancel one through OMS:

```{code-block} python
queued = await withdrawals.get_queued_withdrawals(user.public_key)
await withdrawals.cancel_withdrawal(cancel_request)
```

See [Withdrawals](./withdrawals.md) for the end-to-end story.

## Settlements

Atomic / single-tx settlements:

```{code-block} python
from tplus.model.settlement import TxSettlementRequest

await ce.settlements.init_settlement(TxSettlementRequest(...))
sigs = await ce.settlements.get_signatures(user.public_key)
```

Batch settlements:

```{code-block} python
from tplus.model.settlement import BatchSettlementRequest

await ce.settlements.init_batch_settlement(BatchSettlementRequest(...))
```

You can also stream encrypted settlement approvals via WebSocket:

```{code-block} python
async for approval in ce.settlements.stream_approvals(user.public_key):
    # approval["encrypted_data"] needs decryption with the user's Ed25519 key
    ...
```

## Vaults

```{code-block} python
chain_addresses = await ce.vaults.get()
await ce.vaults.update()                    # re-read the registry
await ce.vaults.update_balance(asset_addr)  # nudge the CE to refresh balance
```

## Admin

The admin sub-client wraps test-only endpoints used by the e2e harness --
e.g. modifying a user's inventory, setting risk parameters, injecting
oracle prices, or designating a market-maker. These endpoints are gated
behind the `debug-admin-endpoint` feature flag in the CE.
