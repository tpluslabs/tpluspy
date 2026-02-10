"""
This mirrors the Rust implementation in bin/clearing-engine/src/permissionless/routes/auth.rs
"""

import time

import httpx
import pytest

from tplus.client.clearingengine import AdminClient

CE_URL = "http://127.0.0.1:3032"
# this one's the one from the ce.toml config
OPERATOR_SECRET = "afa3fd40eafd3703780358990983f75930c87744455bf18a472012a04ae521ff"


@pytest.mark.integration
class TestCeAdminAuth:
    def test_set_primary_request(self):
        """Sign a SetPrimaryRequest and POST to /rotation/fetch."""
        sk = AdminClient._load_operator_sk(operator_secret=OPERATOR_SECRET)
        ts = time.time_ns()
        payload = ts.to_bytes(8, "big") + b"\x01"
        sig = AdminClient._sign(payload, sk)

        resp = httpx.post(
            f"{CE_URL}/rotation/fetch",
            json={"inner": {"primary": True, "timestamp_ns": ts}, "signature": sig},
            timeout=5,
        )
        assert resp.status_code == 200

    def test_modify_user_status_request(self):
        """Sign a ModifyUserStatusRequest and POST to /admin/status/modify."""
        sk = AdminClient._load_operator_sk(operator_secret=OPERATOR_SECRET)
        ts = time.time_ns()
        user_pubkey = bytes(range(32))
        payload = ts.to_bytes(8, "big") + user_pubkey + b"\x01"
        sig = AdminClient._sign(payload, sk)

        resp = httpx.post(
            f"{CE_URL}/admin/status/modify",
            json={
                "inner": {
                    "user": user_pubkey.hex(),
                    "is_mm": True,
                    "timestamp_ns": ts,
                },
                "signature": sig,
            },
            timeout=5,
        )
        assert resp.status_code == 200
