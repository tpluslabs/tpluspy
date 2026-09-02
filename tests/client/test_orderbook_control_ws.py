import asyncio

import pytest

from tplus.client.orderbook import CONTROL_WS_PROTOCOL
from tplus.exceptions import RateLimitError
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.batch_order import BatchCreateOrderRequest, BatchReplaceOrderRequest
from tplus.utils.limit_order import create_limit_order_ob_request_payload
from tplus.utils.replace_order import create_replace_order_ob_request_payload

ASSET_ID = AssetIdentifier(root="200")


def build_batch(user, *order_ids: str) -> BatchCreateOrderRequest:
    return BatchCreateOrderRequest(
        orders=[
            create_limit_order_ob_request_payload(
                quantity=1,
                price=1000,
                side="Buy",
                signer=user,
                book_quantity_decimals=3,
                book_price_decimals=3,
                asset_identifier=ASSET_ID,
                order_id=order_id,
            )
            for order_id in order_ids
        ]
    )


def build_replace_batch(user, *order_ids: str) -> BatchReplaceOrderRequest:
    return BatchReplaceOrderRequest(
        replaces=[
            create_replace_order_ob_request_payload(
                original_order_id=order_id,
                asset_identifier=ASSET_ID,
                signer=user,
                new_price=1000,
                new_quantity=1,
                book_price_decimals=3,
                book_quantity_decimals=3,
            )
            for order_id in order_ids
        ]
    )


ACK = {"request": {"status": "submitted"}}


def build_create_response(order_id: str, status: str, reason: str | None = None) -> dict:
    return {
        "CreateOrderResponse": {
            "response": {"order_id": order_id, "status": status, "reason": reason},
            "asset_id": str(ASSET_ID),
        }
    }


def build_replace_response(order_id: str, status: str, reason: str | None = None) -> dict:
    return {
        "ReplaceOrderResponse": {
            "response": {"order_id": order_id, "status": status, "reason": reason},
            "asset_id": str(ASSET_ID),
        }
    }


@pytest.mark.anyio
async def test_ensure_control_ws_negotiates_v1(control_ws_client):
    await control_ws_client._ensure_control_ws()

    control_ws_client._open_ws.assert_awaited_once_with(
        "/control", ws_kwargs={"subprotocols": [CONTROL_WS_PROTOCOL]}
    )


@pytest.mark.anyio
async def test_control_ws_send_correlates_by_request_id(control_ws_client, control_ws):
    order_id = "abc"
    payload = {"CancelOrderRequest": {"cancel": {"order_id": order_id, "asset_id": str(ASSET_ID)}}}

    task = asyncio.create_task(
        control_ws_client._control_ws_send(payload, expected_order_id=order_id, timeout=0.5)
    )
    await asyncio.sleep(0)

    sent = control_ws.sent_frame()
    assert sent["data"] == payload

    control_ws.feed(
        {
            "type": "event",
            "channel": "control",
            "request_id": sent["request_id"],
            "data": {
                "CancelOrderResponse": {
                    "response": {"order_id": order_id, "status": "Received"},
                    "asset_id": str(ASSET_ID),
                }
            },
            "error": None,
        }
    )

    assert "CancelOrderResponse" in await task


@pytest.mark.anyio
async def test_control_ws_send_ignores_submitted_ack(control_ws_client, control_ws):
    payload = {"CancelOrderRequest": {"cancel": {"order_id": "oid1", "asset_id": str(ASSET_ID)}}}

    task = asyncio.create_task(
        control_ws_client._control_ws_send(payload, expected_order_id="oid1", timeout=1.0)
    )
    await asyncio.sleep(0)
    request_id = control_ws.sent_frame()["request_id"]

    # The server acks every accepted request under the same request id before the
    # terminal response, so correlating on request id alone resolves too early.
    control_ws.feed(
        {
            "type": "ack",
            "channel": "control",
            "request_id": request_id,
            "data": ACK,
            "error": None,
        }
    )
    control_ws.feed(
        {
            "type": "event",
            "channel": "control",
            "request_id": request_id,
            "data": build_create_response("oid1", "Received"),
            "error": None,
        }
    )

    assert control_ws_client._extract_operation_response(await task).status == "Received"


