import pytest

from tplus.utils.universe import Universe, build_dev_universe_name, compute_universe_id


@pytest.fixture(scope="session")
def universe_vectors():
    """The universe IDs `tplus-contracts` checks its Solidity helper against."""
    return {
        "tplus-mainnet": "0x3bd9c7e6fb255efd993fafc42a4e17dad2d8094ae29b96a475797d1441e5e62e",
        "tplus-staging": "0x752bdcd9181857e3855dd35f11b56d35b7b40579ad54eafe656e7ced8bcd4d57",
        "tplus-dev-example": "0xb4e22ac07ba2415e72f4535db7385b0b874a5362c79ecbaac52ec3e989c7c1cb",
    }


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(Universe.MAINNET.value, id="mainnet"),
        pytest.param(Universe.STAGING.value, id="staging"),
        pytest.param(build_dev_universe_name("example"), id="dev-environment"),
    ],
)
def test_compute_universe_id_matches_contract_vectors(universe_vectors, name):
    assert compute_universe_id(name).to_0x_hex() == universe_vectors[name]
