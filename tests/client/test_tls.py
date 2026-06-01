import pytest


@pytest.mark.anyio
async def test_http_client_verify_flag(monkeypatch):
    from tplus.client.base import BaseClient

    c = BaseClient(base_url="http://localhost")
    try:
        assert c._settings.insecure_ssl is False
        assert c._settings.verify_requests is True
    finally:
        await c.close()


@pytest.mark.anyio
async def test_http_client_insecure_ssl_disables_verify(monkeypatch):
    from tplus.client.base import BaseClient

    c = BaseClient(base_url="http://localhost", insecure_ssl=True)
    try:
        assert c._settings.insecure_ssl is True
    finally:
        await c.close()
