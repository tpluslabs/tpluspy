import hashlib

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed, encode_dss_signature

from tplus.client.oms.oms_admin import OmsAdminClient, canonical_asset_id
from tplus.model.asset_identifier import AssetIdentifier
from tplus.model.sync_book import CreateSyncBookStatus
from tplus.model.types import UserPublicKey
from tplus.utils.operator import load_operator_sk
from tplus.utils.user import User

MM = UserPublicKey("ab" * 32)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("wire", "status"),
    [
        ("Created", CreateSyncBookStatus.CREATED),
        ("AlreadyExisted", CreateSyncBookStatus.ALREADY_EXISTED),
    ],
)
async def test_create_sync_book_parses_the_reply(build_client, wire, status):
    client, request = build_client(default_user=User())
    request.return_value = {"asset_id": "200", "mm_pubkey": MM, "status": wire}

    response = await client.create_sync_book(AssetIdentifier("200"))

    assert request.call_args.args[:2] == ("POST", "/sync_book/create")
    assert request.call_args.kwargs["json_data"] == {"asset_id": "200"}
    assert response.status == status
    assert response.mm_pubkey == MM


@pytest.mark.anyio
async def test_operator_create_sync_book_signs_the_oms_layout(mocker, operator_secret):
    """The signed bytes mirror ``OperatorCreateSyncBookRequest::signing_payload`` in the OMS."""
    client = OmsAdminClient("http://example.com")
    request = mocker.patch.object(
        client,
        "_request",
        new=mocker.AsyncMock(
            return_value={"asset_id": "200", "mm_pubkey": MM, "status": "Created"}
        ),
    )

    response = await client.create_sync_book(
        MM, AssetIdentifier("200"), operator_secret, timestamp_ns=2, nonce=1
    )

    assert response.status == CreateSyncBookStatus.CREATED
    assert request.call_args.args[:2] == ("POST", "admin/sync-book")
    body = request.call_args.kwargs["json_data"]
    assert body["inner"] == {"timestamp_ns": 2, "nonce": 1, "asset_id": "200", "user_id": MM}
    expected = (
        b"oms.admin.create_sync_book.v1"
        + (1).to_bytes(8, "big")
        + (2).to_bytes(8, "big")
        + bytes.fromhex(MM)
        + b"200"
    )
    signature = bytes.fromhex(body["signature"])
    der = encode_dss_signature(
        int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
    )
    load_operator_sk(operator_secret).public_key().verify(
        der, hashlib.sha256(expected).digest(), ec.ECDSA(Prehashed(hashes.SHA256()))
    )


# The OMS's own spellings (`the_signed_asset_is_the_canonical_identifier` holds the same pairs).
CANONICAL = [
    ("0200", "200"),
    (200, "200"),
    (
        "62622E77D1349Face943C6e7D5c01C61465FE1dc@00000000000000a4b1",
        "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@00000000000000a4b1",
    ),
    (
        "62622E77D1349FACE943C6E7D5C01C61465FE1DC000000000000000000000000@00000000000000A4B1",
        "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@00000000000000a4b1",
    ),
]


@pytest.mark.parametrize(("spelled", "canonical"), CANONICAL)
def test_canonical_asset_id_is_the_oms_spelling(spelled, canonical):
    assert canonical_asset_id(spelled) == canonical
    assert canonical_asset_id(AssetIdentifier(spelled)) == canonical


@pytest.mark.anyio
@pytest.mark.parametrize(("spelled", "canonical"), CANONICAL)
async def test_operator_create_sync_book_signs_and_sends_the_canonical_asset(
    mocker, operator_secret, spelled, canonical
):
    client = OmsAdminClient("http://example.com")
    request = mocker.patch.object(
        client,
        "_request",
        new=mocker.AsyncMock(
            return_value={"asset_id": canonical, "mm_pubkey": MM, "status": "Created"}
        ),
    )

    await client.create_sync_book(MM, spelled, operator_secret, timestamp_ns=2, nonce=1)

    body = request.call_args.kwargs["json_data"]
    assert body["inner"]["asset_id"] == canonical
    expected = (
        b"oms.admin.create_sync_book.v1"
        + (1).to_bytes(8, "big")
        + (2).to_bytes(8, "big")
        + bytes.fromhex(MM)
        + canonical.encode()
    )
    signature = bytes.fromhex(body["signature"])
    der = encode_dss_signature(
        int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
    )
    load_operator_sk(operator_secret).public_key().verify(
        der, hashlib.sha256(expected).digest(), ec.ECDSA(Prehashed(hashes.SHA256()))
    )
