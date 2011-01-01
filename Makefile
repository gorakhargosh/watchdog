RM = rm -rf

.PHONY: all

all: build

help:
	@echo "Possible targets:"
	@echo "	   test        - run testsuite"
	@echo "    doc         - builds the documentation"
	@echo "	   view-doc    - opens documentation in the browser"
	@echo "	   upload-doc  - uploads the documentation to PyPI"
	@echo "	   develop	   - set up development environment"
	@echo "	   clean       - clean up generated files"
	@echo "	   release     - performs a release"
	@echo "	   auto        - continuous builds"

release: clean test upload-doc
	python setup.py sdist upload

build: doc
	@bin/python setup.py build

doc: develop
	@make SPHINXBUILD=../bin/sphinx-build -C docs/ html

upload-doc: doc
	@bin/python setup.py upload_docs --upload-dir=docs/build/html

view-doc: doc
	@bin/python -c "import webbrowser; webbrowser.open('docs/build/html/index.html')"

test:
	@bin/coverage erase
	@bin/python-tests tests/run_tests.py
	@bin/coverage html

auto: scripts/nosy.py
	@bin/python scripts/nosy.py .

# Development environment targets and dependencies.
develop: submodules bin/python

submodules:
	@git submodule update --init --recursive

bin/buildout: buildout.cfg setup.py
	@python scripts/bootstrap.py --distribute

bin/python: bin/buildout
	@bin/buildout

clean:
	@make -C docs/ clean > /dev/null
	@$(RM) build/ *.egg-info/
	@find . \( \
		-iname "*.pyc" \
		-or -iname "*.pyo" \
		-or -iname "*.so" \
		-or -iname "*.o" \
		-or -iname "*~" \
		-or -iname "._*" \
		-or -iname "*.swp" \
		-or -iname "Desktop.ini" \
		-or -iname "Thumbs.db" \
		-or -iname "__MACOSX__" \
		-or -iname ".DS_Store" \
		\) -delete

distclean: clean
	@$(RM) \
		dist/ \
		bin/ \
		develop-eggs/ \
		eggs/ \
		parts/ \
		MANIFEST \
		htmlcov/ \
		.pythoscope/ \
		.coverage \
		.installed.cfg