@pytest.mark.anyio
async def test_control_ws_send_batch_gathers_out_of_order_responses(
    control_ws_client, control_ws, control_user
):
    batch = build_batch(control_user, "oid1", "oid2")

    task = asyncio.create_task(control_ws_client._control_ws_send_batch(batch, timeout=1.0))
    await asyncio.sleep(0)

    sent = control_ws.sent_frame()
    request_id = sent["request_id"]
    assert list(sent.keys()) == ["request_id", "data"]
    assert list(sent["data"].keys()) == ["BatchCreateRequest"]

    # The ack carries no order id and must be ignored, then responses arrive reversed.
    for data in (
        ACK,
        build_create_response("oid2", "Rejected", reason="InsufficientInventory"),
        build_create_response("oid1", "Received"),
    ):
        control_ws.feed(
            {
                "type": "event",
                "channel": "control",
                "request_id": request_id,
                "data": data,
                "error": None,
            }
        )

    response = await task

    by_id = {status.order_id: status for status in response.batch_order_status}
    assert by_id["oid1"].status == "Received"
    assert by_id["oid1"].reason is None
    assert by_id["oid2"].status == "Rejected"
    assert by_id["oid2"].reason == "InsufficientInventory"


@pytest.mark.anyio
async def test_control_ws_send_replace_batch_gathers_per_item_responses(
    control_ws_client, control_ws, control_user
):
    batch = build_replace_batch(control_user, "oid1", "oid2")

    task = asyncio.create_task(control_ws_client._control_ws_send_replace_batch(batch, timeout=1.0))
    await asyncio.sleep(0)

    sent = control_ws.sent_frame()
    request_id = sent["request_id"]
    assert list(sent["data"].keys()) == ["BatchReplaceRequest"]
    wire_items = sent["data"]["BatchReplaceRequest"]["replaces"]
    assert [item["request"]["order_id"] for item in wire_items] == ["oid1", "oid2"]
    # Each item carries its own signature and signer, exactly like a single replace.
    assert all(item["signer"] and item["signature"] for item in wire_items)

    # The ack carries no order id and must be ignored; per-item replies may arrive in
    # any order, as each orderbook answers.
    for data in (
        ACK,
        build_replace_response("oid2", "Rejected", reason="OrderNotFound"),
        build_replace_response("oid1", "Received"),
    ):
        control_ws.feed(
            {
                "type": "event",
                "channel": "control",
                "request_id": request_id,
                "data": data,
                "error": None,
            }
        )

    response = await task

    assert [status.order_id for status in response.batch_order_status] == ["oid1", "oid2"]
    by_id = {status.order_id: status for status in response.batch_order_status}
    assert by_id["oid1"].status == "Received"
    assert by_id["oid1"].reason is None
    assert by_id["oid2"].status == "Rejected"
    assert by_id["oid2"].reason == "OrderNotFound"


@pytest.mark.anyio
async def test_control_ws_send_rate_limit_is_correlated_without_timeout(
    control_ws_client, control_ws
):
    payload = {"ReplaceOrderRequest": {"request": {"order_id": "oid1", "base_asset": "200"}}}

    task = asyncio.create_task(
        control_ws_client._control_ws_send(payload, expected_order_id="oid1", timeout=1.0)
    )
    await asyncio.sleep(0)

    control_ws.feed(
        {
            "type": "error",
            "channel": "control",
            "request_id": control_ws.sent_frame()["request_id"],
            "data": None,
            "error": {
                "code": "RATE_LIMITED",
                "message": "Rate limit exceeded",
                "details": {},
                "retryable": True,
            },
        }
    )

    with pytest.raises(RateLimitError) as exc_info:
        await task

    assert exc_info.value.status_code == 429
    assert exc_info.value.retryable is True
