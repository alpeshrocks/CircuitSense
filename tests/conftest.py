"""
tests/conftest.py — Shared pytest fixtures for CircuitSense test suite
======================================================================
PURPOSE:
    Provides session-scoped fixtures that are expensive to compute
    (subprocess calls, file I/O) and should only run once per test session,
    not once per test function. pytest automatically discovers this file and
    makes all fixtures defined here available to every test module.

SESSION SCOPE:
    All three fixtures use scope="session" so the C++ binaries are invoked
    only once regardless of how many test functions consume the fixture.
    This keeps the test suite fast (~2s total) even as more tests are added.

FIXTURES:
    sample_stats   — dict from circuit_parser run on sample_circuit.txt
    sample_timing  — dict from sta_engine run on sample_circuit.txt
    full_adder_gates — list of gate dicts from parsing full_adder_gate.v

PREREQUISITES:
    C++ binaries must be compiled before running tests:
        make -C parser
    Python venv must be active with requirements-dev.txt installed.
"""

import json
import os
import subprocess
import pytest

# Absolute paths — tests can be run from any directory
ROOT       = os.path.dirname(os.path.dirname(__file__))
PARSER_BIN = os.path.join(ROOT, "parser", "circuit_parser")
STA_BIN    = os.path.join(ROOT, "parser", "sta_engine")
SAMPLE_TXT = os.path.join(ROOT, "sample_circuit.txt")
SAMPLE_V   = os.path.join(ROOT, "samples", "full_adder_gate.v")


@pytest.fixture(scope="session")
def sample_stats() -> dict:
    """
    Run circuit_parser on sample_circuit.txt and return the parsed JSON dict.

    Invokes the C++ binary as a subprocess, captures stdout, and parses JSON.
    Fails immediately with a clear message if the binary returns a non-zero
    exit code (e.g. if make -C parser was not run first).

    Returns:
        Dict matching the circuit_parser JSON schema:
        total_gates, combinational_gates, sequential_gates, total_area_um2,
        total_power_uW, power_density_uW_um2, gate_type_counts,
        gate_type_power_uW, gate_type_area_um2, gates list, etc.
    """
    result = subprocess.run(
        [PARSER_BIN, SAMPLE_TXT],
        capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"circuit_parser failed (exit {result.returncode}).\n"
        f"Stderr: {result.stderr}\n"
        f"Did you run 'make -C parser'?"
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="session")
def sample_timing() -> dict:
    """
    Run sta_engine on sample_circuit.txt with a 10 ns target period.

    Returns:
        Dict matching the sta_engine JSON schema:
        target_period_ns, critical_path_ns, max_frequency_mhz, timing_met,
        wns_ns, tns_ns, wns_gate, critical_path list, gate_timing list.
    """
    result = subprocess.run(
        [STA_BIN, SAMPLE_TXT, "--period", "10.0"],
        capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"sta_engine failed (exit {result.returncode}).\n"
        f"Stderr: {result.stderr}"
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="session")
def full_adder_gates() -> list[dict]:
    """
    Parse samples/full_adder_gate.v and return the list of gate dicts.

    The full adder has exactly 5 gates: 2× XOR2, 2× AND2, 1× OR2.
    Multiple tests use this fixture to verify different aspects of parsing.

    Returns:
        List of gate dicts with keys: name, type, area, power, drive,
        output_net, input_nets.
    """
    from vlsi.verilog_parser import parse_verilog
    return parse_verilog(SAMPLE_V)
