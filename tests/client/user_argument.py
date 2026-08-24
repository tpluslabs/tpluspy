"""Shared checks for passing an EVM account straight into client API calls."""

from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.cancel_order import CancelOrder
from tplus.utils.user import to_user

ASSET = AssetIdentifier(200)


async def check_read_call_uses_derived_user(account, build_client) -> None:
    """A read call with the account as ``default_user`` addresses the derived T+ user."""
    expected = to_user(account).public_key
    client, request = build_client(default_user=account)

    await client.get_user_inventory()
    assert request.call_args.args[1] == f"/inventory/user/{expected}"


async def check_read_call_with_per_call_user(account, build_client) -> None:
    """The same holds for a per-call ``user=`` override on a client with no default."""
    expected = to_user(account).public_key
    client, request = build_client()

    await client.get_user_inventory(user=account)
    assert request.call_args.args[1] == f"/inventory/user/{expected}"
    # The override must also reach the auth layer, or the request authenticates as the
    # default user (or fails outright when there is none).
    assert request.call_args.kwargs["user"] is account


async def check_signed_call_uses_derived_key(account, build_client) -> None:
    """A signing call signs with the derived Ed25519 key, and the T+ user verifies it."""
    user = to_user(account)
    client, request = build_client(default_user=account)

    await client.cancel_order("oid", ASSET)
    method, endpoint = request.call_args.args
    body = request.call_args.kwargs["json_data"]
    assert method == "DELETE"
    assert endpoint == "/orders/cancel"
    assert body["cancel"]["signer"] == user.public_key

    cancel = CancelOrder.model_validate(body["cancel"])
    signed_payload = cancel.model_dump_json().replace(" ", "")
    user.vk.verify(bytes(body["signature"]), signed_payload.encode("utf-8"))
    assert request.call_args.kwargs["user"].public_key == user.public_key
