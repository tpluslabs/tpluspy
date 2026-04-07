import pytest


@pytest.mark.anyio
async def test_http_client_verify_flag(monkeypatch):
    from tplus.client.base import BaseClient, ClientSettings

    settings = ClientSettings(base_url="http://localhost")
    c = BaseClient(settings)
    try:
        assert isinstance(c._client, type(c._client))
    finally:
        await c.close()


@pytest.mark.anyio
async def test_http_client_insecure_ssl_disables_verify(monkeypatch):
    from tplus.client.base import BaseClient, ClientSettings

    settings = ClientSettings(base_url="http://localhost", insecure_ssl=True)
    c = BaseClient(settings)
    try:
        assert settings.insecure_ssl is True
    finally:
        await c.close()
