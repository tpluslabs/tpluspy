#!/usr/bin/env python
from pathlib import Path

from setuptools import find_packages, setup

here = Path(__file__).parent.absolute()
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="tpluspy",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    description="""tpluspy: Client utilities for interacting with tplus""",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="TPlus Labs",
    author_email="admin@tlus.cx",
    url="https://github.com/tpluslabs/tpluspy",
    include_package_data=True,
    install_requires=[
        "cryptography>=44.0.1",
        "eth-pydantic-types>=0.2.2,<0.3",
        "eth-utils>=5.1.0,<6",
        "httpx>=0.20",
        "pycryptodome>=3.17.1",
        "pydantic>=2.10.4,<3",
        "websockets>=13.1,<14",
    ],
    python_requires=">=3.10,<4",
    extras_require={
        "test": [
            "pytest>=8.0",
            "pytest-timeout>=2.2.0,<3",
            "pytest-mock",
            "anyio>=4",
            "pytest-anyio>=0.0.0",
            "trio>=0.24",
        ],
        "lint": [
            "ruff>=0.11.7",
            "mypy>=1.18.2,<2",
        ],
        "release": [
            "setuptools>=75.6.0",
            "wheel",
            "twine",
        ],
        "evm": [
            "ape-tokens",
            "click",
            "eip712>=0.3.1",
            "eth-ape>=0.8.32,<0.9",
            "hexbytes>=1.3.1,<2",
        ],
    },
    py_modules=["tpluspy"],
    license="Apache-2.0",
    zip_safe=False,
    keywords="ethereum",
    packages=find_packages(exclude=["tests", "tests.*"]),
    package_data={"tpluspy": ["py.typed", "evm/manifests/*"]},
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Operating System :: MacOS",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)
