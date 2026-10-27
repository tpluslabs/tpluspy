import pytest

from tplus.utils import timeout
from tplus.utils.timeout import wait_for_condition


async def refresh():
    return None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "waits,expected_sleeps",
    [
        pytest.param({}, [1, 1, 1], id="one-second-by-default"),
        pytest.param(
            {"initial_wait_ns": 50_000_000, "inc_wait_ns": 100_000_000},
            [0.05, 0.1, 0.1],
            id="initial-then-inc",
        ),
        pytest.param({"interval": 0.5}, [0.5, 0.5, 0.5], id="former-interval"),
        pytest.param(
            {"interval": 0.5, "inc_wait_ns": 100_000_000},
            [0.5, 0.1, 0.1],
            id="inc-wins-over-interval",
        ),
    ],
)
async def test_wait_for_condition_sleeps(mocker, waits, expected_sleeps):
    sleep = mocker.patch.object(timeout.asyncio, "sleep", new=mocker.AsyncMock())
    readings = iter([False, False, False, True])

    async def fetch_reading():
        return next(readings)

    await wait_for_condition(refresh, fetch_reading, bool, **waits)

    assert [call.args[0] for call in sleep.await_args_list] == expected_sleeps


@pytest.mark.anyio
async def test_wait_for_condition_unknown_keyword():
    with pytest.raises(TypeError, match="intervall"):
        await wait_for_condition(refresh, refresh, bool, intervall=1)
