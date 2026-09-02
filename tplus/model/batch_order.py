from pydantic import BaseModel

from tplus.model.order import CreateOrderRequest
from tplus.model.replace_order import ReplaceOrderRequestPayload


class BatchCreateOrderRequest(BaseModel):
    orders: list[CreateOrderRequest]


class BatchReplaceOrderRequest(BaseModel):
    """Body of ``PATCH /orders/batch-replace`` / the ``BatchReplaceRequest`` control message.

    Each item is a complete, individually signed replace, exactly as sent to the single
    replace endpoint. At most 50 items; an order id may appear only once per batch.
    """

    replaces: list[ReplaceOrderRequestPayload]


class SingleOrderStatusFromBatch(BaseModel):
    order_id: str
    status: str
    reason: str | None


class BatchCreateOrderRequestResponse(BaseModel):
    batch_order_status: list[SingleOrderStatusFromBatch]


def parse_batch_order_response(
    parsed_batch_order_response: dict,
) -> BatchCreateOrderRequestResponse:
    list_of_single_orders_from_batch: list[SingleOrderStatusFromBatch] = []
    results = parsed_batch_order_response["results"]
    for result in results:
        single_order_from_batch = SingleOrderStatusFromBatch(
            order_id=result["order_id"], status=result["status"], reason=result["reason"]
        )
        list_of_single_orders_from_batch.append(single_order_from_batch)

    return BatchCreateOrderRequestResponse(batch_order_status=list_of_single_orders_from_batch)


class BatchReplaceOrderRequestResponse(BaseModel):
    """One :class:`SingleOrderStatusFromBatch` per submitted replace, in submission order."""

    batch_order_status: list[SingleOrderStatusFromBatch]


def parse_batch_replace_response(
    parsed_batch_replace_response: dict,
) -> BatchReplaceOrderRequestResponse:
    return BatchReplaceOrderRequestResponse(
        batch_order_status=[
            SingleOrderStatusFromBatch(
                order_id=result["order_id"],
                status=result["status"],
                reason=result.get("reason"),
            )
            for result in parsed_batch_replace_response["results"]
        ]
    )
