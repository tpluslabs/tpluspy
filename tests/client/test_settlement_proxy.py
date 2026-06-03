from typing import Any

import pytest

from tplus.client import OrderBookClient
from tplus.model.settlement import TxSettlementRequest
from tplus.utils.user import User


def _signed_settlement_request(user: User) -> TxSettlementRequest:
    # Inner settlement uses 32-byte asset IDs (padded EVM token addresses), not `addr@chain` vault strings.
    return TxSettlementRequest.create_signed(
        {
            "tplus_user": user.public_key,
            "sub_account_index": user.sub_account,
            "settler": user.public_key,
            "asset_in": "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000",
            "amount_in": "1000000000000000000",
            "asset_out": "11fe4b6ae13d2a6055c8d9cf65c55bac32b5d844000000000000000000000000",
            "amount_out": "500000000000000000",
            "chain_id": "000000000000aa36a7",
        },
        user,
    )


@pytest.mark.anyio
async def test_init_settlement_uses_oms_client(monkeypatch: pytest.MonkeyPatch):
    user = User(sub_account=12)
    client = OrderBookClient(default_user=user, base_url="http://127.0.0.1:8000")
    request = _signed_settlement_request(user)
    called = {}

    async def fake_post(endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        assert json_data is not None
        called["endpoint"] = endpoint
        called["sub_account_index"] = json_data["inner"]["sub_account_index"]
        return {
            "success": True,
            "approval": {"inner": {"nonce": 12, "signature": "00"}, "expiry": 1},
        }

    monkeypatch.setattr(client, "_post", fake_post)
    await client.init_settlement(request)

    assert called["endpoint"] == "settlement/init"
    assert called["sub_account_index"] == 12


@pytest.mark.anyio
async def test_init_settlement_surfaces_oms_failure(monkeypatch: pytest.MonkeyPatch):
    user = User()
    client = OrderBookClient(default_user=user, base_url="http://127.0.0.1:8000")
    request = _signed_settlement_request(user)

    async def fake_post(endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        _ = endpoint, json_data
        return {"success": False, "details": "invalid settlement request"}

    monkeypatch.setattr(client, "_post", fake_post)

    with pytest.raises(RuntimeError, match="invalid settlement request"):
        await client.init_settlement(request)


@pytest.mark.anyio
async def test_get_settlement_signatures_uses_oms_client(monkeypatch: pytest.MonkeyPatch):
    user = User()
    client = OrderBookClient(default_user=user, base_url="http://127.0.0.1:8000")
    called = {}

    async def fake_get(endpoint: str, json_data: dict[str, Any] | None = None) -> Any:
        _ = json_data
        called["endpoint"] = endpoint
        return [{"inner": {"nonce": 7}}]

    monkeypatch.setattr(client, "_get", fake_get)
    result = await client.get_settlement_signatures(user.public_key)

    assert called["endpoint"] == f"settlement/signatures/{user.public_key}"
    assert result == [{"inner": {"nonce": 7}}]
