# CircuitSense — root Makefile
# Convenience targets for common operations

PYTHON  = .venv/bin/python3
PIP     = .venv/bin/pip
PYTEST  = .venv/bin/pytest

.PHONY: all setup build test run run-verilog clean help

all: setup

## setup   : full one-shot setup (venv + deps + C++ build)
setup:
	bash setup.sh

## build   : compile C++ tools only
build:
	make -C parser

## test    : run all 45 pytest tests
test:
	$(PYTEST) tests/ -v

## cov     : run tests with coverage report
cov:
	$(PYTEST) tests/ --cov=vlsi --cov-report=term-missing

## run     : analyse sample circuit (no LLM)
run:
	$(PYTHON) main.py --no-llm

## run-v   : analyse full adder Verilog (no LLM)
run-v:
	$(PYTHON) main.py samples/full_adder_gate.v --no-llm

## llm     : full run with LLM (needs ANTHROPIC_API_KEY)
llm:
	$(PYTHON) main.py

## clean   : remove compiled binaries and generated output
clean:
	make -C parser clean
	rm -rf output/
	find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

## help    : show this help
help:
	@grep -E '^##' Makefile | sed 's/## /  /'
