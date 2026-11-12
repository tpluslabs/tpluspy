import asyncio


def test_update_governance_authorities_posts_the_sync_request(clearing_engine_client):
    asyncio.run(clearing_engine_client.update_governance_authorities())

    clearing_engine_client._post.assert_awaited_once_with("governance-authorities/update")
