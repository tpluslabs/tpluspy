import json
from types import SimpleNamespace

import pytest

from tplus.client.market_data import MarketDataClient
from tplus.client.orderbook import OrderBookClient
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.transfer import cross_margin, isolated


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


PINNED_MARGIN_INNER = (
    '{"user":"' + "00" * 32 + '","source_index":1,"target_index":4,"transfer_asset":"9",'
    '"transfer_amount":"500","target_account_type":{"Isolated":{"asset":9}},"nonce":3}'
)


def test_margin_transfer_matches_pinned_wire_payload():
    user = SimpleNamespace(public_key="00" * 32, signing_parts=lambda _payload: ([], []))
    client = OrderBookClient("http://example.com", default_user=user)
    payload = client._build_transfer_request(
        1, 4, AssetIdentifier("9"), 500, isolated(9), nonce=3, user=user
    )
    assert json.dumps(payload["inner"], separators=(",", ":")) == PINNED_MARGIN_INNER


def test_trading_account_kinds():
    assert cross_margin() == "CrossMargin"
    assert isolated(9) == {"Isolated": {"asset": 9}}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "result",
    [
        {
            "success": True,
            "state": "queued",
            "queued": {
                "progress": {"filled_principal": "0", "remaining_principal": "10"},
                "matures_at_ns": 1,
            },
        },
        {
            "success": True,
            "state": "completed",
            "debited": {"Custody": {"amount": "10"}},
            "credited": {"Canonical": {"amount": "30"}},
        },
    ],
)
async def test_transfer_response_preserved(monkeypatch, result):
    from tplus.client.orderbook import OrderBookClient
    from tplus.model.asset_identifier import AssetIdentifier
    from tplus.utils.user import User

    client = OrderBookClient(default_user=User())

    async def send(payload):
        assert payload["inner"]["transfer_amount"] == "10"
        return result

    monkeypatch.setattr(client, "_send_transfer_request", send)
    assert await client.request_transfer(0, 1, AssetIdentifier.model_validate("1"), 10) == result
