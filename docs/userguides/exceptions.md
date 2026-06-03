# Exceptions

OMS errors arrive in a structured envelope:

```{code-block} json
{
    "error": {
        "code": "INSUFFICIENT_MARGIN",
        "message": "Insufficient margin for order",
        "details": {"order_id": "abc123"},
        "retryable": false
    }
}
```

`tpluspy` parses the envelope and raises the most specific subclass of
{py:class}`tplus.exceptions.OmsError`. Every subclass is also an
`httpx.HTTPStatusError`, so existing `except httpx.HTTPStatusError` blocks
keep working.

## Hierarchy

| Exception                                   | Description                                                                                                |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| {py:class}`tplus.exceptions.OmsError`       | Base class. Carries `code`, `message`, `status_code`, `details`, `retryable`.                              |
| {py:class}`tplus.exceptions.OrderRejected`  | Order create / replace / cancel rejected (insufficient margin, post-only violation, FOK/IOC failure, ...). |
| {py:class}`tplus.exceptions.AuthError`      | Auth / signature / nonce errors.                                                                           |
| {py:class}`tplus.exceptions.RateLimitError` | Rate limit exceeded (HTTP 429 or `RATE_LIMITED`).                                                          |
| {py:class}`tplus.exceptions.NotFoundError`  | Resource not found (HTTP 404 or `*_NOT_FOUND`).                                                            |
| {py:class}`tplus.exceptions.ServerError`    | 5xx / `INTERNAL_ERROR` / `CE_COMMUNICATION_ERROR` / `TIMEOUT`.                                             |

## Branching on error code

```{code-block} python
from tplus.exceptions import OrderRejected, RateLimitError

try:
    await client.create_limit_order(...)
except OrderRejected as err:
    if err.code == "INSUFFICIENT_MARGIN":
        ...
    elif err.code.startswith("POST_ONLY"):
        ...
except RateLimitError as err:
    if err.retryable:
        await asyncio.sleep(1)
```

`OrderRejected` exposes a convenience `order_id` property pulled from
`details`.

## Mapping rules

The classification rules live in {py:func}`tplus.exceptions._classify` and
are summarised below:

- `UNAUTHORIZED`, `INVALID_SIGNATURE`, `SIGNER_*`, `NONCE_*` → `AuthError`.
- `RATE_LIMITED` → `RateLimitError`.
- `*_NOT_FOUND` → `NotFoundError`.
- `INTERNAL_ERROR`, `CE_COMMUNICATION_ERROR`, `TIMEOUT` → `ServerError`.
- `INSUFFICIENT_MARGIN`, `INVALID_ORDER`, `ORDER_REJECTED`, `DUPLICATE_ORDER`, `SELF_TRADE`, `REDUCE_ONLY`, `POST_ONLY`, `FOK_*`, `IOC_*` → `OrderRejected`.
- Otherwise, the HTTP status falls through: 5xx → `ServerError`,
  429 → `RateLimitError`, 401/403 → `AuthError`, 404 →
  `NotFoundError`, anything else → `OmsError`.
