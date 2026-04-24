"""
tests/test_parser.py — Unit tests for the C++ circuit_parser binary
====================================================================
WHAT IS TESTED:
    The circuit_parser binary (parser/circuit_parser) is an external process.
    Tests invoke it via subprocess and validate:
      - Binary exists (i.e. 'make -C parser' was run)
      - Output is valid JSON
      - Gate counts match the known sample_circuit.txt layout (19 gates)
      - Sequential / combinational split is correct (4 DFFs, 15 comb)
      - Area and power totals match hand-calculated values
      - Power density is positive (sanity check)
      - Per-type counts include DFF with count 4
      - "gates" list is present and matches total_gates
      - Fanout statistics are non-zero and consistent
      - Non-existent file input returns non-zero exit code

SAMPLE CIRCUIT (sample_circuit.txt):
    19 gates total: 4× DFF, 3× XOR2, 2× AND2, 2× OR2, 2× NAND2,
                    2× NOR2, 2× BUF, 2× INV
    Total area : 51.84 um²
    Total power: 70.10 uW
"""

import json
import subprocess
import os
import pytest

ROOT       = os.path.dirname(os.path.dirname(__file__))
PARSER_BIN = os.path.join(ROOT, "parser", "circuit_parser")
SAMPLE_TXT = os.path.join(ROOT, "sample_circuit.txt")


def test_parser_binary_exists():
    assert os.path.isfile(PARSER_BIN), "circuit_parser binary not found — run make"


def test_parser_returns_valid_json(sample_stats):
    assert isinstance(sample_stats, dict)


def test_gate_count(sample_stats):
    assert sample_stats["total_gates"] == 19


def test_seq_comb_split(sample_stats):
    assert sample_stats["sequential_gates"] == 4
    assert sample_stats["combinational_gates"] == 15


def test_total_area_approx(sample_stats):
    assert abs(sample_stats["total_area_um2"] - 51.84) < 0.1


def test_total_power_approx(sample_stats):
    assert abs(sample_stats["total_power_uW"] - 70.10) < 0.1


def test_power_density_positive(sample_stats):
    assert sample_stats["power_density_uW_um2"] > 0


def test_gate_type_counts_present(sample_stats):
    counts = sample_stats["gate_type_counts"]
    assert "DFF" in counts
    assert counts["DFF"] == 4


def test_gates_list_present(sample_stats):
    gates = sample_stats.get("gates", [])
    assert len(gates) == sample_stats["total_gates"]
    for g in gates:
        assert "name" in g and "type" in g and "area" in g and "power" in g


def test_fanout_stats(sample_stats):
    assert sample_stats["total_nets"] > 0
    assert sample_stats["avg_fanout"] > 0
    assert sample_stats["max_fanout"] >= 1


def test_missing_file_returns_nonzero():
    result = subprocess.run(
        [PARSER_BIN, "/nonexistent/file.txt"],
        capture_output=True, text=True
    )
    assert result.returncode != 0
