# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import os
import sys

sys.path.insert(0, os.path.abspath("../../new_modeling_toolkit"))

# -- Project information -----------------------------------------------------

project = "Resolve"
copyright = "2023, Energy & Environmental Economics, Inc."
author = "Energy & Environmental Economics, Inc."


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "myst_parser",
    "sphinxawesome_theme.highlighting",
    "sphinxcontrib.mermaid",
    "sphinx.ext.autodoc",
    "sphinx.ext.graphviz",
    "sphinx.ext.intersphinx",
    "sphinx.ext.mathjax",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinxcontrib.autodoc_pydantic",
    "sphinx_design",
    "sphinx_last_updated_by_git",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["../_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
# exclude_patterns = []

add_module_names = False
toc_object_entries_show_parents = "hide"


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "furo"
html_favicon = "_images/e3-logo.ico"


# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]
html_css_files = ["css/furo-e3.css"]

html_title = "RESOLVE"

html_theme_options = {
    "light_css_variables": {
        "color-brand-primary": "#034E6E",  # The standard E3 dark blue
        "color-brand-background": "#E2ECF0",  # The E3 light blue/grey background color
        "color-brand-dropdown": "white",
    },
    "light_logo": "resolve-logo-light.svg",
    "dark_css_variables": {
        "color-brand-primary": "#C4AD73",
        "color-brand-background": "#212529",  # Same as sphinx-design --sd-color-dark
        "color-brand-dropdown": "#212529",  # Same as sphinx-design --sd-color-dark
    },
    "dark_logo": "resolve-logo-dark.svg",
    "sidebar_hide_name": True,
    "top_of_page_button": "edit",
}


# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
# html_static_path = ["_static"]
add_module_names = False

suppress_warnings = ["myst.header", "git.too_shallow"]


myst_enable_extensions = [
    "amsmath",
    "attrs_inline",
    "colon_fence",
    "dollarmath",
    "substitution",
]

latex_elements = {"extrapackages": "\\usepackage{amsmath}"}

# ------------ Mermaid configuration --------------------------------
mermaid_d3_zoom = True


# -- Instructions for how to update ------------------------------------------
"""
1. If you need to update the autodoc files (e.g., structure changes),
   run the following command from the docs/ directory
    sphinx-apidoc -f -o source [absolute path to src directory]
2. Add text to the RST files manually for more documentation
3. Run make html to update the HTML files
4. Run make latex to update LaTeX files

https://ethreesf.sharepoint.com/sites/Training/_layouts/OneNote.aspx?id=%2Fsites%2FTraining%2FSiteAssets%2FTraining%20Notebook&wd=target%28Technical%20Skills%20Training%2FPython.one%7C916C3A04-A4B3-4112-9E7F-F2F503E5B87C%2FDocumentation%20%26%20Docstrings%7C72764774-57EE-4BC6-8496-E63524712FF6%2F%29
"""
