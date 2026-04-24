"""
vlsi/verilog_parser.py — Gate-Level Verilog Parser
===================================================
PURPOSE:
    Parse a structural (gate-level) Verilog netlist and convert it into
    CircuitSense's internal GATE/NET text format so the C++ tools
    (circuit_parser, sta_engine) can process it.

    This is intentionally NOT a full Verilog parser. It targets the
    specific subset produced by synthesis tools — gate instantiation
    statements — and ignores RTL constructs (always blocks, assign, etc.).

SUPPORTED INPUT:
    Positional port style  : GATE_TYPE inst_name (out, in1, in2);
    Named port style       : GATE_TYPE inst_name (.Y(out), .A(in1), .B(in2));
    Timing annotations     : GATE_TYPE #(0.3) inst_name (ports);  -- delay ignored
    Yosys internal cells   : $_AND_, $_OR_, $_NOT_, $_DFF_P_, $_MUX_, etc.

STANDARD CELL LIBRARY (STD_CELL):
    Area and power estimates are representative 28nm LP values.
    Any gate type not in the library defaults to area=1.44 um², power=2.10 uW.
    To target a different process node, update STD_CELL and rerun.

PUBLIC API:
    parse_verilog(filepath)        → list of gate dicts
    verilog_to_txt(verilog_path)   → path to converted .txt netlist

GATE DICT SCHEMA:
    {
      "name"       : str,        instance name, e.g. "g_xor1"
      "type"       : str,        normalised cell type, e.g. "XOR2"
      "area"       : float,      cell area in um²
      "power"      : float,      cell power in uW
      "drive"      : int,        drive strength (1, 2, 4, 8)
      "output_net" : str | None, name of the net this gate drives
      "input_nets" : list[str],  names of nets feeding this gate's inputs
    }
"""

import re
import os
import tempfile
from typing import Optional

# ── Standard cell library ─────────────────────────────────────────────────────
# Area (um²) and power (uW) per gate type at 28nm LP typical corner.
# Includes both common industry names and Yosys internal primitive names.
# Yosys uses $_ prefix for its internal cell types after synthesis.
STD_CELL: dict[str, dict] = {
    # Standard combinational cells
    "INV":   {"area": 0.72,  "power": 0.90,  "drive": 1},
    "BUF":   {"area": 0.72,  "power": 0.90,  "drive": 1},
    "NOT":   {"area": 0.72,  "power": 0.90,  "drive": 1},  # alias for INV
    "NAND2": {"area": 1.44,  "power": 2.10,  "drive": 1},
    "NOR2":  {"area": 1.44,  "power": 1.80,  "drive": 1},
    "AND2":  {"area": 1.80,  "power": 2.40,  "drive": 1},
    "OR2":   {"area": 1.80,  "power": 2.30,  "drive": 1},
    "XOR2":  {"area": 2.88,  "power": 3.80,  "drive": 1},
    "XNOR2": {"area": 2.88,  "power": 3.80,  "drive": 1},
    "NAND3": {"area": 2.16,  "power": 2.80,  "drive": 1},
    "NOR3":  {"area": 2.16,  "power": 2.50,  "drive": 1},
    "AND3":  {"area": 2.52,  "power": 3.20,  "drive": 1},
    "OR3":   {"area": 2.52,  "power": 3.10,  "drive": 1},
    "MUX2":  {"area": 3.60,  "power": 4.20,  "drive": 1},
    # Sequential cells (drive=2 reflects stronger Q output driver)
    "DFF":   {"area": 5.40,  "power": 8.20,  "drive": 2},
    # Yosys internal primitives — mapped to equivalent standard cells
    "$_NOT_":   {"area": 0.72, "power": 0.90, "drive": 1},
    "$_AND_":   {"area": 1.80, "power": 2.40, "drive": 1},
    "$_OR_":    {"area": 1.80, "power": 2.30, "drive": 1},
    "$_XOR_":   {"area": 2.88, "power": 3.80, "drive": 1},
    "$_NAND_":  {"area": 1.44, "power": 2.10, "drive": 1},
    "$_NOR_":   {"area": 1.44, "power": 1.80, "drive": 1},
    "$_DFF_P_": {"area": 5.40, "power": 8.20, "drive": 2},  # positive-edge DFF
    "$_DFF_N_": {"area": 5.40, "power": 8.20, "drive": 2},  # negative-edge DFF
    "$_MUX_":   {"area": 3.60, "power": 4.20, "drive": 1},
}

