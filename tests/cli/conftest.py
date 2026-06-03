import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from tplus.client import ClearingEngineClient
from tplus.utils.user.manager import UserManager

PRIVATE_KEY_HEX = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
PUBLIC_KEY_HEX = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
PASSWORD = "hunter2"

CE_URL = "http://127.0.0.1:3032"
OMS_URL = "https://127.0.0.1:8000"
NETWORK = "ethereum:local:foundry"
APE_ACCOUNT = "TEST::0"
CHAIN_ID_EVM = 31337
BASE_ARGS = ["--network", NETWORK, "--account", APE_ACCOUNT]

BOOTSTRAP_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "dev-bootstrap.sh"


@pytest.fixture
def user_dir(tmp_path, monkeypatch):
    data = tmp_path / "users"

    def _init(self):
        self._data_folder = data
        self._default_user = None

    monkeypatch.setattr(UserManager, "__init__", _init)
    monkeypatch.setenv("TPLUS_PASSWORD", PASSWORD)
    return data


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli_env(monkeypatch, user_dir):
    monkeypatch.setenv("TPLUS_ACCOUNT", "settler")
    monkeypatch.setenv("TPLUS_CLEARING_BASE_URL", CE_URL)
    monkeypatch.setenv("TPLUS_ORDERBOOK_BASE_URL", OMS_URL)
    monkeypatch.setenv("TPLUS_IGNORE_SSL", "1")
    monkeypatch.setenv("TPLUS_DEFAULT_BLOCKCHAIN_NETWORK", NETWORK)


@pytest.fixture
def settler_user(runner, cli_env):
    from tplus._cli import cli

    result = runner.invoke(cli, ["accounts", "generate", "settler"])
    assert result.exit_code == 0, result.output
    return UserManager().load("settler")


@pytest.fixture
def tplus_cli(runner):
    from tplus._cli import cli

    def _run(argv: list[str]) -> str:
        result = runner.invoke(cli, argv)
        assert result.exit_code == 0, f"tplus {' '.join(argv)} failed:\n{result.output}"
        return result.output

    return _run


