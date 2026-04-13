"""Tests for the structured OMS error handling."""

import json

import httpx
import pytest

from tplus.exceptions import (
    AuthError,
    NotFoundError,
    OmsError,
    OrderRejected,
    RateLimitError,
    ServerError,
    from_error_body,
)

# ---------------------------------------------------------------------------
# from_error_body classification tests
# ---------------------------------------------------------------------------


class TestFromErrorBody:
    def test_insufficient_margin(self):
        body = {
            "code": "INSUFFICIENT_MARGIN",
            "message": "Insufficient margin for order",
            "details": {"order_id": "abc123"},
            "retryable": False,
        }
        exc = from_error_body(body, 400)
        assert isinstance(exc, OrderRejected)
        assert exc.code == "INSUFFICIENT_MARGIN"
        assert exc.order_id == "abc123"
        assert exc.retryable is False
        assert exc.status_code == 400

    def test_invalid_order(self):
        exc = from_error_body({"code": "INVALID_ORDER", "message": "bad"}, 400)
        assert isinstance(exc, OrderRejected)

    def test_unauthorized(self):
        exc = from_error_body({"code": "UNAUTHORIZED", "message": "no"}, 401)
        assert isinstance(exc, AuthError)
        assert exc.status_code == 401

    def test_invalid_signature(self):
        exc = from_error_body({"code": "INVALID_SIGNATURE", "message": "bad sig"}, 401)
        assert isinstance(exc, AuthError)

    def test_signer_prefix(self):
        exc = from_error_body({"code": "SIGNER_MISMATCH", "message": "wrong"}, 403)
        assert isinstance(exc, AuthError)

    def test_nonce_prefix(self):
        exc = from_error_body({"code": "NONCE_EXPIRED", "message": "old"}, 401)
        assert isinstance(exc, AuthError)

    def test_rate_limited(self):
        exc = from_error_body({"code": "RATE_LIMITED", "message": "slow down"}, 429)
        assert isinstance(exc, RateLimitError)

    def test_not_found_suffix(self):
        exc = from_error_body({"code": "ORDERS_NOT_FOUND", "message": "none"}, 404)
        assert isinstance(exc, NotFoundError)

    def test_user_not_found(self):
        exc = from_error_body({"code": "USER_NOT_FOUND", "message": "gone"}, 404)
        assert isinstance(exc, NotFoundError)

    def test_internal_error(self):
        exc = from_error_body({"code": "INTERNAL_ERROR", "message": "oops"}, 500)
        assert isinstance(exc, ServerError)

    def test_ce_communication_error(self):
        exc = from_error_body({"code": "CE_COMMUNICATION_ERROR", "message": "down"}, 502)
        assert isinstance(exc, ServerError)

    def test_timeout_code(self):
        exc = from_error_body({"code": "TIMEOUT", "message": "slow"}, 504)
        assert isinstance(exc, ServerError)

    def test_unknown_code_5xx_fallback(self):
        exc = from_error_body({"code": "SOMETHING_WEIRD", "message": "huh"}, 503)
        assert isinstance(exc, ServerError)

    def test_unknown_code_429_fallback(self):
        exc = from_error_body({"code": "SOMETHING_WEIRD", "message": "huh"}, 429)
        assert isinstance(exc, RateLimitError)

    def test_unknown_code_401_fallback(self):
        exc = from_error_body({"code": "SOMETHING_WEIRD", "message": "huh"}, 401)
        assert isinstance(exc, AuthError)

    def test_unknown_code_404_fallback(self):
        exc = from_error_body({"code": "SOMETHING_WEIRD", "message": "huh"}, 404)
        assert isinstance(exc, NotFoundError)

    def test_truly_unknown_falls_to_base(self):
        exc = from_error_body({"code": "SOMETHING_WEIRD", "message": "huh"}, 400)
        assert type(exc) is OmsError

    def test_details_none(self):
        exc = from_error_body({"code": "INSUFFICIENT_MARGIN", "message": "no margin"}, 400)
        assert isinstance(exc, OrderRejected)
        assert exc.order_id is None

    def test_retryable_field(self):
        exc = from_error_body(
            {"code": "CE_COMMUNICATION_ERROR", "message": "retry", "retryable": True},
            502,
        )
        assert exc.retryable is True


# ---------------------------------------------------------------------------
# raise_for_status_with_body tests
# ---------------------------------------------------------------------------


class TestRaiseForStatusWithBody:
    def test_success_does_not_raise(self):
        from tplus.client.base import raise_for_status_with_body

        resp = httpx.Response(200, request=httpx.Request("GET", "http://x"), text="{}")
        raise_for_status_with_body(resp)  # should not raise

    def test_structured_error_raises_oms_error(self):
        from tplus.client.base import raise_for_status_with_body

        body = json.dumps(
            {
                "error": {
                    "code": "INSUFFICIENT_MARGIN",
                    "message": "Insufficient margin for order",
                    "details": {"order_id": "abc"},
                    "retryable": False,
                }
            }
        )
        resp = httpx.Response(400, request=httpx.Request("POST", "http://x"), text=body)
        with pytest.raises(OrderRejected) as exc_info:
            raise_for_status_with_body(resp)
        assert exc_info.value.code == "INSUFFICIENT_MARGIN"
        assert exc_info.value.order_id == "abc"

    def test_unstructured_error_raises_http_status_error(self):
        from tplus.client.base import raise_for_status_with_body

        resp = httpx.Response(
            500, request=httpx.Request("GET", "http://x"), text="Internal Server Error"
        )
        with pytest.raises(httpx.HTTPStatusError):
            raise_for_status_with_body(resp)

    def test_non_dict_json_falls_back(self):
        from tplus.client.base import raise_for_status_with_body

        resp = httpx.Response(404, request=httpx.Request("GET", "http://x"), text="[]")
        with pytest.raises(httpx.HTTPStatusError):
            raise_for_status_with_body(resp)

    def test_error_key_not_dict_falls_back(self):
        from tplus.client.base import raise_for_status_with_body

        resp = httpx.Response(
            400, request=httpx.Request("GET", "http://x"), text='{"error": "just a string"}'
        )
        with pytest.raises(httpx.HTTPStatusError):
            raise_for_status_with_body(resp)


# ---------------------------------------------------------------------------
# OmsError hierarchy tests
# ---------------------------------------------------------------------------


class TestOmsErrorHierarchy:
    def test_order_rejected_is_oms_error(self):
        assert issubclass(OrderRejected, OmsError)

    def test_auth_error_is_oms_error(self):
        assert issubclass(AuthError, OmsError)

    def test_rate_limit_error_is_oms_error(self):
        assert issubclass(RateLimitError, OmsError)

    def test_not_found_error_is_oms_error(self):
        assert issubclass(NotFoundError, OmsError)

    def test_server_error_is_oms_error(self):
        assert issubclass(ServerError, OmsError)

    def test_str_format(self):
        exc = OmsError(code="TEST", message="test msg", status_code=400)
        assert str(exc) == "[TEST] test msg"

    def test_catching_base_catches_subclass(self):
        exc = OrderRejected(
            code="INSUFFICIENT_MARGIN",
            message="no",
            status_code=400,
            details={"order_id": "x"},
        )
        with pytest.raises(OmsError):
            raise exc
