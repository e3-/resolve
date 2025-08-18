from sphinx.application import Sphinx

_SOURCE_DIR = "./source"
_CONFIG_DIR = "./source"
_OUTPUT_DIR = "./build"
_DOCTREE_DIR = "./build/doctrees"


def test_html_docs_build():
    """Simple test that the HTML docs can build (mainly a test that the dev dependencies still work.

    TODO: In the future, we could switch on `warningiserror` to force devs to address any Sphinx errors (e.g., missing reference targets)
    """
    app = Sphinx(_SOURCE_DIR, _CONFIG_DIR, _OUTPUT_DIR, _DOCTREE_DIR, buildername="html", warningiserror=False)
    app.build(force_all=True)


## Update
