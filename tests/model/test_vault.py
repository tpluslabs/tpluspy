from tplus.model.chain_address import ChainAddress
from tplus.model.vault import ChildManager


def test_child_manager_chain_address_reads_the_clearing_engine_response():
    manager_address = "ab" * 20
    child_manager = ChildManager.model_validate(
        {"routing_id": 0, "vm_id": "10143", "manager": f"0x{manager_address}{'00' * 12}"}
    )

    assert child_manager.chain_address == ChainAddress.from_evm_address(manager_address, 10_143)
