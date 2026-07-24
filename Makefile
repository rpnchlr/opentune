.PHONY: install upgrade test

install:
	pipx install .

upgrade:
	pipx install --force .

test:
	python3 -m unittest discover -s tests -v
