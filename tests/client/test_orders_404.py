import pytest


@pytest.mark.anyio
async def test_get_user_orders_for_book_404_empty(monkeypatch):
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
