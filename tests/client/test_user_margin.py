from decimal import Decimal

import httpx
import pytest

from tplus.client.orderbook import OrderBookClient
from tplus.exceptions import NotFoundError
from tplus.model.user_margin import PositionSide, parse_user_margin_info
from tplus.utils.user import User

MARGIN_RESPONSE = {
    "accounts": {
        "1": {
            "account_equity": "15000.0",
            "available_margin": "3000.0",
            "utilized_margin": "12000.0",
            "maintenance_margin_surplus": "10000.0",
            "mm_requirement": "5000.0",
            "account_leverage": "4.0",
            "is_solvent": True,
            "is_liquidatable": False,
            "total_upnl": "250.0",
            "im_surplus": None,
            "net_apy": None,
            "positions": [
                {
                    "asset_id": "2",
                    "side": "long",
                    "size": "10.0",
                    "notional_value": "60000.0",
                    "margin": "5000.0",
                }
            ],
        }
    },
    "warnings": [
        {
            "sub_account": 1,
            "code": "SPOT_PRICE_UNAVAILABLE",
            "message": "No price for asset 3",
            "asset": "3",
        }
    ],
}


def test_parse_user_margin_info_preserves_complete_oms_response():
    result = parse_user_margin_info(MARGIN_RESPONSE)

    account = result.accounts[1]
    assert account.account_equity == Decimal("15000.0")
    assert account.available_margin == Decimal("3000.0")
    assert account.utilized_margin == Decimal("12000.0")
    assert account.maintenance_margin_surplus == Decimal("10000.0")
    assert account.mm_requirement == Decimal("5000.0")
    assert account.account_leverage == Decimal("4.0")
    assert account.is_solvent is True
    assert account.is_liquidatable is False
    assert account.total_upnl == Decimal("250.0")
    assert account.im_surplus is None
    assert account.net_apy is None
    assert account.positions is not None
    assert account.positions[0].side is PositionSide.LONG
    assert account.positions[0].margin == Decimal("5000.0")
    assert result.warnings[0].code == "SPOT_PRICE_UNAVAILABLE"
    assert result.warnings[0].asset == "3"


@pytest.mark.anyio
async def test_get_user_margin_info_uses_single_sub_account_filter():
    user = User()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/nonce/"):
            return httpx.Response(200, json={"value": "n"})
        if request.url.path == "/auth":
            return httpx.Response(
                200,
                json={"token": "tok", "expiry_ns": 9_999_999_999_999_999_999},
            )
        if request.url.path == f"/margin/user/{user.public_key}":
            assert request.url.params.get("sub_account") == "1"
            assert request.url.params.get("include_positions") == "true"
            return httpx.Response(200, json=MARGIN_RESPONSE)
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    client = OrderBookClient("http://test", default_user=user, client=httpx_client)

    result = await client.get_user_margin_info(sub_account=1, include_positions=True)

    assert result.accounts[1].mm_requirement == Decimal("5000.0")
    await client.close()


@pytest.mark.anyio
async def test_get_user_margin_info_rejects_multiple_legacy_filters():
    client = OrderBookClient(default_user=User())

    with pytest.raises(ValueError, match="at most one sub-account"):
        await client.get_user_margin_info(sub_accounts=[1, 2])

    await client.close()


@pytest.mark.anyio
async def test_get_user_margin_info_surfaces_not_found():
    user = User()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/nonce/"):
            return httpx.Response(200, json={"value": "n"})
        if request.url.path == "/auth":
            return httpx.Response(
                200,
                json={"token": "tok", "expiry_ns": 9_999_999_999_999_999_999},
            )
        if request.url.path == f"/margin/user/{user.public_key}":
            return httpx.Response(
                404,
                json={
                    "error": {
                        "code": "USER_NOT_FOUND",
                        "message": "User not found",
                        "retryable": False,
                    }
                },
            )
        return httpx.Response(404)

    httpx_client = httpx.AsyncClient(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    client = OrderBookClient("http://test", default_user=user, client=httpx_client)

    with pytest.raises(NotFoundError, match="User not found"):
        await client.get_user_margin_info()

    await client.close()
