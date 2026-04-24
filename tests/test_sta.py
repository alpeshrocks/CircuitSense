"""
tests/test_sta.py — Unit tests for the C++ sta_engine binary
=============================================================
WHAT IS TESTED:
    The sta_engine binary (parser/sta_engine) is tested via subprocess.
    Tests validate:
      - Binary exists after 'make -C parser'
      - Output is valid JSON
      - All required timing keys are present in the output
      - Critical path is non-empty and delay is positive
      - Max frequency is a positive non-zero value
      - Timing is PASS with a generous 100 ns period
      - Timing is FAIL with a 0.001 ns (near-zero) period
      - Every gate in the netlist appears in gate_timing list
      - slack = required - arrival holds for every gate (STA math check)

STA CORRECTNESS CHECK:
    The test test_slack_equals_rat_minus_at() verifies the fundamental
    STA invariant: slack[g] = RAT[g] - AT[g] for all gates.
    This validates the backward-pass implementation in sta_engine.cpp.
"""

import json
import subprocess
import os
import pytest

ROOT    = os.path.join(os.path.dirname(__file__), "..")
STA_BIN = os.path.normpath(os.path.join(ROOT, "parser", "sta_engine"))
SAMPLE  = os.path.normpath(os.path.join(ROOT, "sample_circuit.txt"))


def test_sta_binary_exists():
    assert os.path.isfile(STA_BIN), "sta_engine binary not found — run make"


def test_sta_returns_valid_json(sample_timing):
    assert isinstance(sample_timing, dict)


def test_sta_required_keys(sample_timing):
    for key in ("target_period_ns", "critical_path_ns", "max_frequency_mhz",
                "timing_met", "wns_ns", "tns_ns", "critical_path", "gate_timing"):
        assert key in sample_timing, f"Missing key: {key}"


def test_critical_path_nonempty(sample_timing):
    assert len(sample_timing["critical_path"]) > 0


def test_critical_path_delay_positive(sample_timing):
    assert sample_timing["critical_path_ns"] > 0


def test_max_frequency_positive(sample_timing):
    assert sample_timing["max_frequency_mhz"] > 0


def test_timing_met_with_generous_period(tmp_path):
    """With a 100 ns period, timing should always be met."""
    result = subprocess.run(
        [STA_BIN, SAMPLE, "--period", "100.0"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["timing_met"] is True
    assert data["wns_ns"] >= 0


def test_timing_violated_with_zero_period(tmp_path):
    """With a 0.001 ns period, timing should be violated."""
    result = subprocess.run(
        [STA_BIN, SAMPLE, "--period", "0.001"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["timing_met"] is False
    assert data["wns_ns"] < 0


def test_gate_timing_all_gates_present(sample_stats, sample_timing):
    """Every gate in the netlist should appear in the timing report."""
    timing_names = {g["name"] for g in sample_timing["gate_timing"]}
    for g in sample_stats["gates"]:
        assert g["name"] in timing_names, f"Gate {g['name']} missing from timing"


def test_slack_equals_rat_minus_at(sample_timing):
    for g in sample_timing["gate_timing"]:
        expected = round(g["required_ns"] - g["arrival_ns"], 4)
        assert abs(g["slack_ns"] - expected) < 1e-3
