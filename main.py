#!/usr/bin/env python3
"""
VLSI Circuit Analysis Tool — Mini EDA Flow
==========================================
Flow:
  1. Input  : .txt netlist  OR  gate-level .v Verilog  OR  RTL .v (+ Yosys)
  2. Parse  : C++ circuit_parser  → power/area/gate stats (JSON)
  3. STA    : C++ sta_engine      → critical path / slack / frequency (JSON)
  4. Floor  : Python floorplanner → 2D placement image
  5. Report : Python report gen   → self-contained HTML report
  6. LLM    : Claude agentic loop → tool-use optimization suggestions
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT       = os.path.dirname(os.path.abspath(__file__))
PARSER_BIN = os.path.join(ROOT, "parser", "circuit_parser")
STA_BIN    = os.path.join(ROOT, "parser", "sta_engine")


# ── Build helpers ─────────────────────────────────────────────────────────────

def build_tools() -> bool:
    src_cpp   = os.path.join(ROOT, "parser", "circuit_parser.cpp")
    src_sta   = os.path.join(ROOT, "parser", "sta_engine.cpp")
    needs_build = (
        not os.path.exists(PARSER_BIN) or
        not os.path.exists(STA_BIN) or
        os.path.getmtime(src_cpp) > os.path.getmtime(PARSER_BIN) or
        os.path.getmtime(src_sta) > os.path.getmtime(STA_BIN)
    )
    if needs_build:
        print("[*] Compiling C++ tools...")
        r = subprocess.run(["make", "-C", os.path.join(ROOT, "parser")],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("Build failed:\n", r.stderr)
            return False
        print("[+] C++ tools compiled.")
    return True


# ── Input resolution ──────────────────────────────────────────────────────────

def resolve_netlist(path: str) -> str:
    """
    If path is a .v file, convert it to our .txt format first.
    Returns the .txt netlist path to use with C++ tools.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".txt":
        return path

    if ext == ".v":
        # Check if it looks like RTL (no gate instantiations) → try Yosys
        from vlsi.yosys_wrapper import yosys_available, try_synthesize
        from vlsi.verilog_parser import verilog_to_txt, parse_verilog

        gates = parse_verilog(path)
        if not gates and yosys_available():
            print("[*] No gates found in Verilog — attempting Yosys synthesis...")
            synth_v, ok = try_synthesize(path)
            if ok:
                path = synth_v
                gates = parse_verilog(path)

        if not gates:
            print("[!] No parseable gates found. Is this gate-level Verilog?")
            sys.exit(1)

        print(f"[+] Parsed {len(gates)} gates from Verilog.")
        tmp_txt = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, prefix="vlsi_").name
        return verilog_to_txt(path, tmp_txt)

    print(f"[!] Unsupported file type: {ext}. Use .txt or .v")
    sys.exit(1)


# ── C++ runners ───────────────────────────────────────────────────────────────

def run_parser(netlist: str) -> dict:
    r = subprocess.run([PARSER_BIN, netlist], capture_output=True, text=True)
    if r.returncode != 0:
        print("Parser error:\n", r.stderr); sys.exit(1)
    return json.loads(r.stdout)


