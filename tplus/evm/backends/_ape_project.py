"""Ape-only loading of the ``tplus-contracts`` Solidity project (used by the Ape backend)."""

import os
from typing import TYPE_CHECKING

from ape.exceptions import ProjectError
from ape.managers.project import Project
from ape.utils.basemodel import ManagerAccessMixin

from tplus.evm._manifest import _MANIFEST_PATH

if TYPE_CHECKING:
    from ape.contracts.base import ContractContainer
    from ape.managers.project import LocalProject, ProjectManager


def load_tplus_contracts_project(
    version: str | None = None, allow_install: bool | None = None
) -> "LocalProject":
    """
    Loads the Ape project containing the Solidity contracts for tplus.
    If you are in the tplus-contracts repo, it detects that and loads that way.
    Else, it checks all Ape installed dependencies. If it is not installed, it will fail.
    Install the tplus-contracts project by running ``ape pm install tpluslabs/tplus-contracts``,
    or pass ``allow_install=True`` (default: the ``TPLUS_CONTRACTS_ALLOW_INSTALL`` env var)
    to let Ape install it on load.
    """
    if path := os.environ.get("TPLUS_CONTRACTS_PATH"):
        return Project(path)

    elif ManagerAccessMixin.local_project.name == "tplus-contracts":
        # Working from the t+ contracts repo
        return ManagerAccessMixin.local_project

    # Load the project from dependencies.
    try:
        project = _load_tplus_contracts_from_dependencies(
            version=version, allow_install=_resolve_allow_install(allow_install)
        )
    except Exception:
        if version:
            # If specifying a version, this has to have worked or else it is a mistake.
            raise

        # Use manifest that comes with tpluspy.
        project = _load_tplus_contracts_from_manifest()

    try:
        project.load_contracts()  # Ensure is compiled.
    except Exception:
        if version:
            # If specifying a version, this has to have worked or else it is a mistake.
            raise

        # Compiling failed for some reason. Just use the manifest, which is already compiled.
        project = _load_tplus_contracts_from_manifest()

    return project


def _resolve_allow_install(allow_install: bool | None) -> bool:
    if allow_install is not None:
        return allow_install

    return os.environ.get("TPLUS_CONTRACTS_ALLOW_INSTALL", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _load_tplus_contracts_from_dependencies(
    version: str | None = None, allow_install: bool = False
) -> "ProjectManager":
    """
    The installed ``tplus-contracts`` dependency, at ``version`` or the first one.

    By default only an installed dependency is used. Resolving one Ape knows of but
    has not installed makes Ape fetch it: a GitHub API call and a clone on every load,
    which stalls for a minute each time the unauthenticated API quota is spent
    and never installs anything where the clone cannot authenticate. With
    ``allow_install``, Ape installs it instead.
    """
    dependencies = ManagerAccessMixin.local_project.dependencies
    if version:
        dependency = dependencies.get_dependency(
            "tplus-contracts", version, allow_install=allow_install
        )
    else:
        dependency = next(
            (
                candidate
                for candidate in dependencies.get_versions(
                    "tplus-contracts", allow_install=allow_install
                )
                if candidate.installed
            ),
            None,
        )

    if dependency is None or not dependency.installed:
        raise ProjectError(
            "The t+ contracts project is not installed; "
            "run `ape pm install tpluslabs/tplus-contracts`"
        )

    return dependency.project


def _load_tplus_contracts_from_manifest() -> Project:
    # Use manifest that comes with tpluspy.
    return Project.from_manifest(_MANIFEST_PATH)


def load_tplus_contract_container(
    name: str, version: str | None = None, allow_install: bool | None = None
) -> "ContractContainer":
    project = load_tplus_contracts_project(version=version, allow_install=allow_install)
    contract = project.contracts.get(name)
    if contract is None:
        raise ValueError(f"Missing contract '{name}' from tplus contracts project.")

    return contract
