"""Sphinx configuration for the specpol documentation (Markdown pages via MyST, Furo theme)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
import specpol  # noqa: E402

project = "specpol"
author = "Mirza Arnaut"
copyright = "2026, Mirza Arnaut"
version = release = specpol.__version__

extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.viewcode"]
myst_enable_extensions = ["colon_fence", "deflist"]
myst_heading_anchors = 3  # [text](page.md#heading) links

# The docs build without the camera stack (Aravis, PyAV, Streamlit), so autodoc mocks it.
autodoc_mock_imports = ["gi", "av", "anyio", "numpy", "PIL", "starlette", "streamlit", "tifffile"]
autodoc_member_order = "bysource"

exclude_patterns = ["_build"]
html_theme = "furo"
html_title = f"specpol {release}"
html_theme_options = {  # "view/edit this page" links
    "source_repository": "https://github.com/arunoruto/specpol/",
    "source_branch": "main",
    "source_directory": "docs/",
}
