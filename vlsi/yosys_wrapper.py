"""
vlsi/yosys_wrapper.py — Yosys RTL Synthesis Wrapper
====================================================
PURPOSE:
    Provide a thin wrapper around the Yosys open-source synthesis tool
    so CircuitSense can accept RTL Verilog (behavioural code with always
    blocks, assign statements, etc.) and automatically synthesise it into
    a gate-level netlist before analysis.

    This is entirely optional — if Yosys is not installed, the tool
    degrades gracefully and only gate-level .v files or .txt netlists
    can be used. No error is raised; a warning is printed instead.

YOSYS SYNTHESIS FLOW:
    1. read_verilog <rtl.v>   — parse RTL source
    2. synth [-top <name>]    — run default synthesis passes:
                                 coarse optimisation → technology mapping
                                 → fine optimisation
    3. write_verilog -noattr  — emit clean gate-level Verilog
                                (-noattr strips synthesis attributes)

    The output is a flat gate-level .v file using Yosys internal cell
    types ($_AND_, $_OR_, $_NOT_, $_DFF_P_, etc.) which verilog_parser.py
    already knows how to handle via the STD_CELL and OUTPUT_PIN mappings.

INSTALLATION:
    macOS : brew install yosys
    Ubuntu: sudo apt install yosys
    Windows: build from source or use WSL

PUBLIC API:
    yosys_available()             → bool
    synthesize(rtl_path, ...)     → str (gate-level .v path)
    try_synthesize(rtl_path, ...) → tuple(str, bool)  — safe variant
"""

import shutil
import subprocess
import os
import tempfile


def yosys_available() -> bool:
    """
    Check whether the yosys binary is present on the system PATH.

    Uses shutil.which() which handles PATH lookup cross-platform.

    Returns:
        True if yosys is installed and callable, False otherwise.
    """
    return shutil.which("yosys") is not None


def synthesize(rtl_path: str, top_module: str = "", out_dir: str = "") -> str:
    """
    Run Yosys synthesis on an RTL Verilog file and return the gate-level output path.

    Constructs a one-liner Yosys script that reads the RTL, runs the default
    synthesis flow (which includes logic optimisation and technology mapping),
    and writes a gate-level Verilog file stripped of Yosys attributes.

    Args:
        rtl_path:   Path to the RTL Verilog input file (.v).
        top_module: Name of the top-level module to synthesise.
                    If empty, Yosys auto-detects the top module.
        out_dir:    Directory to write the synthesised netlist into.
                    If empty, a temporary directory is created automatically.

    Returns:
        Absolute path to the synthesised gate-level Verilog file
        (named <basename>_synth.v in out_dir).

    Raises:
        RuntimeError: If Yosys is not installed.
        RuntimeError: If Yosys synthesis fails (non-zero exit code).

    Example:
        gate_v = synthesize("samples/half_adder_rtl.v", top_module="half_adder")
        # gate_v → "/tmp/vlsi_yosys_xyz/half_adder_synth.v"
    """
    if not yosys_available():
        raise RuntimeError(
            "Yosys not found. Install with:\n"
            "  macOS : brew install yosys\n"
            "  Ubuntu: sudo apt install yosys"
        )

    # Create output directory if not provided
    if not out_dir:
        out_dir = tempfile.mkdtemp(prefix="vlsi_yosys_")

    base  = os.path.splitext(os.path.basename(rtl_path))[0]
    out_v = os.path.join(out_dir, f"{base}_synth.v")

    # Build Yosys script: read → synthesise → write
    # -top flag is optional — without it Yosys infers the top module automatically
    top_flag = f"-top {top_module}" if top_module else ""
    script = (
        f"read_verilog {rtl_path}; "
        f"synth {top_flag}; "
        f"write_verilog -noattr {out_v}"
    )

    result = subprocess.run(
        ["yosys", "-p", script],
        capture_output=True, text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"Yosys synthesis failed:\n{result.stderr}")

    return out_v


def try_synthesize(
    rtl_path: str,
    top_module: str = "",
    out_dir: str = ""
) -> tuple[str, bool]:
    """
    Attempt Yosys synthesis, falling back gracefully if unavailable or failed.

    This is the safe variant used by main.py. It never raises — on any
    failure it returns the original file path and False so the caller can
    decide how to proceed (e.g. attempt direct Verilog parsing instead).

    Args:
        rtl_path:   Path to the RTL Verilog input file.
        top_module: Top-level module name (optional).
        out_dir:    Output directory for synthesised netlist (optional).

    Returns:
        (synthesised_gate_v_path, True)  — if synthesis succeeded
        (rtl_path, False)                — if Yosys not found or synthesis failed

    Example:
        path, ok = try_synthesize("design.v")
        if ok:
            gates = parse_verilog(path)   # parse synthesised gate-level
        else:
            gates = parse_verilog(path)   # attempt to parse RTL directly
    """
    if not yosys_available():
        print("[!] Yosys not found — using input file directly (limited analysis).")
        return rtl_path, False

    try:
        out = synthesize(rtl_path, top_module, out_dir)
        print(f"[+] Yosys synthesis complete: {out}")
        return out, True
    except RuntimeError as e:
        print(f"[!] Yosys error: {e}")
        return rtl_path, False
