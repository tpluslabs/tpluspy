# Withdrawals

Withdrawals route through the clearing engine: Funding tokens are locked, the CE
collects threshold signatures, and you (or any caller) replay those
signatures to the on-chain deposit vault.

## Amount units

Two different units are in play. The CE request carries the amount in
CE-internal 1e18 units, but the CE converts it to the asset's native chain
decimals (rounding down) before signing the vault approval. The on-chain
`vault.withdraw(...)` call must use that converted value or the digest will not
match and the transaction reverts with `InvalidSignature()`.

Each approval carries that signed chain amount as `amount`, and
{py:class}`tplus.evm.managers.withdraw.WithdrawalManager` `execute_withdrawal()` uses
it. `WithdrawalInfo.amount` is the 1e18 request amount. Pass a
{py:class}`tplus.utils.amount.Amount` to `init_withdrawal()` to give the amount
in native decimals; a plain `int` is read as 1e18 units.

`max_fee=` bounds the rebalancing fee the withdrawal may reserve, in 1e18 units
of the asset, and is signed with the request. The CE refuses a request quoted
above it with nothing locked, and fails the withdrawal, returning the locked
amount and the held fee, if the approval at its checkpoint prices above it.
Left `None`, the request accepts whatever the protocol reserves; `0` admits only
a fee-free approval.

## 1. Initialize

Build a {py:class}`tplus.model.withdrawal.WithdrawalRequest` and submit it
through the OMS-facing {py:class}`tplus.client.withdrawal.WithdrawalClient`:

```{code-block} python
from tplus.client import ClearingEngineClient, OrderBookClient, WithdrawalClient
from tplus.model.withdrawal import WithdrawalRequest
from tplus.utils.user import load_user

user = load_user("alice")
withdrawals = WithdrawalClient(default_user=user, base_url="http://127.0.0.1:8000")
oms = OrderBookClient(default_user=user, base_url="http://127.0.0.1:8000")
ce = ClearingEngineClient.from_local(user)

request = WithdrawalRequest(...)  # see the model for required fields
await withdrawals.init_withdrawal(request)
```

Once accepted, the request locks concrete tokens on Funding (account 0).
There is no chain-withdrawal delay or cancel operation. If the balance is on
account 1, first use `OrderBookClient.request_transfer(1, 0,
token_identifier, amount)` and wait for its actual token credit. Nonzero trading
custody for that token must cover the entire amount; otherwise the request is
refused. Only zero custody selects canonical redemption, whose gross debit
includes the fee.
A queued transfer response is acceptance, not completion.

## 2. Signature delivery and status

`WithdrawalManager.init_withdrawal(..., then_execute=True)` subscribes before
initialization, waits for a successful acknowledgement, and uses signature
hints plus status reads to claim. The manager also resynchronizes after a
reconnect. It uses the native amount carried by the approval.

For a manual recovery read:

```{code-block} python
rows = await withdrawals.get_withdrawal_status(user.public_key)
for row in rows:
    print(row)  # awaiting_signature or approved, grouped by signed payload
```

A timeout after submission is ambiguous. Inspect status before submitting
another request. A successful subscription frame must have nonempty channels
and no errors; a rejected frame does not authorize initialization.

## 3. Cancel a transfer remainder

```{code-block} python
from tplus.model.withdrawal import CancelTransferRequest

request = CancelTransferRequest.create_signed(
    signer=user, source=1, token=token_address, nonce=transfer_nonce,
)
await oms.cancel_transfer(request)
```

`await oms.get_queued_transfers(user.public_key)` reads delayed/fillable transfer intents.
Cancellation retains prior fills and ends only the unfilled remainder. Transfers
do not expire. Chain withdrawal approval expiry instead requires an on-chain
non-execution check before token locks are released.

## On-chain replay (EVM)

With the `evm` extra installed you can replay the approvals against the
deposit vault directly. See [Contracts](./contracts.md) for a full example
of `vault.withdraw(...)`.
