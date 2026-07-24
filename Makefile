.PHONY: install upgrade test build

install:
	pipx install .

upgrade:
	pipx install --force .

test:
	python3 -m unittest discover -s tests -v

build:
	python3 -m build
