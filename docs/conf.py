# Configuration file for the Sphinx documentation builder.
#
# Full reference: https://www.sphinx-doc.org/en/master/usage/configuration.html

import sys
from pathlib import Path

# Make tpluspy importable for autodoc.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

project = "tpluspy"
author = "TPlus Labs"
copyright = "TPlus Labs"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

# Source file suffixes.
source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}

# MyST configuration -- enable a useful set of extensions for user guides.
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "linkify",
    "smartquotes",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

# Autodoc configuration.
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_typehints = "description"
autoclass_content = "class"

# Napoleon: parse Google-style docstrings.
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_use_param = True
napoleon_use_rtype = True
# Render "Attributes:" sections as ``:ivar:`` fields so they don't generate
# their own ``.. attribute::`` directives that collide with the autodoc-generated
# entries for the same Pydantic fields.
napoleon_use_ivar = True

# Cross-project references.
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# HTML theme.
html_theme = "sphinx_rtd_theme"
html_title = "tpluspy"

# Do not fail the build if optional ``evm`` dependencies are missing -- the
# evm subpackage is documented but the heavy ``ape``/``eip712`` dependencies
# may not be installed in the docs environment.
autodoc_mock_imports = [
    "ape",
    "ape_tokens",
    "eip712",
    "eth_ape",
    "hexbytes",
]
