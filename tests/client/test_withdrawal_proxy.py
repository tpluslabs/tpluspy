from typing import Any

import pytest

from tplus.client.withdrawal import WithdrawalClient
from tplus.exceptions import OmsError, ServerError
from tplus.model.withdrawal import CancelWithdrawalRequest, WithdrawalRequest
from tplus.utils.user import User


@pytest.mark.anyio
async def test_init_withdrawal_uses_oms_client(monkeypatch: pytest.MonkeyPatch):
    user = User()
    client = WithdrawalClient(default_user=user, base_url="http://127.0.0.1:8000")
    request = WithdrawalRequest.create_signed(
        signer=user,
        asset="0x62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7",
        amount=100,
        nonce=7,
    )
    called = {}

    async def fake_post(endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        assert json_data is not None
        called["endpoint"] = endpoint
        called["nonce"] = json_data["inner"]["nonce"]
        return {"success": True}

    monkeypatch.setattr(client, "_post", fake_post)
    await client.init_withdrawal(request)

    assert called["endpoint"] == "withdrawal/init"
    assert called["nonce"] == 7


@pytest.mark.anyio
async def test_init_withdrawal_ignores_timeout_unknown_state(monkeypatch: pytest.MonkeyPatch):
    user = User()
    client = WithdrawalClient(default_user=user, base_url="http://127.0.0.1:8000")
    request = WithdrawalRequest.create_signed(
        signer=user,
        asset="0x62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7",
        amount=100,
        nonce=2,
    )

    async def fake_post(endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        _ = endpoint, json_data
        raise ServerError(
            code="TIMEOUT_UNKNOWN_STATE",
            message="Timed out",
            status_code=504,
        )

    monkeypatch.setattr(client, "_post", fake_post)
    await client.init_withdrawal(request)


@pytest.mark.anyio
async def test_init_withdrawal_propagates_other_oms_errors(monkeypatch: pytest.MonkeyPatch):
    user = User()
    client = WithdrawalClient(default_user=user, base_url="http://127.0.0.1:8000")
    request = WithdrawalRequest.create_signed(
        signer=user,
        asset="0x62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7",
        amount=100,
        nonce=2,
    )

    async def fake_post(endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        _ = endpoint, json_data
        raise OmsError(code="CE_COMMUNICATION_ERROR", message="down", status_code=502)

    monkeypatch.setattr(client, "_post", fake_post)
    with pytest.raises(OmsError, match="CE_COMMUNICATION_ERROR"):
        await client.init_withdrawal(request)


@pytest.mark.anyio
async def test_init_withdrawal_surfaces_oms_failure(monkeypatch: pytest.MonkeyPatch):
    user = User()
    client = WithdrawalClient(default_user=user, base_url="http://127.0.0.1:8000")
    request = WithdrawalRequest.create_signed(
        signer=user,
        asset="0x62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7",
        amount=100,
        nonce=3,
    )

    async def fake_post(endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        _ = endpoint, json_data
        return {"success": False, "details": "nonce mismatch"}

    monkeypatch.setattr(client, "_post", fake_post)

    with pytest.raises(RuntimeError, match="nonce mismatch"):
        await client.init_withdrawal(request)


@pytest.mark.anyio
async def test_get_queued_withdrawals_uses_oms_client(monkeypatch: pytest.MonkeyPatch):
    user = User()
    client = WithdrawalClient(default_user=user, base_url="http://127.0.0.1:8000")
    payload = {
        "user": user.public_key,
        "asset": "0x62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7",
        "amount": "fa",
        "nonce": 9,
        "target": "00" * 32,
        "status": {"type": "approved", "approvals": [{"inner": {"nonce": 9, "signature": "ab"}}]},
    }

    async def fake_get(endpoint: str, json_data=None, **_kwargs):
        _ = json_data
        assert endpoint == f"withdrawal/queue/{user.public_key}"
        return [payload]

    monkeypatch.setattr(client, "_get", fake_get)
    queued = await client.get_queued_withdrawals(user.public_key)

    assert len(queued) == 1
    assert queued[0]["nonce"] == 9
    assert queued[0]["status"]["type"] == "approved"


@pytest.mark.anyio
async def test_cancel_withdrawal_uses_oms_client(monkeypatch: pytest.MonkeyPatch):
    user = User()
    client = WithdrawalClient(default_user=user, base_url="http://127.0.0.1:8000")
    called = {}
    cancel_request = CancelWithdrawalRequest.create_signed(
        signer=user,
        asset_address="0x62622E77D1349Face943C6e7D5c01C61465FE1dc@000000000000aa36a7",
        nonce=4,
    )

    async def fake_post(endpoint: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        assert json_data is not None
        called["endpoint"] = endpoint
        called["nonce"] = json_data["inner"]["nonce"]
        return {}

    monkeypatch.setattr(client, "_post", fake_post)
    await client.cancel_withdrawal(cancel_request)

    assert called["endpoint"] == "withdrawal/cancel"
    assert called["nonce"] == 4
