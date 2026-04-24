"""
vlsi/floorplanner.py — Row-Based Gate Floorplanner
===================================================
PURPOSE:
    Assign 2D (x, y) coordinates to every gate in the circuit and render
    a colour-coded PNG floorplan image. This is a simplified version of the
    placement phase in a real Place-and-Route (P&R) flow.

ALGORITHM — Row-based placement:
    1. Sort gates by type priority (DFFs first, then complex gates, then simple)
       so related cells cluster together, which minimises wire length in practice.
    2. Assign each gate a rectangular bounding box (w × h) such that w * h = area
       and w/h = ASPECT ratio (default 1.5, a typical standard cell shape).
    3. Place gates left-to-right in a row. When the next cell would exceed
       chip_width, start a new row below with ROW_GAP spacing.
    4. chip_width is auto-computed as sqrt(total_area) * 1.4 if not supplied,
       giving ~20% white-space overhead (realistic for early floorplanning).

OUTPUT:
    A PNG image rendered with matplotlib using a dark theme.
    Each gate type has a distinct colour; a legend identifies types.
    Gate type labels are drawn inside cells that are wide enough (> 0.8 um).

COLOUR SCHEME (gate type → hex colour):
    DFF   → red      (sequential cells, most area/power — stand out)
    XOR2  → purple   (common in adders/comparators)
    NAND2 → blue     (most common logic primitive)
    AND2  → green    (data-path gates)
    OR2   → orange
    INV   → grey     (smallest, least critical)

PUBLIC API:
    place_gates(gates, chip_width)          → list of placed gate dicts
    render_floorplan(placed_gates, out_path)→ PNG path
    run_floorplan(stats, out_path)          → convenience wrapper

PLACED GATE DICT SCHEMA (extends the parser gate dict):
    Adds: x (float), y (float), w (float), h (float) — all in um
"""

import math
import os
from typing import Optional

import matplotlib
matplotlib.use("Agg")   # non-interactive backend — no display required
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


# ── Visual configuration ──────────────────────────────────────────────────────

# Colour per gate type — chosen for contrast on dark background
GATE_COLORS: dict[str, str] = {
    "DFF":   "#e74c3c",   # red     — sequential, high power/area
    "XOR2":  "#9b59b6",   # purple  — used in adders / parity
    "XNOR2": "#8e44ad",   # dark purple
    "NAND2": "#2980b9",   # blue    — most common primitive
    "NOR2":  "#1abc9c",   # teal
    "AND2":  "#27ae60",   # green
    "OR2":   "#f39c12",   # orange
    "INV":   "#95a5a6",   # grey    — smallest gate
    "BUF":   "#bdc3c7",   # light grey
    "MUX2":  "#e67e22",   # dark orange
    "NAND3": "#2471a3",   # dark blue
    "NOR3":  "#148f77",   # dark teal
}
DEFAULT_COLOR = "#7f8c8d"   # fallback for unknown gate types

# Layout constants (all in um)
ROW_GAP  = 0.5   # vertical gap between rows
CELL_GAP = 0.3   # horizontal gap between cells in the same row
ASPECT   = 1.5   # cell width / height ratio (matches standard cell library shape)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _cell_dims(area: float) -> tuple[float, float]:
    """
    Compute cell width and height from area and a fixed aspect ratio.

    Uses: h = sqrt(area / ASPECT),  w = area / h
    This ensures w * h == area and w / h == ASPECT.

    Args:
        area: Cell area in um².

    Returns:
        (width, height) tuple in um.

    Example:
        _cell_dims(1.44) → (1.47, 0.98)  for ASPECT=1.5
    """
    h = math.sqrt(area / ASPECT)
    w = area / h
    return w, h


# ── Public API ────────────────────────────────────────────────────────────────

