import pytest

from tests.client.user_argument import (
    ASSET,
    check_read_call_uses_derived_user,
    check_read_call_with_per_call_user,
    check_signed_call_uses_derived_key,
)


@pytest.mark.anyio
async def test_get_user_inventory_eth_account_as_default_user(eth_account, build_client):
    await check_read_call_uses_derived_user(eth_account, build_client)


@pytest.mark.anyio
async def test_get_user_inventory_eth_account_as_user_argument(eth_account, build_client):
    await check_read_call_with_per_call_user(eth_account, build_client)


@pytest.mark.anyio
async def test_cancel_order_eth_account_as_default_user(eth_account, build_client):
    await check_signed_call_uses_derived_key(eth_account, build_client)


@pytest.mark.anyio
async def test_get_user_inventory_public_key_still_accepted(eth_user, client_build):
    client, request = client_build

    await client.get_user_inventory(user=eth_user.public_key)
    assert request.call_args.args[1] == f"/inventory/user/{eth_user.public_key}"


@pytest.mark.anyio
async def test_cancel_order_public_key_cannot_sign(eth_user, client):
    with pytest.raises(TypeError, match="Cannot sign with"):
        await client.cancel_order("oid", ASSET, user=eth_user.public_key)  # type: ignore[arg-type]
