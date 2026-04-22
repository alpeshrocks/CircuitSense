"""
Yosys wrapper: synthesize RTL Verilog to gate-level netlist.
Falls back gracefully if Yosys is not installed.
"""

import shutil
import subprocess
import os
import tempfile


def yosys_available() -> bool:
    return shutil.which("yosys") is not None


def synthesize(rtl_path: str, top_module: str = "", out_dir: str = "") -> str:
    """
    Run Yosys synthesis on an RTL Verilog file.
    Returns path to the gate-level Verilog netlist.
    Raises RuntimeError if Yosys is not installed.
    """
    if not yosys_available():
        raise RuntimeError(
            "Yosys not found. Install with: brew install yosys  "
            "(macOS) or  apt install yosys  (Ubuntu)."
        )

    if not out_dir:
        out_dir = tempfile.mkdtemp(prefix="vlsi_yosys_")

    base = os.path.splitext(os.path.basename(rtl_path))[0]
    out_v = os.path.join(out_dir, f"{base}_synth.v")

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
        raise RuntimeError(f"Yosys failed:\n{result.stderr}")

    return out_v


def try_synthesize(rtl_path: str, top_module: str = "", out_dir: str = "") -> tuple[str, bool]:
    """
    Attempt synthesis. Returns (path, was_synthesized).
    If Yosys is unavailable, returns (rtl_path, False).
    """
    if not yosys_available():
        print("[!] Yosys not found — using RTL file directly (limited analysis).")
        return rtl_path, False
    try:
        out = synthesize(rtl_path, top_module, out_dir)
        print(f"[+] Yosys synthesis complete: {out}")
        return out, True
    except RuntimeError as e:
        print(f"[!] Yosys error: {e}")
        return rtl_path, False
