import asyncio

import pytest

from tplus._cli import cli

from .conftest import APE_ACCOUNT, BASE_ARGS, NETWORK

pytestmark = [pytest.mark.integration, pytest.mark.timeout(90)]


INITIAL_WETH_DEPOSIT = 400 * 10**18
SETTLE_AMOUNT_WETH = 100 * 10**18
SETTLE_AMOUNT_USDC = 100 * 10**6
EXPECTED_SPOT_WETH = INITIAL_WETH_DEPOSIT - SETTLE_AMOUNT_WETH
EXPECTED_SPOT_USD = 100 * 10**18


@pytest.mark.integration
def test_settle_weth_out_usdc_in(runner, env, tplus_cli):
    tplus_cli(
        [
            "deposit",
            env.weth.address,
            "--amount",
            str(INITIAL_WETH_DEPOSIT),
            "--wait",
            *BASE_ARGS,
        ],
    )

    env.settler_executor.setReturnAmount(SETTLE_AMOUNT_USDC, sender=env.admin)

    result = runner.invoke(
        cli,
        [
            "settle",
            "execute",
            "--network",
            NETWORK,
            "--account",
            APE_ACCOUNT,
            "--asset-in",
            str(env.usdc.tplus_address),
            "--amount-in",
            str(SETTLE_AMOUNT_USDC),
            "--amount-in-decimals",
            "6",
            "--asset-out",
            str(env.weth.tplus_address),
            "--amount-out",
            str(SETTLE_AMOUNT_WETH),
            "--amount-out-decimals",
            "18",
            "--mode",
            "SPOT",
            "--settler-executor",
            env.settler_executor.address,
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Settlement executed" in result.output

    async def _verify():
        env.ce_client = env._fresh_ce()
        await env.verify_inventory(
            sub_account=0,
            asset=env.weth.asset_identifier,
            spot=True,
            expected_amount=EXPECTED_SPOT_WETH,
            expected_spot_usd=EXPECTED_SPOT_USD,
        )

    asyncio.run(_verify())