# ── Output pin name mapping ───────────────────────────────────────────────────
# For named-port format (.Y(sig), .A(in1)), we need to know which pin name
# carries the output so we can identify output_net correctly.
# Convention: combinational gates use "Y" or "Z"; flip-flops use "Q".
OUTPUT_PIN: dict[str, str] = {
    "INV": "Y",  "BUF": "Y",  "NOT": "Y",
    "NAND2": "Y", "NOR2": "Y", "AND2": "Y", "OR2": "Y",
    "XOR2": "Y",  "XNOR2": "Y",
    "NAND3": "Y", "NOR3": "Y", "AND3": "Y", "OR3": "Y",
    "MUX2": "Y",  "DFF": "Q",
    "$_NOT_": "Y",   "$_AND_": "Y",  "$_OR_": "Y",
    "$_XOR_": "Y",   "$_NAND_": "Y", "$_NOR_": "Y",
    "$_DFF_P_": "Q", "$_DFF_N_": "Q", "$_MUX_": "Y",
}

# Verilog keywords that must never be treated as gate types or instance names
_SKIP_KEYWORDS = {
    'MODULE', 'ENDMODULE', 'INPUT', 'OUTPUT', 'INOUT',
    'WIRE', 'REG', 'ASSIGN', 'ALWAYS', 'BEGIN', 'END',
    'IF', 'ELSE', 'CASE', 'ENDCASE', 'PARAMETER', 'LOCALPARAM',
}

# Regex to match a gate instantiation:
#   TYPE [#(timing)] INSTANCE_NAME (port_list) ;
# The port_list is captured lazily ([^;]*?) to stop at the first semicolon.
_GATE_INST_RE = re.compile(
    r'([\w\$\\]+)'             # Group 1: gate type
    r'(?:\s*#\s*\([^)]*\))?'  # Optional timing annotation #(0.3) — ignored
    r'\s+([\w\$\\]+)'          # Group 2: instance name
    r'\s*\(([^;]*?)\)\s*;',   # Group 3: port list (everything inside outer parens)
    re.DOTALL                  # Allow port lists spanning multiple lines
)


def _norm_type(t: str) -> str:
    """
    Normalise a raw Verilog gate type token to the STD_CELL lookup key.

    Strips Verilog escaped-identifier backslash prefix and uppercases.

    Args:
        t: Raw type string from Verilog source, e.g. "\\AND2" or "xor2"

    Returns:
        Normalised key string, e.g. "AND2" or "XOR2"
    """
    return t.strip("\\").upper()


def _parse_port_list(port_str: str) -> tuple[list | None, dict | None]:
    """
    Detect whether a port list uses named or positional style, then parse it.

    Named style:   .PIN_NAME(SIGNAL_NAME), ...
        e.g.  .Y(sum), .A(a), .B(b)
        → returns (None, {"Y": "sum", "A": "a", "B": "b"})

    Positional style: SIGNAL, SIGNAL, ...
        e.g.  sum, a, b
        Convention: first signal is output, rest are inputs.
        → returns (["sum", "a", "b"], None)

    Verilog constants (1'b0, 4'hF, etc.) are replaced with a placeholder
    so they don't corrupt net name lookups.

    Args:
        port_str: Raw content between the outer parentheses of a gate instance.

    Returns:
        (positional_list, None) for positional style, or
        (None, named_dict)     for named style.
    """
    port_str = port_str.strip()

    # Named ports: detect by presence of .PIN(SIG) pattern
    named_matches = re.findall(r'\.(\w+)\s*\(([^)]*)\)', port_str)
    if named_matches:
        named = {pin.strip(): sig.strip() for pin, sig in named_matches}
        return None, named

    # Positional: comma-separated signal names
    positional = []
    for tok in port_str.split(','):
        tok = tok.strip()
        # Replace Verilog numeric literals so they don't look like wire names
        if re.match(r"^\d+'[bBhHoO]", tok):
            tok = f"_const_{tok}"
        positional.append(tok)
    return positional, None


