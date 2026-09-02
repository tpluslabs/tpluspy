import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_MANIFEST_PATH = Path(__file__).parent / "manifests" / "tplus-contracts.json"


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    """The bundled ``tplus-contracts`` ethPM manifest."""
    return json.loads(_MANIFEST_PATH.read_text())


def get_contract_type(name: str) -> dict[str, Any]:
    """The raw ethPM ``contractType`` entry for ``name`` (ABI, bytecode, ...)."""
    contract_types = load_manifest().get("contractTypes", {})
    try:
        return contract_types[name]
    except KeyError as err:
        available = ", ".join(sorted(contract_types)) or "<none>"
        raise KeyError(
            f"Contract '{name}' not found in the bundled tplus-contracts manifest. "
            f"Available: {available}."
        ) from err


def get_abi(name: str) -> list[dict[str, Any]]:
    """The ABI for the named t+ contract."""
    return list(get_contract_type(name).get("abi", []))


def get_deployment_bytecode(name: str) -> bytes:
    """The creation bytecode for the named t+ contract."""
    return _bytecode_to_bytes(get_contract_type(name).get("deploymentBytecode"), name)


def _bytecode_to_bytes(raw: Any, name: str) -> bytes:
    if isinstance(raw, dict):
        raw = raw.get("bytecode")

    if not isinstance(raw, str) or not raw:
        raise ValueError(f"Contract '{name}' has no deployment bytecode in the manifest.")

    return bytes.fromhex(raw.removeprefix("0x"))
