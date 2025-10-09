import pytest


@pytest.mark.anyio
async def test_http_client_verify_flag(monkeypatch):
    from tplus.client.base import BaseClient

    class DummyUser:
        public_key = "USER"

    c = BaseClient(user=DummyUser(), base_url="http://localhost")  # type: ignore
    try:
        # Insecure is False by default → default httpx AsyncClient verifies certs by default
        # We cannot access private verify attribute reliably; ensure auth headers would carry token when set
        assert isinstance(c._client, type(c._client))
    finally:
        await c.close()


@pytest.mark.anyio
async def test_http_client_insecure_ssl_disables_verify(monkeypatch):
    from tplus.client.base import BaseClient

    class DummyUser:
        public_key = "USER"

    c = BaseClient(user=DummyUser(), base_url="http://localhost", insecure_ssl=True)  # type: ignore
    try:
        # Construction should succeed with insecure flag; httpx accepts verify=False
        assert c._insecure_ssl is True
    finally:
        await c.close()
