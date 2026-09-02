"""Ape-only loading of the ``tplus-contracts`` Solidity project (used by the Ape backend)."""

import os
from typing import TYPE_CHECKING

from ape.exceptions import ProjectError
from ape.managers.project import Project
from ape.utils.basemodel import ManagerAccessMixin

from tplus.evm._manifest import _MANIFEST_PATH

if TYPE_CHECKING:
    from ape.contracts.base import ContractContainer
    from ape.managers.project import LocalProject


def load_tplus_contracts_project(version: str | None = None) -> "LocalProject":
    """
    Loads the Ape project containing the Solidity contracts for tplus.
    If you are in the tplus-contracts repo, it detects that and loads that way.
    Else, it checks all Ape installed dependencies. If it is not installed, it will fail.
    Install the tplus-contracts project by running ``ape pm install tpluslabs/tplus-contracts``.
    """
    if path := os.environ.get("TPLUS_CONTRACTS_PATH"):
        return Project(path)

    elif ManagerAccessMixin.local_project.name == "tplus-contracts":
        # Working from the t+ contracts repo
        return ManagerAccessMixin.local_project

    # Load the project from dependencies.
    try:
        project = _load_tplus_contracts_from_dependencies(version=version)
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


def _load_tplus_contracts_from_dependencies(version: str | None = None):
    available_versions = ManagerAccessMixin.local_project.dependencies["tplus-contracts"]
    if version:
        return available_versions[version]

    # Select first one.
    if not (version_key := next(iter(available_versions), None)):
        raise ProjectError("Please install the t+ contracts project")

    return available_versions[version_key]


def _load_tplus_contracts_from_manifest() -> Project:
    # Use manifest that comes with tpluspy.
    return Project.from_manifest(_MANIFEST_PATH)


def load_tplus_contract_container(name: str, version: str | None = None) -> "ContractContainer":
    project = load_tplus_contracts_project(version=version)
    contract = project.contracts.get(name)
    if contract is None:
        raise ValueError(f"Missing contract '{name}' from tplus contracts project.")

    return contract
