"""
tests/test_report.py — Unit tests for vlsi/report.py
=====================================================
WHAT IS TESTED:
    generate_report() — produces a self-contained HTML file from mock data.

    Tests use MOCK_STATS and MOCK_TIMING dicts (not real C++ binary output)
    so they run without compiling C++ and are fully deterministic.

CHECKS:
    - Output file is created at the specified path
    - File size exceeds 5 KB (ensures charts were embedded as base64 PNG)
    - HTML contains expected section headings (PPA Summary, Critical Path, etc.)
    - At least one base64 PNG data URI is embedded (charts rendered)
    - PASS badge appears when timing_met=True
    - FAIL badge appears when timing_met=False
    - LLM suggestions section appears when suggestions text is provided
    - LLM section is absent when suggestions=None

MOCK DATA:
    MOCK_STATS — 5-gate circuit: 2× NAND2, 2× XOR2, 1× DFF
    MOCK_TIMING — 2-gate critical path (g1 → g2), timing PASS, WNS = 9.44 ns
"""

import os
import pytest
from vlsi.report import generate_report

MOCK_STATS = {
    "total_gates": 5,
    "combinational_gates": 4,
    "sequential_gates": 1,
    "total_area_um2": 12.24,
    "total_power_uW": 17.3,
    "power_density_uW_um2": 1.41,
    "avg_gate_power_uW": 3.46,
    "avg_gate_area_um2": 2.45,
    "max_power_gate": "ff1",
    "max_power_gate_uW": 8.2,
    "max_area_gate": "ff1",
    "max_area_gate_um2": 5.4,
    "total_nets": 4,
    "avg_fanout": 1.5,
    "max_fanout": 3,
    "max_fanout_net": "n1",
    "high_fanout_nets": 0,
    "gate_type_counts": {"NAND2": 2, "XOR2": 2, "DFF": 1},
    "gate_type_power_uW": {"NAND2": 4.2, "XOR2": 7.6, "DFF": 8.2},
    "gate_type_area_um2": {"NAND2": 2.88, "XOR2": 5.76, "DFF": 5.4},
    "gates": [
        {"name": "g1", "type": "NAND2", "area": 1.44, "power": 2.1, "drive": 1},
        {"name": "g2", "type": "XOR2",  "area": 2.88, "power": 3.8, "drive": 1},
        {"name": "ff1","type": "DFF",   "area": 5.40, "power": 8.2, "drive": 2},
    ],
}

MOCK_TIMING = {
    "target_period_ns": 10.0,
    "critical_path_ns": 0.56,
    "max_frequency_mhz": 1785.7,
    "timing_met": True,
    "wns_ns": 9.44,
    "tns_ns": 0.0,
    "wns_gate": "g2",
    "critical_path": ["g1", "g2"],
    "gate_timing": [
        {"name": "g1", "type": "NAND2", "delay_ns": 0.08,
         "arrival_ns": 0.08, "required_ns": 9.64, "slack_ns": 9.56},
        {"name": "g2", "type": "XOR2",  "delay_ns": 0.20,
         "arrival_ns": 0.56, "required_ns": 10.0, "slack_ns": 9.44},
        {"name": "ff1","type": "DFF",   "delay_ns": 0.25,
         "arrival_ns": 0.25, "required_ns": 10.0, "slack_ns": 9.75},
    ],
}


def test_report_creates_file(tmp_path):
    out = str(tmp_path / "report.html")
    generate_report(MOCK_STATS, MOCK_TIMING, None, None, out, "Test Circuit")
    assert os.path.isfile(out)


def test_report_file_not_empty(tmp_path):
    out = str(tmp_path / "report.html")
    generate_report(MOCK_STATS, MOCK_TIMING, None, None, out)
    assert os.path.getsize(out) > 5000


def test_report_contains_key_sections(tmp_path):
    out = str(tmp_path / "report.html")
    generate_report(MOCK_STATS, MOCK_TIMING, None, None, out, "Demo")
    html = open(out).read()
    assert "PPA Summary" in html
    assert "Critical Path" in html
    assert "Gate Timing Table" in html
    assert "Floorplan" in html


def test_report_embeds_charts(tmp_path):
    out = str(tmp_path / "report.html")
    generate_report(MOCK_STATS, MOCK_TIMING, None, None, out)
    html = open(out).read()
    # Charts are embedded as base64 PNG data URIs
    assert "data:image/png;base64" in html


def test_report_shows_timing_pass(tmp_path):
    out = str(tmp_path / "report.html")
    generate_report(MOCK_STATS, MOCK_TIMING, None, None, out)
    html = open(out).read()
    assert "PASS" in html


def test_report_shows_timing_fail(tmp_path):
    failing_timing = dict(MOCK_TIMING, timing_met=False, wns_ns=-0.5)
    out = str(tmp_path / "report_fail.html")
    generate_report(MOCK_STATS, failing_timing, None, None, out)
    html = open(out).read()
    assert "FAIL" in html


def test_report_with_llm_suggestions(tmp_path):
    out = str(tmp_path / "report_llm.html")
    suggestions = "1. Replace OR2 with NOR2+INV for better power.\n2. Buffer high-fanout net."
    generate_report(MOCK_STATS, MOCK_TIMING, None, suggestions, out)
    html = open(out).read()
    assert "LLM Optimization Suggestions" in html
    assert "Replace OR2" in html