def place_gates(gates: list[dict], chip_width: Optional[float] = None) -> list[dict]:
    """
    Assign (x, y, w, h) coordinates to each gate using row-based placement.

    Does NOT modify the input dicts in-place — returns new dicts with the
    extra positional fields merged in.

    Placement order:
        DFF gates are placed first (they typically form I/O ring).
        Then complex gates (XOR2 — used in data paths).
        Then standard gates by area descending (larger cells placed first
        to reduce fragmentation at row ends).

    Args:
        gates:      List of gate dicts from circuit_parser JSON "gates" key.
                    Each dict must have: name, type, area (and optionally power, drive).
        chip_width: Target row width in um. If None, auto-set to
                    sqrt(total_area) * 1.4  (~20% area overhead).

    Returns:
        New list of gate dicts, each with added keys:
            x (float): left edge x-coordinate in um
            y (float): bottom edge y-coordinate in um
            w (float): cell width in um
            h (float): cell height in um

    Example:
        placed = place_gates(stats["gates"])
        # → [{"name": "ff1", "type": "DFF", "x": 0.0, "y": 0.0, ...}, ...]
    """
    if not gates:
        return gates

    # Auto-compute chip width from total area if not provided
    total_area = sum(g["area"] for g in gates)
    if chip_width is None:
        chip_width = math.sqrt(total_area) * 1.4

    # Sort gates: DFFs first, then XOR2, then others by area descending
    def sort_key(g: dict) -> tuple:
        type_priority = {"DFF": 0, "XOR2": 1, "NAND2": 2, "NOR2": 3}
        return (type_priority.get(g["type"], 5), -g["area"])

    sorted_gates = sorted(gates, key=sort_key)

    # Row-based placement loop
    placed: list[dict] = []
    x, y       = 0.0, 0.0
    row_height = 0.0   # tallest cell in the current row

    for g in sorted_gates:
        w, h = _cell_dims(g["area"])

        # Wrap to next row if this cell doesn't fit (and we're not at row start)
        if x + w > chip_width and x > 0:
            y          += row_height + ROW_GAP
            x           = 0.0
            row_height  = 0.0

        # Create a new dict (don't mutate the caller's data)
        g_placed = dict(g)
        g_placed.update({"x": x, "y": y, "w": w, "h": h})
        placed.append(g_placed)

        x          += w + CELL_GAP
        row_height  = max(row_height, h)

    return placed


def render_floorplan(placed_gates: list[dict], out_path: str,
                     title: str = "VLSI Floorplan") -> str:
    """
    Render a colour-coded floorplan PNG from a list of placed gates.

    Each gate is drawn as a rounded rectangle with its type colour.
    Gate type labels appear inside cells that are wider than 0.8 um.
    A legend in the top-right maps colours to gate types.

    Args:
        placed_gates: List of placed gate dicts (output of place_gates).
                      Each dict must have: type, x, y, w, h.
        out_path:     Destination path for the PNG file (e.g. "output/fp.png").
        title:        Plot title shown above the floorplan.

    Returns:
        out_path if successful, empty string if placed_gates is empty.

    Side effects:
        Writes a PNG file to out_path at 150 dpi.
    """
    if not placed_gates:
        return ""

    # Determine canvas size from placed bounding box
    max_x = max(g["x"] + g["w"] for g in placed_gates)
    max_y = max(g["y"] + g["h"] for g in placed_gates)

    # Scale figure size: clamp between reasonable min/max inches
    fig_w = min(max(8, max_x / 5), 16)
    fig_h = min(max(6, max_y / 5), 12)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # Draw each gate as a rounded rectangle
    for g in placed_gates:
        color = GATE_COLORS.get(g["type"], DEFAULT_COLOR)
        rect  = mpatches.FancyBboxPatch(
            (g["x"], g["y"]), g["w"], g["h"],
            boxstyle="round,pad=0.05",
            linewidth=0.5, edgecolor="white",
            facecolor=color, alpha=0.85
        )
        ax.add_patch(rect)

        # Only label cells wide enough to fit text readably
        if g["w"] > 0.8:
            ax.text(
                g["x"] + g["w"] / 2, g["y"] + g["h"] / 2,
                g["type"], ha="center", va="center",
                fontsize=5, color="white", fontweight="bold"
            )

    # Build legend from gate types actually present (preserving placement order)
    seen_types = list(dict.fromkeys(g["type"] for g in placed_gates))
    legend_patches = [
        mpatches.Patch(facecolor=GATE_COLORS.get(t, DEFAULT_COLOR), label=t)
        for t in seen_types
    ]
    ax.legend(handles=legend_patches, loc="upper right",
              fontsize=7, framealpha=0.8, ncol=2)

    # Axes and styling
    ax.set_xlim(-0.5, max_x + 0.5)
    ax.set_ylim(-0.5, max_y + 0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("Width (um)")
    ax.set_ylabel("Height (um)")
    ax.set_title(title, fontsize=11, fontweight="bold")

    # Dark theme to match the HTML report
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#16213e")
    ax.tick_params(colors="white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.title.set_color("white")

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)   # free memory — important in batch processing
    return out_path


def run_floorplan(stats: dict, out_path: str, title: str = "VLSI Floorplan") -> str:
    """
    Convenience wrapper: extract gates from circuit_parser output, place and render.

    Args:
        stats:    Dict returned by run_parser() — must contain "gates" list.
        out_path: Destination PNG path.
        title:    Floorplan title string.

    Returns:
        Path to the rendered PNG, or empty string if no gates in stats.

    Example:
        fp_path = run_floorplan(stats, "output/design_floorplan.png", "MyDesign")
    """
    gates = stats.get("gates", [])
    if not gates:
        return ""
    placed = place_gates(gates)
    return render_floorplan(placed, out_path, title)
