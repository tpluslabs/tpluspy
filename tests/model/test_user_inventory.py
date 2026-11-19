from decimal import Decimal

from tplus.model.user_inventory import parse_user_inventory


def test_parse_funding_account_preserves_token_balances():
    token = "62622e77d1349face943c6e7d5c01c61465fe1dc000000000000000000000000@000000000000007a69"
    inventory = parse_user_inventory(
        {
            "accounts": {
                "0": {
                    "kind": "funding",
                    "spot_token_balances": {token: "12.5"},
                    "token_liabilities": {},
                },
            },
            "is_mm": False,
        }
    )

    assert set(inventory.accounts) == {0}
    funding = inventory.accounts[0]
    assert funding.kind == "funding"
    assert funding.spot_token_balances == {token: Decimal("12.5")}
    assert funding.spot_canonical_balances.spot_account_balance == {}
    assert funding.margin.margin_positions == {}
    assert inventory.is_mm is False
