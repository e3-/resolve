# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import pathlib
import sys

from sphinxawesome_theme.postprocess import Icons

print(pathlib.Path(__file__).parents[2] / "tests")
sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Kit"
copyright = "2024, Energy & Environmental Economics, Inc."
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
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
# exclude_patterns = []

# Intentionally not inheriting all autodoc members, because I want to be able to control what pydantic model
# attributes are shown (e.g., not attrs inherited from`Component` or `CustomModel`)
autodoc_default_options = {
    "inherited-members": False,
}

autodoc_pydantic_field_list_validators = False
autodoc_pydantic_model_show_config_member = False
autodoc_pydantic_model_show_config_summary = False
autodoc_pydantic_model_show_json = False
autodoc_pydantic_model_show_validator_members = False
autodoc_pydantic_model_show_validator_summary = False
autodoc_pydantic_model_signature_prefix = "class"

add_module_names = False
toc_object_entries_show_parents = "hide"

intersphinx_mapping = {"pandas": ("https://pandas.pydata.org/pandas-docs/stable/", None)}
myst_url_schemes = ["https"]

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinxawesome_theme"
html_favicon = "e3-logo.ico"


# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]
html_css_files = ["css/e3.css"]

html_title = "Kit"
html_permalinks_icon = Icons.permalinks_icon

html_sidebars = {
    "branding": ["sidebar_main_nav_links.html"],
    "dev": ["sidebar_main_nav_links.html"],
    "roadmap": ["sidebar_main_nav_links.html"],
}

html_theme_options = {
    "awesome_external_links": True,
    "breadcrumbs_separator": Icons.chevron_right,
    "logo_dark": "_static/logos/kit-dark.svg",
    "logo_light": "_static/logos/kit-light.svg",
    "main_nav_links": {
        "Branding": "branding",
        "Development Guide": "dev",
        "Changelog & Roadmap": "roadmap",
    },
    "show_breadcrumbs": True,
    "show_prev_next": True,
    "show_scrolltop": True,
}

graphviz_output_format = "svg"


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
    sphinx-apidoc -f -o source [absolute path to new_modeling_toolkit directory]
2. Convert the .rst files to .md using the command rst2myst 
   (https://docs.readthedocs.io/en/stable/guides/migrate-rest-myst.html#how-to-convert-existing-restructuredtext-documentation-to-myst)
2. Add text to the .md files manually for more documentation
3. Run `make html` to update the HTML files
4. Run `make latex` to update LaTeX files

https://ethreesf.sharepoint.com/sites/Training/_layouts/OneNote.aspx?id=%2Fsites%2FTraining%2FSiteAssets%2FTraining%20Notebook&wd=target%28Technical%20Skills%20Training%2FPython.one%7C916C3A04-A4B3-4112-9E7F-F2F503E5B87C%2FDocumentation%20%26%20Docstrings%7C72764774-57EE-4BC6-8496-E63524712FF6%2F%29
"""
