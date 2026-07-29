# Withdrawals

Withdrawals route through the clearing engine: you queue an intent, the CE
collects threshold signatures, and you (or any caller) replays those
signatures to the on-chain deposit vault.

## Amount units

Two different units are in play. The CE request carries the amount in
CE-internal 1e18 units, but the CE converts it to the asset's native chain
decimals (rounding down) before signing the vault approval. The on-chain
`vault.withdraw(...)` call must use that converted value or the digest will not
match and the transaction reverts with `InvalidSignature()`.

{py:class}`tplus.evm.managers.withdraw.WithdrawalManager` keeps both:
`WithdrawalInfo.amount` is the 1e18 request amount and
`WithdrawalInfo.chain_amount` is the native-decimals amount the approval covers.
`execute_withdrawal()` uses `chain_amount`. Pass a
{py:class}`tplus.utils.amount.Amount` to `init_withdrawal()` to give the amount
in native decimals; a plain `int` is read as 1e18 units and the asset's decimals
are looked up from the registry.

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
