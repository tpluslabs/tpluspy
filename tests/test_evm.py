def test_settlement_order(signer, order):
    signature = signer.sign_message(order)
    assert signer.check_signature(order, signature)
