"""
This mirrors the Rust implementation in bin/clearing-engine/src/permissionless/routes/auth.rs
"""

import time

import httpx
import pytest

from tplus.client.clearingengine import AdminClient


@pytest.mark.integration
class TestCeAdminAuth:
    def test_modify_user_status_request(self, operator_secret, ce_url):
        """Sign a ModifyUserStatusRequest and POST to /admin/status/modify."""
        sk = AdminClient._load_operator_sk(operator_secret=operator_secret)
        ts = time.time_ns()
        nonce = time.time_ns()
        user_pubkey = bytes(range(32))
        payload = (
            b"ce.admin.status.modify.v1"
            + nonce.to_bytes(8, "big")
            + ts.to_bytes(8, "big")
            + user_pubkey
            + b"\x01"
        )
        sig = AdminClient._sign(payload, sk)

        resp = httpx.post(
            f"{ce_url}/admin/status/modify",
            json={
                "inner": {
                    "user": user_pubkey.hex(),
                    "is_mm": True,
                    "timestamp_ns": ts,
                    "nonce": nonce,
                },
                "signature": sig,
            },
            timeout=5,
        )
        assert resp.status_code == 200
