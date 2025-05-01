from ape import Contract, accounts

from tplus.contracts import DepositVault, Registry


def main():
    account = accounts.load("tplus-account")

    tokens = Registry().get_assets()

    # Ensure we have tokens.
    tokens[0].mint(account, "1 ether", sender=account)
    tokens[1].mint(account, "1 ether", sender=account)

    vault = DepositVault()  # Loads address from connected network

    # Approve the vault to spend the tokens first.
    tokens[0].approve(vault.contract, "1 ether", sender=account)
    tokens[1].approve(vault.contract, "1 ether", sender=account)

    # Deposit the tokens into your t+ account.
    vault.deposit(account, account, tokens[0], "1 ether", sender=account)
    vault.deposit(account, account, tokens[1], "1 ether", sender=account)

    # Now, you can check your deposits using another call.
    print(vault.getDeposits(0, account))


if __name__ == "__main__":
    main()