@pytest.fixture
def env(tplus_cli, settler_user, cli_env):
    # ape / tplus.evm are the optional ``[evm]`` extra — kept local so the core
    # (non-evm) test job can still collect this module.
    from ape import networks

    from tplus.evm.contracts import DepositVault
    from tplus.evm.dev import DeveloperEnvironment

    with networks.ethereum.local.use_provider("foundry"):
        bootstrap = subprocess.run(
            ["bash", str(BOOTSTRAP_SCRIPT)],
            env={
                **os.environ,
                "TPLUS_CLEARING_BASE_URL": CE_URL,
                "TPLUS_IGNORE_SSL": "1",
                "CHAIN_ID": str(CHAIN_ID_EVM),
                "APE_NETWORK": NETWORK,
                "APE_ACCOUNT": APE_ACCOUNT,
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert bootstrap.returncode == 0, (
            f"dev-bootstrap.sh failed:\nstdout:\n{bootstrap.stdout}\nstderr:\n{bootstrap.stderr}"
        )
        addresses = _parse_bootstrap_exports(bootstrap.stdout)

        deposit_vault = DepositVault(address=addresses["DEPOSIT_VAULT"])
        dev_env = DeveloperEnvironment(
            settler_user,
            _fresh_ce(settler_user),
            deposit_vault=deposit_vault,
        )
        dev_env._fresh_ce = lambda: _fresh_ce(settler_user)  # type: ignore[attr-defined]

        usdc = dev_env.usdc
        weth = dev_env.weth

        # Any deposit above ``max_deposits`` gets downgraded to
        # ``AssetIdentifier::Address`` (isolated) by the CE, which then
        # resolves to default risk params (``max_collateral=0``).
        huge_raw_cap = 10**30
        for index, token in ((0, usdc), (1, weth)):
            tplus_cli(
                [
                    "assets",
                    "set",
                    str(index),
                    token.address,
                    "--chain-id",
                    str(CHAIN_ID_EVM),
                    "--max-deposit",
                    str(huge_raw_cap),
                    "--max-1hr",
                    str(huge_raw_cap),
                    "--min-weight",
                    "1200000",
                    *BASE_ARGS,
                ],
            )

        tplus_cli(["decimals", "update", f"{usdc.asset_address}", f"{weth.asset_address}"])

        # Risk params must go through the Registry — the CE overwrites its
        # whole map from on-chain on every sync, so the admin shortcut
        # (``/admin/risk-parameters/modify``) gets clobbered.
        params = _permissive_risk_params_struct()
        params_json = json.dumps(params)
        for index in (0, 1):
            tplus_cli(["params", "set", str(index), "--params", params_json, *BASE_ARGS])
            tplus_cli(["params", "apply", str(index), *BASE_ARGS])
        tplus_cli(["params", "update-ce"])
        _wait_for_ce_risk_params(settler_user, (0, 1), params["maxCollateral"])

        # ``executeAtomicSettlement`` dispatches ``onAtomicSettlement`` back
        # into ``msg.sender``, so the executor has to be a contract.
        settler_executor = dev_env.settler_executor
        tplus_cli(
            [
                "vaults",
                "register-settler",
                "settler",
                "--executor",
                settler_executor.address,
                "--wait",
                *BASE_ARGS,
            ],
        )

        for token in (usdc, weth):
            mint_amount = 1_000_000 * 10 ** token.contract.decimals()
            token.contract.mint(dev_env.admin, mint_amount, sender=dev_env.admin)
            token.contract.mint(dev_env.deposit_vault, mint_amount, sender=dev_env.admin)
            token.contract.approve(dev_env.deposit_vault, mint_amount, sender=dev_env.admin)
            token.contract.mint(settler_executor, mint_amount, sender=dev_env.admin)
            token.contract.approve(dev_env.deposit_vault, mint_amount, sender=settler_executor)

        tplus_cli(["vaults", "register-depositor", dev_env.admin.address, *BASE_ARGS])

        yield dev_env


def _fresh_ce(user):
    # ``httpx.AsyncClient`` binds to the running event loop on first request,
    # so reusing one across ``asyncio.run`` calls fails with "Event loop is closed".
    return ClearingEngineClient(base_url=CE_URL, default_user=user, insecure_ssl=True)


def _parse_bootstrap_exports(stdout: str) -> dict[str, str]:
    exports: dict[str, str] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("export ") and "=" in line:
            key, _, value = line[len("export ") :].partition("=")
            exports[key] = value
    return exports


def _wait_for_ce_risk_params(user, indexes, expected_max_collateral: int, timeout: float = 10.0):
    # ``params/update`` is fire-and-forget, so poll until the CE reflects
    # the Registry write before any test trades.
    async def _once():
        return await _fresh_ce(user).assets.get_risk_parameters()

    deadline = time.time() + timeout
    params: dict = {}
    while time.time() < deadline:
        params = asyncio.run(_once())
        if all(
            int(params.get(str(idx), {}).get("max_collateral", "0") or 0) == expected_max_collateral
            for idx in indexes
        ):
            return
        time.sleep(0.25)
    raise AssertionError(f"CE did not ingest risk params within {timeout}s (saw {params!r})")


def _permissive_risk_params_struct() -> dict:
    # camelCase matches ``Registry.RiskParameters`` so ape encodes directly.
    # on-chain ``validateRiskParameters`` checks: kinks start 0, increase,
    # end at 1_000_000; bufferMultiple in [1e6, 2e6]; funding/util rates <= 1142.
    huge = 10**30
    kinks = [0, 400000, 700000, 850000, 950000, 1000000]
    rates = [0, 20000, 50000, 100000, 300000, 1000000]

    return {
        "collateralFactor": 75,
        "liabilityFactor": 50,
        "maxCollateral": huge,
        "maxOpenInterest": huge,
        "maxSpotOpenInterest": huge,
        "maxUtilization": 800000000000000000,
        "isolatedOnly": False,
        "interestKinks": kinks,
        "kinkInterestRates": rates,
        "usdInterestKinks": kinks,
        "usdKinkInterestRates": rates,
        "skewModifier": 9000,
        "skewCliff": 500,
        "baseFundingRate": 500,
        "premiumClamp": 500,
        "initialMarginClamps": [0, 500000],
        "initialMarginFactors": [980000, 0],
        "maxFundingRate": 1000,
        "maxUtilizationRate": 1000,
        "bufferMultiple": 1200000,
    }
