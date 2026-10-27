import json

from tplus.model.multisig import SignerEntry, SignerKey

KEY = {"Ed25519": [7] * 32}


class TestSignerEntry:
    def test_serializes_in_signing_order_and_omits_unset_level(self):
        entry = SignerEntry.model_validate(
            {
                "max_signing_window_ns": 60,
                "weight": 1,
                "key": KEY,
                "created_at_ns": 5,
                "expires_at_ns": None,
            }
        )
        dumped = entry.model_dump(mode="json")
        assert list(dumped) == [
            "key",
            "weight",
            "created_at_ns",
            "expires_at_ns",
            "max_signing_window_ns",
        ]
        assert json.dumps(dumped, separators=(",", ":")) == (
            '{"key":{"Ed25519":' + json.dumps([7] * 32, separators=(",", ":")) + "},"
            '"weight":1,"created_at_ns":5,"expires_at_ns":null,"max_signing_window_ns":60}'
        )

    def test_carries_a_set_level_last(self):
        entry = SignerEntry(
            key=SignerKey.ed25519([7] * 32),
            weight=2,
            created_at_ns=5,
            max_multisig_permission_level="low",
        )
        dumped = entry.model_dump(mode="json")
        assert list(dumped)[-1] == "max_multisig_permission_level"
        assert dumped["max_multisig_permission_level"] == "low"
        assert entry.key == SignerKey.ed25519([7] * 32)
