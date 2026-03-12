PYTHON ?= python3
VENV ?= .venv
ifeq ($(OS),Windows_NT)
BIN := $(VENV)/Scripts
else
BIN := $(VENV)/bin
endif

bootstrap:
	$(PYTHON) scripts/bootstrap.py --path .

up:
	$(BIN)/viki up --path .

test:
	$(BIN)/pytest -q

package:
	$(BIN)/python -m build
