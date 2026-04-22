"""
Simple row-based floorplanner.
Takes the gate list from the circuit parser and assigns (x, y) coordinates.
Generates a matplotlib floorplan image.
"""

import math
import os
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


# Color map per gate type
GATE_COLORS = {
    "DFF":   "#e74c3c",
    "XOR2":  "#9b59b6",
    "XNOR2": "#8e44ad",
    "NAND2": "#2980b9",
    "NOR2":  "#1abc9c",
    "AND2":  "#27ae60",
    "OR2":   "#f39c12",
    "INV":   "#95a5a6",
    "BUF":   "#bdc3c7",
    "MUX2":  "#e67e22",
    "NAND3": "#2471a3",
    "NOR3":  "#148f77",
}
DEFAULT_COLOR = "#7f8c8d"

ROW_GAP   = 0.5   # gap between rows (um)
CELL_GAP  = 0.3   # gap between cells in a row (um)
ASPECT    = 1.5   # width/height ratio for gate cells


def _cell_dims(area: float) -> tuple[float, float]:
    """Compute (width, height) from area assuming fixed aspect ratio."""
    h = math.sqrt(area / ASPECT)
    w = area / h
    return w, h


def place_gates(gates: list[dict], chip_width: Optional[float] = None) -> list[dict]:
    """
    Row-based placement. Modifies gates in-place adding 'x', 'y', 'w', 'h'.
    Returns placed gates.
    """
    if not gates:
        return gates

    total_area = sum(g["area"] for g in gates)
    if chip_width is None:
        chip_width = math.sqrt(total_area) * 1.4

    # Sort: DFFs first (they form the boundary), then by area descending
    def sort_key(g):
        order = {"DFF": 0, "XOR2": 1, "NAND2": 2, "NOR2": 3}
        return (order.get(g["type"], 5), -g["area"])

    sorted_gates = sorted(gates, key=sort_key)

    placed = []
    x, y = 0.0, 0.0
    row_height = 0.0

    for g in sorted_gates:
        w, h = _cell_dims(g["area"])
        if x + w > chip_width and x > 0:
            y += row_height + ROW_GAP
            x = 0.0
            row_height = 0.0
        g_placed = dict(g)
        g_placed.update({"x": x, "y": y, "w": w, "h": h})
        placed.append(g_placed)
        x += w + CELL_GAP
        row_height = max(row_height, h)

    return placed


def render_floorplan(placed_gates: list[dict], out_path: str,
                     title: str = "VLSI Floorplan") -> str:
    """
    Render the placed floorplan to a PNG file.
    Returns the output path.
    """
    if not placed_gates:
        return ""

    max_x = max(g["x"] + g["w"] for g in placed_gates)
    max_y = max(g["y"] + g["h"] for g in placed_gates)

    fig_w = min(max(8, max_x / 5), 16)
    fig_h = min(max(6, max_y / 5), 12)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    for g in placed_gates:
        color = GATE_COLORS.get(g["type"], DEFAULT_COLOR)
        rect = mpatches.FancyBboxPatch(
            (g["x"], g["y"]), g["w"], g["h"],
            boxstyle="round,pad=0.05",
            linewidth=0.5, edgecolor="white",
            facecolor=color, alpha=0.85
        )
        ax.add_patch(rect)
        # Label only if cell is wide enough
        if g["w"] > 0.8:
            ax.text(
                g["x"] + g["w"] / 2, g["y"] + g["h"] / 2,
                g["type"], ha="center", va="center",
                fontsize=5, color="white", fontweight="bold"
            )

    # Legend
    seen_types = list(dict.fromkeys(g["type"] for g in placed_gates))
    legend_patches = [
        mpatches.Patch(facecolor=GATE_COLORS.get(t, DEFAULT_COLOR), label=t)
        for t in seen_types
    ]
    ax.legend(handles=legend_patches, loc="upper right", fontsize=7,
              framealpha=0.8, ncol=2)

    ax.set_xlim(-0.5, max_x + 0.5)
    ax.set_ylim(-0.5, max_y + 0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("Width (um)")
    ax.set_ylabel("Height (um)")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#16213e")
    ax.tick_params(colors="white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.title.set_color("white")

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def run_floorplan(stats: dict, out_path: str, title: str = "VLSI Floorplan") -> str:
    """
    High-level entry point: takes circuit_parser JSON stats, runs placement,
    renders floorplan image, returns image path.
    """
    gates = stats.get("gates", [])
    if not gates:
        return ""
    placed = place_gates(gates)
    return render_floorplan(placed, out_path, title)
