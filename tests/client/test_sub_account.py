import pytest

from tplus.client.market_data import MarketDataClient
from tplus.client.orderbook import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.sub_account import SubAccountType


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


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        pytest.param("Spot", "Spot", id="spot"),
        pytest.param("CrossMargin", "CrossMargin", id="cross-margin"),
        pytest.param(
            "Isolated",
            {"Isolated": {"asset": "200"}},
            id="isolated",
        ),
    ],
)
def test_build_transfer_to_subaccount_encodes_the_target_account_type(
    build_client, eth_user, kind, expected
):
    client, _ = build_client(default_user=eth_user)

    payload = client._build_transfer_to_subaccount(
        0,
        1,
        AssetIdentifier("200"),
        1234,
        SubAccountType.from_kind(kind, AssetIdentifier("200")),
        nonce=1,
        user=eth_user,
    )

    assert payload["inner"]["target_account_type"] == expected
