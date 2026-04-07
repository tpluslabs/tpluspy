"""Structured exception hierarchy for OMS API errors.

The OMS returns errors in a standardised envelope::

    {
        "error": {
            "code": "INSUFFICIENT_MARGIN",
            "message": "Insufficient margin for order",
            "details": {"order_id": "abc123"},
            "retryable": false
        }
    }

Each exception carries the parsed fields so callers can branch on ``code``,
inspect ``details``, or check ``retryable`` without parsing JSON themselves.
"""

from __future__ import annotations


class OmsError(Exception):
    """Base class for OMS API errors with structured error response."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        details: dict | None = None,
        retryable: bool | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        self.retryable = retryable
        super().__init__(f"[{code}] {message}")


class OrderRejected(OmsError):
    """Order was rejected (create/replace/cancel)."""

    @property
    def order_id(self) -> str | None:
        return self.details.get("order_id") if self.details else None


class AuthError(OmsError):
    """Authentication/authorization failure."""

    pass


class RateLimitError(OmsError):
    """Rate limit exceeded."""

    pass


class NotFoundError(OmsError):
    """Resource not found."""

    pass


class ServerError(OmsError):
    """Server-side error (5xx)."""

    pass


# ---------------------------------------------------------------------------
# Code -> exception class mapping
# ---------------------------------------------------------------------------

# Prefixes / exact codes that map to each subclass.  Checked in order;
# first match wins.
_AUTH_CODES = frozenset({
    "UNAUTHORIZED",
    "INVALID_SIGNATURE",
})
_AUTH_PREFIXES = ("SIGNER_", "NONCE_")

_RATE_LIMIT_CODES = frozenset({"RATE_LIMITED"})

_NOT_FOUND_SUFFIXES = ("_NOT_FOUND",)

_SERVER_CODES = frozenset({
    "INTERNAL_ERROR",
    "CE_COMMUNICATION_ERROR",
    "TIMEOUT",
})

_ORDER_PREFIXES = (
    "INSUFFICIENT_MARGIN",
    "INVALID_ORDER",
    "ORDER_REJECTED",
    "DUPLICATE_ORDER",
    "SELF_TRADE",
    "REDUCE_ONLY",
    "POST_ONLY",
    "FOK_",
    "IOC_",
)


def _classify(code: str, status_code: int) -> type[OmsError]:
    """Return the most specific ``OmsError`` subclass for *code*."""
    if code in _AUTH_CODES or any(code.startswith(p) for p in _AUTH_PREFIXES):
        return AuthError
    if code in _RATE_LIMIT_CODES:
        return RateLimitError
    if any(code.endswith(s) for s in _NOT_FOUND_SUFFIXES):
        return NotFoundError
    if code in _SERVER_CODES:
        return ServerError
    if any(code.startswith(p) for p in _ORDER_PREFIXES):
        return OrderRejected
    # Fall back based on HTTP status code ranges
    if 500 <= status_code <= 599:
        return ServerError
    if status_code == 429:
        return RateLimitError
    if status_code in {401, 403}:
        return AuthError
    if status_code == 404:
        return NotFoundError
    # Default
    return OmsError


def from_error_body(
    body: dict,
    status_code: int,
) -> OmsError:
    """Build an ``OmsError`` (or subclass) from a parsed error envelope.

    *body* is the **inner** ``error`` dict (i.e. ``response_json["error"]``).
    """
    code = body.get("code", "UNKNOWN")
    message = body.get("message", "")
    details = body.get("details")
    retryable = body.get("retryable")

    cls = _classify(code, status_code)
    return cls(
        code=code,
        message=message,
        status_code=status_code,
        details=details,
        retryable=retryable,
    )