def parse_verilog(filepath: str) -> list[dict]:
    """
    Parse a gate-level Verilog file and return all gate instances found.

    Strips comments, then uses regex to find every gate instantiation statement.
    Verilog module/port declarations, wire declarations, assign statements, and
    RTL constructs are silently ignored — only gate instances are extracted.

    For each gate instance, area and power are looked up from STD_CELL using the
    normalised gate type. Unknown types get fallback values (NAND2 equivalent).

    Args:
        filepath: Absolute or relative path to the .v file.

    Returns:
        List of gate dicts, each with keys:
          name, type, area, power, drive, output_net, input_nets

    Raises:
        FileNotFoundError: If filepath does not exist.

    Example:
        gates = parse_verilog("samples/full_adder_gate.v")
        # → [{"name": "g_xor1", "type": "XOR2", "area": 2.88, ...}, ...]
    """
    with open(filepath) as f:
        content = f.read()

    # Remove comments so they don't confuse the regex engine
    content = re.sub(r'//.*', '', content)               # single-line: // ...
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)  # block: /* ... */

    gates = []
    seen_names: set[str] = set()   # track instance names to deduplicate

    for m in _GATE_INST_RE.finditer(content):
        gtype_raw, gname, port_str = m.group(1), m.group(2), m.group(3)
        gtype_norm = _norm_type(gtype_raw)

        # Skip Verilog structural keywords that the regex might accidentally match
        if gtype_norm in _SKIP_KEYWORDS or gname.upper() in _SKIP_KEYWORDS:
            continue

        # Deduplicate: if name already seen, append a suffix
        if gname in seen_names:
            gname = f"{gname}_{len(seen_names)}"
        seen_names.add(gname)

        # Parse the port list to extract output and input net names
        positional, named = _parse_port_list(port_str)

        output_net: str | None = None
        input_nets: list[str] = []

        if named:
            # Named-port style: look up which pin is the output
            out_pin    = OUTPUT_PIN.get(gtype_norm, "Y")
            output_net = named.get(out_pin) or named.get("Z") or named.get("Q")
            input_nets = [v for k, v in named.items()
                          if k not in (out_pin, "Z", "Q")]
        elif positional:
            # Positional style: first port is always the output by convention
            output_net = positional[0] if positional else None
            input_nets = positional[1:]

        # Drop placeholder constants — they are not real net names
        input_nets = [n for n in input_nets if n and not n.startswith("_const_")]

        # Look up cell parameters; default to NAND2 values for unknown types
        cell = STD_CELL.get(gtype_norm, {"area": 1.44, "power": 2.10, "drive": 1})

        gates.append({
            "name":       gname,
            "type":       gtype_norm,
            "area":       cell["area"],
            "power":      cell["power"],
            "drive":      cell["drive"],
            "output_net": output_net,
            "input_nets": input_nets,
        })

    return gates


def verilog_to_txt(verilog_path: str, out_path: Optional[str] = None) -> str:
    """
    Convert a gate-level Verilog file to CircuitSense's GATE/NET text format.

    Steps:
      1. Call parse_verilog() to get the list of gate instances.
      2. Build a net_driver map: net_name → gate_name (who drives this net).
      3. Build a nets map: driver_gate → [load_gates] by matching each gate's
         input_nets against net_driver.
      4. Write GATE lines for every gate instance.
      5. Write NET lines for every driver → loads connection.

    The resulting .txt file can be passed directly to circuit_parser and
    sta_engine C++ binaries.

    Args:
        verilog_path: Path to the gate-level .v input file.
        out_path:     Path to write the .txt output. If None, a temp file is
                      created automatically and its path is returned.

    Returns:
        Absolute path to the written .txt file.

    Raises:
        ValueError: If no gates are found in the Verilog file.

    Example:
        txt_path = verilog_to_txt("samples/full_adder_gate.v", "/tmp/fa.txt")
        # txt_path contains GATE and NET lines parseable by C++ tools
    """
    gates = parse_verilog(verilog_path)
    if not gates:
        raise ValueError(f"No gates found in {verilog_path}")

    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix=".txt", prefix="vlsi_")
        os.close(fd)

    # net_driver: maps each output net name to the gate that drives it
    # Used in the next step to resolve input_nets → driver gate name
    net_driver: dict[str, str] = {}
    for g in gates:
        if g["output_net"]:
            net_driver[g["output_net"]] = g["name"]

    # nets: maps each driver gate to the list of gates it feeds
    # Built by checking every gate's input_nets against net_driver
    nets: dict[str, list[str]] = {}
    for g in gates:
        for inp in g["input_nets"]:
            driver = net_driver.get(inp)
            if driver and driver != g["name"]:   # skip self-loops
                nets.setdefault(driver, []).append(g["name"])

    with open(out_path, "w") as f:
        f.write(f"# Auto-converted from {os.path.basename(verilog_path)}\n\n")

        # One GATE line per instance
        for g in gates:
            f.write(
                f"GATE {g['type']} {g['name']} "
                f"drive={g['drive']} area={g['area']} power={g['power']}\n"
            )
        f.write("\n")

        # One NET line per driver-to-loads connection
        # dict.fromkeys preserves insertion order and removes duplicates
        for i, (src, dsts) in enumerate(nets.items()):
            dsts_unique = list(dict.fromkeys(dsts))
            f.write(f"NET n{i} {src} {' '.join(dsts_unique)}\n")

    return out_path
