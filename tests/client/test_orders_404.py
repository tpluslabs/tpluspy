import pytest


@pytest.mark.anyio
async def test_get_user_orders_for_book_404_empty(monkeypatch):
    """Legacy path: 404 with empty-list body (pre-standardised error format)."""
    import httpx

    from tplus.client.orderbook import OrderBookClient

    class DummyClient(OrderBookClient):
        async def _request(self, method, endpoint, json_data=None, params=None):
            req = httpx.Request(method, f"http://example.com{endpoint}")
            resp = httpx.Response(404, request=req, text="[]")
            raise httpx.HTTPStatusError("Not Found", request=req, response=resp)

    class DummyUser:
        public_key = "USER"

    client = DummyClient(user=DummyUser(), base_url="http://example.com")  # type: ignore
    orders = await client.get_user_orders_for_book(
        asset_id=type("A", (), {"__str__": lambda self: "200"})()
    )
    assert orders == []


@pytest.mark.anyio
async def test_get_user_orders_for_book_not_found_error(monkeypatch):
    """New path: NotFoundError raised by standardised error handling."""
    from tplus.client.orderbook import OrderBookClient
    from tplus.exceptions import NotFoundError

    class DummyClient(OrderBookClient):
        async def _request(self, method, endpoint, json_data=None, params=None):
            raise NotFoundError(
                code="ORDERS_NOT_FOUND",
                message="No orders found",
                status_code=404,
            )

    class DummyUser:
        public_key = "USER"

    client = DummyClient(user=DummyUser(), base_url="http://example.com")  # type: ignore
    orders = await client.get_user_orders_for_book(
        asset_id=type("A", (), {"__str__": lambda self: "200"})()
    )
    assert orders == []