def run_sta(netlist: str, period: float) -> dict:
    r = subprocess.run([STA_BIN, netlist, "--period", str(period)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("STA error:\n", r.stderr); sys.exit(1)
    return json.loads(r.stdout)


# ── Display helpers ───────────────────────────────────────────────────────────

def print_stats(stats: dict) -> None:
    print("\n" + "=" * 58)
    print("  VLSI Circuit Statistics")
    print("=" * 58)
    print(f"  Gates          : {stats['total_gates']} "
          f"(comb={stats['combinational_gates']}, seq={stats['sequential_gates']})")
    print(f"  Total Area     : {stats['total_area_um2']:.2f} um²")
    print(f"  Total Power    : {stats['total_power_uW']:.2f} uW")
    print(f"  Power Density  : {stats['power_density_uW_um2']:.4f} uW/um²")
    print(f"  Max Power Gate : {stats['max_power_gate']} ({stats['max_power_gate_uW']:.2f} uW)")
    print(f"  Nets           : {stats['total_nets']} | "
          f"Avg fanout: {stats['avg_fanout']:.2f} | "
          f"Max fanout: {stats['max_fanout']} ({stats['max_fanout_net']})")
    print("\n  Gate Type Breakdown:")
    for gtype, count in stats["gate_type_counts"].items():
        pwr  = stats["gate_type_power_uW"].get(gtype, 0)
        area = stats["gate_type_area_um2"].get(gtype, 0)
        print(f"    {gtype:<8} x{count:<3}  power={pwr:.2f} uW  area={area:.2f} um²")
    print("=" * 58)


def print_timing(timing: dict) -> None:
    status = "PASS ✓" if timing["timing_met"] else "FAIL ✗"
    print("\n" + "=" * 58)
    print("  Static Timing Analysis")
    print("=" * 58)
    print(f"  Target Period  : {timing['target_period_ns']:.2f} ns")
    print(f"  Critical Path  : {timing['critical_path_ns']:.4f} ns")
    print(f"  Max Frequency  : {timing['max_frequency_mhz']:.2f} MHz")
    print(f"  WNS            : {timing['wns_ns']:.4f} ns")
    print(f"  TNS            : {timing['tns_ns']:.4f} ns")
    print(f"  Timing         : {status}")
    cp = timing.get("critical_path", [])
    if cp:
        print(f"  Path           : {' → '.join(cp)}")
    print("=" * 58)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="VLSI Circuit Analysis Tool — Mini EDA Flow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                   # analyse sample_circuit.txt
  python main.py samples/full_adder_gate.v         # gate-level Verilog
  python main.py my_design.txt --period 5.0        # 5 ns clock target
  python main.py my_design.txt --no-llm            # skip LLM, stats only
  python main.py my_design.txt --no-report --no-floor  # terminal output only
""")
    parser.add_argument(
        "netlist", nargs="?",
        default=os.path.join(ROOT, "sample_circuit.txt"),
        help="Netlist file (.txt or .v)  [default: sample_circuit.txt]",
    )
    parser.add_argument("--period",    type=float, default=10.0,
                        help="Target clock period in ns  [default: 10.0]")
    parser.add_argument("--no-llm",   action="store_true",
                        help="Skip LLM optimization analysis")
    parser.add_argument("--no-report",action="store_true",
                        help="Skip HTML report generation")
    parser.add_argument("--no-floor", action="store_true",
                        help="Skip floorplanning")
    parser.add_argument("--output",   default=os.path.join(ROOT, "output"),
                        help="Output directory for reports  [default: ./output]")
    args = parser.parse_args()

    if not os.path.exists(args.netlist):
        print(f"Error: file not found: {args.netlist}")
        sys.exit(1)

    if not build_tools():
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)
    circuit_name = os.path.splitext(os.path.basename(args.netlist))[0]

    # 1. Resolve netlist (convert Verilog if needed)
    print(f"\n[*] Input: {args.netlist}")
    netlist_txt = resolve_netlist(args.netlist)

    # 2. Parse (power/area stats)
    print("[*] Running circuit parser...")
    stats = run_parser(netlist_txt)
    print_stats(stats)

    # 3. STA
    print("[*] Running static timing analysis...")
    timing = run_sta(netlist_txt, args.period)
    print_timing(timing)

    # 4. Floorplan
    floorplan_path = None
    if not args.no_floor:
        from vlsi.floorplanner import run_floorplan
        fp_out = os.path.join(args.output, f"{circuit_name}_floorplan.png")
        print("[*] Running floorplanner...")
        floorplan_path = run_floorplan(stats, fp_out, f"{circuit_name} — Floorplan")
        if floorplan_path:
            print(f"[+] Floorplan saved: {floorplan_path}")

    # 5. LLM agent
    llm_text = None
    if not args.no_llm:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("\n[!] ANTHROPIC_API_KEY not set — skipping LLM analysis.")
            print("    Export it or run with --no-llm.")
        else:
            from vlsi.llm_agent import run_agent
            llm_text = run_agent(stats, timing, api_key)

    # 6. HTML report
    if not args.no_report:
        from vlsi.report import generate_report
        report_out = os.path.join(args.output, f"{circuit_name}_report.html")
        print("[*] Generating HTML report...")
        generate_report(stats, timing, floorplan_path, llm_text,
                        report_out, circuit_name)
        print(f"[+] Report saved: {report_out}")

    # Clean up temp file if Verilog was converted
    if netlist_txt != args.netlist and os.path.exists(netlist_txt):
        os.unlink(netlist_txt)

    print("\n[+] Done.")


if __name__ == "__main__":
    main()
