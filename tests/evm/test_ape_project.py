import pytest

pytest.importorskip("ape")

from ape.utils._github import github_client  # noqa: E402

from tplus.evm.backends._ape_project import load_tplus_contracts_project  # noqa: E402


def test_loading_the_contracts_never_reaches_github(monkeypatch):
    """
    The ``tplus-contracts`` dependency is declared but not installed here, and
    installing it is the user's step: loading the project falls back to the
    bundled manifest without a GitHub API call or a clone, which would stall
    for a minute whenever the unauthenticated API quota is spent.
    """
    reached = []

    def offline(name):
        def reach(*_args, **_kwargs):
            reached.append(name)
            raise RuntimeError("offline")

        return reach

    for name in ("get_repo", "clone_repo", "download_package"):
        monkeypatch.setattr(github_client, name, offline(name))

    project = load_tplus_contracts_project()

    assert reached == []
    assert project.contracts.get("DepositVault") is not None


@pytest.mark.parametrize(
    ("env", "allow_install", "expected"),
    [
        (None, None, False),
        ("1", None, True),
        ("true", None, True),
        ("0", None, False),
        ("1", False, False),
        (None, True, True),
    ],
)
def test_installing_the_contracts_is_opt_in(monkeypatch, env, allow_install, expected):
    """
    Ape installs a missing ``tplus-contracts`` dependency only when asked, by the
    ``allow_install`` argument or else the ``TPLUS_CONTRACTS_ALLOW_INSTALL`` env var.
    """
    from ape.managers.project import DependencyManager

    asked = []

    def get_versions(_self, _name, allow_install=True):
        asked.append(allow_install)
        return iter(())

    monkeypatch.setattr(DependencyManager, "get_versions", get_versions)
    if env is None:
        monkeypatch.delenv("TPLUS_CONTRACTS_ALLOW_INSTALL", raising=False)
    else:
        monkeypatch.setenv("TPLUS_CONTRACTS_ALLOW_INSTALL", env)

    load_tplus_contracts_project(allow_install=allow_install)

    assert asked == [expected]
