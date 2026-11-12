import pytest

from tplus.model.config import ChainConfig


@pytest.mark.parametrize(
    "chain_id,block_time_ms,confirmations",
    [
        pytest.param(1, 12_000, 4, id="ethereum"),
        pytest.param(42_161, 1_000, 15, id="arbitrum"),
        pytest.param(143, 400, 15, id="monad"),
        pytest.param(8_453, 2_000, 10, id="base"),
    ],
)
def test_for_evm_chain_matches_production(chain_id, block_time_ms, confirmations):
    config = ChainConfig.for_evm_chain(chain_id)

    assert config == ChainConfig(
        blockTimeMs=block_time_ms,
        defaultConfirmations=confirmations,
        depositIngestConfirmations=confirmations,
        withdrawalIngestConfirmations=confirmations,
        settlementIngestConfirmations=0,
    )
    assert config.find_unexpected_zero_confirmations(config) == []


def test_find_unexpected_zero_confirmations_flags_zeros_production_does_not_set():
    production = ChainConfig.for_evm_chain(42_161)
    assert production is not None

    config = production.model_copy(update={"depositIngestConfirmations": 0})

    assert ChainConfig.for_evm_chain(10_143) is None
    assert config.find_unexpected_zero_confirmations(production) == ["depositIngestConfirmations"]
    assert ChainConfig.dev().find_unexpected_zero_confirmations(None) == [
        "defaultConfirmations",
        "depositIngestConfirmations",
        "withdrawalIngestConfirmations",
        "settlementIngestConfirmations",
    ]
