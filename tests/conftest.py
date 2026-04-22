"""Shared pytest fixtures."""

import json
import os
import subprocess
import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
PARSER_BIN = os.path.join(ROOT, "parser", "circuit_parser")
STA_BIN    = os.path.join(ROOT, "parser", "sta_engine")
SAMPLE_TXT = os.path.join(ROOT, "sample_circuit.txt")
SAMPLE_V   = os.path.join(ROOT, "samples", "full_adder_gate.v")


@pytest.fixture(scope="session")
def sample_stats():
    """Run circuit_parser on sample_circuit.txt and return parsed JSON."""
    result = subprocess.run(
        [PARSER_BIN, SAMPLE_TXT], capture_output=True, text=True
    )
    assert result.returncode == 0, f"Parser failed: {result.stderr}"
    return json.loads(result.stdout)


@pytest.fixture(scope="session")
def sample_timing():
    """Run sta_engine on sample_circuit.txt and return parsed JSON."""
    result = subprocess.run(
        [STA_BIN, SAMPLE_TXT, "--period", "10.0"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"STA failed: {result.stderr}"
    return json.loads(result.stdout)


@pytest.fixture(scope="session")
def full_adder_gates():
    """Parse the full_adder_gate.v Verilog sample."""
    from vlsi.verilog_parser import parse_verilog
    return parse_verilog(SAMPLE_V)
