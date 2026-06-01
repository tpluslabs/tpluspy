# Withdrawals

Withdrawals route through the clearing engine: you queue an intent, the CE
collects threshold signatures, and you (or any caller) replays those
signatures to the on-chain deposit vault.

## 1. Initialize

Build a {py:class}`tplus.model.withdrawal.WithdrawalRequest` and submit it
through the OMS-facing {py:class}`tplus.client.withdrawal.WithdrawalClient`:

```{code-block} python
from tplus.client import ClearingEngineClient, WithdrawalClient
from tplus.model.withdrawal import WithdrawalRequest
from tplus.utils.user import load_user

user = load_user("alice")
withdrawals = WithdrawalClient(user, base_url="http://127.0.0.1:8000")
ce = ClearingEngineClient.from_local(user)

request = WithdrawalRequest(...)  # see the model for required fields
await withdrawals.init_withdrawal(request)
```

Once accepted, the request is held in the CE's withdrawal queue subject to
any configured delay parameters.

## 2. Inspect the queue

```{code-block} python
queued = await withdrawals.get_queued_withdrawals(user.public_key)
for w in queued:
    print(w)
```

## 3. Fetch signatures

When the queue entry is ready, retrieve the threshold of CE signatures:

```{code-block} python
approvals = await withdrawals.get_withdrawal_signatures(user.public_key)
```

Each approval contains a signature, nonce, and expiry suitable for replaying
on-chain.

## 4. Cancel a queued withdrawal

```{code-block} python
from tplus.model.withdrawal import CancelWithdrawalRequest

await withdrawals.cancel_withdrawal(CancelWithdrawalRequest(...))
```

## On-chain replay (EVM)

With the `evm` extra installed you can replay the approvals against the
deposit vault directly. See [Contracts](./contracts.md) for a full example
of `vault.withdraw(...)`.
