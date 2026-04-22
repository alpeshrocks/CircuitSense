"""Tests for the Python Verilog parser."""

import os
import pytest
from vlsi.verilog_parser import parse_verilog, verilog_to_txt

ROOT     = os.path.dirname(os.path.dirname(__file__))
ADDER_V  = os.path.join(ROOT, "samples", "full_adder_gate.v")
COUNTER_V = os.path.join(ROOT, "samples", "counter_4bit_gate.v")


def test_full_adder_gate_count(full_adder_gates):
    # full_adder_gate.v has 5 gates: 2 XOR2, 2 AND2, 1 OR2
    assert len(full_adder_gates) == 5


def test_full_adder_gate_types(full_adder_gates):
    types = [g["type"] for g in full_adder_gates]
    assert types.count("XOR2") == 2
    assert types.count("AND2") == 2
    assert types.count("OR2") == 1


def test_gate_has_required_fields(full_adder_gates):
    for g in full_adder_gates:
        assert "name" in g
        assert "type" in g
        assert "area" in g and g["area"] > 0
        assert "power" in g and g["power"] > 0
        assert "output_net" in g
        assert "input_nets" in g


def test_full_adder_output_nets_assigned(full_adder_gates):
    # All gates should have an assigned output net
    for g in full_adder_gates:
        assert g["output_net"] is not None, f"Gate {g['name']} has no output_net"


def test_full_adder_input_nets_nonempty(full_adder_gates):
    # All gates should have at least one input
    for g in full_adder_gates:
        assert len(g["input_nets"]) > 0, f"Gate {g['name']} has no input_nets"


def test_verilog_to_txt_creates_file(tmp_path):
    out = str(tmp_path / "adder.txt")
    result_path = verilog_to_txt(ADDER_V, out)
    assert os.path.isfile(result_path)
    content = open(result_path).read()
    assert "GATE" in content
    assert "NET" in content


def test_verilog_to_txt_gate_lines(tmp_path):
    out = str(tmp_path / "adder.txt")
    verilog_to_txt(ADDER_V, out)
    lines = open(out).readlines()
    gate_lines = [l for l in lines if l.startswith("GATE")]
    assert len(gate_lines) == 5


def test_counter_parses_dffs():
    gates = parse_verilog(COUNTER_V)
    dff_gates = [g for g in gates if g["type"] == "DFF"]
    assert len(dff_gates) == 4


def test_unknown_file_raises():
    with pytest.raises(FileNotFoundError):
        parse_verilog("/nonexistent/file.v")
