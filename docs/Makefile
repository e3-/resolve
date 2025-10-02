# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = build
NMTDIR        ?= ../new_modeling_toolkit
UMLDIR        = "$(NMTDIR)/uml/"

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Add `github` as an option: https://github.com/sphinx-doc/sphinx/issues/3382#issuecomment-470772316
github:
	@make html
	@cp -a build/html/. ../docs

# Generate UML diagrams from Python source that are viewable
# 	using Graphviz Interactive Preview (Visual Studio Code Extension)
# Windows example:
#   (kit-dev) C:\...\kit\docs> make.exe uml_dot
# Linux example:
#   (kit-dev) usr@machine:<some path>/kit/docs$ make uml_dot
uml_dot:
	pyreverse $(NMTDIR)/recap   -s 1 -a 1 -my -p recap -o="dot" --output-directory $(UMLDIR)
	pyreverse $(NMTDIR)/resolve -s 1 -a 1 -my -p resolve -o="dot" --output-directory $(UMLDIR)
	pyreverse $(NMTDIR)/system  -s 1 -a 1 -my -p system -o="dot" --output-directory $(UMLDIR)
	pyreverse $(NMTDIR)/core    -s 1 -a 1 -my -p core -o="dot" --output-directory $(UMLDIR)
	pyreverse $(NMTDIR)/ui      -s 1 -a 1 -my -p ui -o="dot" --output-directory $(UMLDIR)




# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)