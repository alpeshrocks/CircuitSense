"""Tests for the Python floorplanner."""

import os
import pytest
from vlsi.floorplanner import place_gates, render_floorplan, run_floorplan

SAMPLE_GATES = [
    {"name": "g1", "type": "NAND2", "area": 1.44, "power": 2.1, "drive": 1},
    {"name": "g2", "type": "XOR2",  "area": 2.88, "power": 3.8, "drive": 1},
    {"name": "g3", "type": "DFF",   "area": 5.40, "power": 8.2, "drive": 2},
    {"name": "g4", "type": "INV",   "area": 0.72, "power": 0.9, "drive": 1},
    {"name": "g5", "type": "OR2",   "area": 1.80, "power": 2.3, "drive": 1},
]


def test_all_gates_placed():
    placed = place_gates(list(SAMPLE_GATES))
    assert len(placed) == len(SAMPLE_GATES)


def test_placed_gates_have_coordinates():
    placed = place_gates(list(SAMPLE_GATES))
    for g in placed:
        assert "x" in g and "y" in g
        assert "w" in g and "h" in g
        assert g["w"] > 0 and g["h"] > 0


def test_no_negative_coordinates():
    placed = place_gates(list(SAMPLE_GATES))
    for g in placed:
        assert g["x"] >= 0
        assert g["y"] >= 0


def test_area_preserved():
    """Placed cell w*h should approximately equal original area."""
    placed = place_gates(list(SAMPLE_GATES))
    for g in placed:
        assert abs(g["w"] * g["h"] - g["area"]) < 0.01


def test_render_creates_file(tmp_path):
    placed = place_gates(list(SAMPLE_GATES))
    out = str(tmp_path / "floorplan.png")
    result = render_floorplan(placed, out, "Test Floorplan")
    assert result == out
    assert os.path.isfile(out)
    assert os.path.getsize(out) > 1000  # non-empty PNG


def test_run_floorplan_with_stats(tmp_path, sample_stats):
    out = str(tmp_path / "fp.png")
    result = run_floorplan(sample_stats, out)
    assert os.path.isfile(result)


def test_empty_gates_returns_empty():
    placed = place_gates([])
    assert placed == []


def test_single_gate():
    gates = [{"name": "only", "type": "INV", "area": 0.72, "power": 0.9, "drive": 1}]
    placed = place_gates(gates)
    assert len(placed) == 1
    assert placed[0]["x"] == 0.0
    assert placed[0]["y"] == 0.0
