from pydantic import BaseModel

from tplus.model.order import CreateOrderRequest


class BatchCreateOrderRequest(BaseModel):
    orders: list[CreateOrderRequest]


class SingleOrderFromBatch(BaseModel):
    order_id: str
    status: str
    reason: str | None


class BatchCreateOrderRequestResponse(BaseModel):
    batch_order_status: list[SingleOrderFromBatch]


def parse_batch_order_response(
    parsed_batch_order_response: dict,
) -> BatchCreateOrderRequestResponse:
    list_of_single_orders_from_batch: list[SingleOrderFromBatch] = []
    results = parsed_batch_order_response["results"]
    for result in results:
        single_order_from_batch = SingleOrderFromBatch(
            order_id=result["order_id"], status=result["status"], reason=result["reason"]
        )
        list_of_single_orders_from_batch.append(single_order_from_batch)

    return BatchCreateOrderRequestResponse(batch_order_status=list_of_single_orders_from_batch)
