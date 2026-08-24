import pytest

from tplus.client.market_data import MarketDataClient
from tplus.client.orderbook import OrderBookClient


@pytest.mark.anyio
async def test_get_sub_account_names_parses_entries(mocker, eth_user, expected_user_id):
    client = MarketDataClient("http://example.com", default_user=eth_user)
    get = mocker.patch.object(
        client,
        "_get",
        new=mocker.AsyncMock(
            return_value={
                "names": [
                    {"account_index": 2, "name": "First"},
                    {"account_index": 7, "name": "Second"},
                ]
            }
        ),
    )

    response = await client.get_sub_account_names()

    assert get.call_args.args[0] == f"/sub-accounts/user/{expected_user_id}"
    assert [(entry.account_index, entry.name) for entry in response.names] == [
        (2, "First"),
        (7, "Second"),
    ]


@pytest.mark.anyio
async def test_rename_sub_account_parses_response(mocker, eth_user, expected_user_id):
    client = OrderBookClient("http://example.com", default_user=eth_user)
    patch = mocker.patch.object(
        client,
        "_patch",
        new=mocker.AsyncMock(
            return_value={"account_index": 2, "old_name": "Sub 2", "new_name": "Rekt Whale"}
        ),
    )

    response = await client.rename_sub_account(2, "Rekt Whale")

    assert patch.call_args.args[0] == f"/account/{expected_user_id}/sub-account/2/name"
    assert patch.call_args.kwargs["json_data"] == {"name": "Rekt Whale"}
    assert response.new_name == "Rekt Whale"
