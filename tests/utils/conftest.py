import pytest


@pytest.fixture
def private_key_hex() -> str:
    return "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"


@pytest.fixture
def public_key_hex() -> str:
    return "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"


@pytest.fixture
def expected_sig_hex() -> str:
    return (
        "8ac3a00dd2fd15fc8d15da0c9d6be551402a252e3bf3e7cb96898a33a431cca"
        "26028f5fc0593d9d36909fce914bacb9c0d845146274f74a99f558cac5a4ffc02"
    )


@pytest.fixture
def password() -> str:
    return "hunter2"
