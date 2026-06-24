from tplus._cli import cli


def test_sync_vault_events_invokes_client(runner, mock_blockchain_client):
    result = runner.invoke(
        cli,
        [
            "debug",
            "sync-vault-events",
            "--from-block",
            "0",
            "--to-block",
            "100",
            "--blockchain-base-url",
            "http://127.0.0.1:8080",
        ],
    )

    assert result.exit_code == 0, result.output
    mock_blockchain_client.sync_vault_events.assert_awaited_once_with(
        0, 100, address=None, events=None, operator_secret=None
    )
