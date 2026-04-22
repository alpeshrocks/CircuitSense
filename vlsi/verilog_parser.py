"""
Gate-level Verilog parser.
Parses simple structural Verilog netlists and converts them to our
GATE/NET .txt format so the C++ tools can process them.
Supports positional and named-port gate instantiations.
"""

import re
import os
import tempfile
from typing import Optional

# Standard cell library: area (um²) and power (uW) per gate type
STD_CELL = {
    "INV":   {"area": 0.72,  "power": 0.90,  "drive": 1},
    "BUF":   {"area": 0.72,  "power": 0.90,  "drive": 1},
    "NOT":   {"area": 0.72,  "power": 0.90,  "drive": 1},
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
    "DFF":   {"area": 5.40,  "power": 8.20,  "drive": 2},
    # Yosys internal primitives
    "$_NOT_":   {"area": 0.72, "power": 0.90, "drive": 1},
    "$_AND_":   {"area": 1.80, "power": 2.40, "drive": 1},
    "$_OR_":    {"area": 1.80, "power": 2.30, "drive": 1},
    "$_XOR_":   {"area": 2.88, "power": 3.80, "drive": 1},
    "$_NAND_":  {"area": 1.44, "power": 2.10, "drive": 1},
    "$_NOR_":   {"area": 1.44, "power": 1.80, "drive": 1},
    "$_DFF_P_": {"area": 5.40, "power": 8.20, "drive": 2},
    "$_DFF_N_": {"area": 5.40, "power": 8.20, "drive": 2},
    "$_MUX_":   {"area": 3.60, "power": 4.20, "drive": 1},
}

# Output pin name for named-port format
OUTPUT_PIN = {
    "INV": "Y", "BUF": "Y", "NOT": "Y",
    "NAND2": "Y", "NOR2": "Y", "AND2": "Y", "OR2": "Y",
    "XOR2": "Y", "XNOR2": "Y",
    "NAND3": "Y", "NOR3": "Y", "AND3": "Y", "OR3": "Y",
    "MUX2": "Y", "DFF": "Q",
    "$_NOT_": "Y", "$_AND_": "Y", "$_OR_": "Y",
    "$_XOR_": "Y", "$_NAND_": "Y", "$_NOR_": "Y",
    "$_DFF_P_": "Q", "$_DFF_N_": "Q", "$_MUX_": "Y",
}

_GATE_RE = re.compile(
    r'^\s*'
    r'([\w\$\\]+)'         # gate type (group 1)
    r'\s+#\([^)]*\)\s*'    # optional: timing annotation #(...)
    r'|'
    r'^\s*([\w\$\\]+)'     # gate type (group 2, no timing)
    r'\s+',
    re.VERBOSE
)


def _norm_type(t: str) -> str:
    """Normalise gate type to uppercase key used in STD_CELL."""
    return t.strip("\\").upper()


def _parse_port_list(port_str: str):
    """
    Parse port list string (inside the outer parentheses of a gate instantiation).
    Returns:
        - positional: list of signal names  [out, in1, in2, ...]
        - named:      dict {pin_name: signal_name}
    """
    port_str = port_str.strip()
    named = {}
    positional = []

    # Named ports: .PIN(SIGNAL)
    named_matches = re.findall(r'\.(\w+)\s*\(([^)]*)\)', port_str)
    if named_matches:
        for pin, sig in named_matches:
            named[pin.strip()] = sig.strip()
        return None, named

    # Positional: split by comma, strip constants like 1'b0
    for tok in port_str.split(','):
        tok = tok.strip()
        if re.match(r"^\d+'[bBhHoO]", tok):
            tok = f"_const_{tok}"
        positional.append(tok)
    return positional, None


def parse_verilog(filepath: str) -> list[dict]:
    """
    Parse a gate-level Verilog file.
    Returns a list of gate dicts:
      {name, type, area, power, drive, output_net, input_nets}
    """
    with open(filepath) as f:
        content = f.read()

    # Strip single-line comments
    content = re.sub(r'//.*', '', content)
    # Strip block comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

    # Remove module / endmodule wrappers and declarations
    # We just look for gate instantiation lines
    gates = []
    seen_names = set()

    # Match gate instantiation lines:
    # TYPE [#(...)] INSTANCE_NAME (ports) ;
    gate_inst_re = re.compile(
        r'([\w\$\\]+)'             # gate type
        r'(?:\s*#\s*\([^)]*\))?'  # optional timing
        r'\s+([\w\$\\]+)'          # instance name
        r'\s*\(([^;]*?)\)\s*;',   # port list
        re.DOTALL
    )

    skip_keywords = {
        'MODULE', 'ENDMODULE', 'INPUT', 'OUTPUT', 'INOUT',
        'WIRE', 'REG', 'ASSIGN', 'ALWAYS', 'BEGIN', 'END',
        'IF', 'ELSE', 'CASE', 'ENDCASE', 'PARAMETER', 'LOCALPARAM',
    }

    for m in gate_inst_re.finditer(content):
        gtype_raw, gname, port_str = m.group(1), m.group(2), m.group(3)
        gtype_norm = _norm_type(gtype_raw)

        if gtype_norm in skip_keywords:
            continue
        if gname.upper() in skip_keywords:
            continue

        # Deduplicate instance names
        if gname in seen_names:
            gname = f"{gname}_{len(seen_names)}"
        seen_names.add(gname)

        positional, named = _parse_port_list(port_str)

        # Determine output net
        output_net = None
        input_nets = []

        if named:
            out_pin = OUTPUT_PIN.get(gtype_norm, "Y")
            output_net = named.get(out_pin, named.get("Z", named.get("Q")))
            input_nets = [v for k, v in named.items() if k != out_pin and k not in ("Z", "Q")]
        elif positional:
            output_net = positional[0] if positional else None
            input_nets = positional[1:]

        # Remove constant/empty signals from inputs
        input_nets = [n for n in input_nets if n and not n.startswith("_const_")]

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
    Convert a gate-level Verilog file to our GATE/NET .txt format.
    Writes to out_path (or a temp file) and returns the path.
    """
    gates = parse_verilog(verilog_path)
    if not gates:
        raise ValueError(f"No gates found in {verilog_path}")

    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix=".txt", prefix="vlsi_")
        os.close(fd)

    # Build net → driver mapping (output_net → gate_name)
    net_driver: dict[str, str] = {}
    for g in gates:
        if g["output_net"]:
            net_driver[g["output_net"]] = g["name"]

    # Build nets: driver → [loads]
    nets: dict[str, list[str]] = {}
    for g in gates:
        for inp in g["input_nets"]:
            driver = net_driver.get(inp)
            if driver and driver != g["name"]:
                nets.setdefault(driver, []).append(g["name"])

    with open(out_path, "w") as f:
        f.write(f"# Auto-converted from {os.path.basename(verilog_path)}\n\n")
        for g in gates:
            f.write(f"GATE {g['type']} {g['name']} "
                    f"drive={g['drive']} area={g['area']} power={g['power']}\n")
        f.write("\n")
        for i, (src, dsts) in enumerate(nets.items()):
            dsts_unique = list(dict.fromkeys(dsts))  # preserve order, deduplicate
            f.write(f"NET n{i} {src} {' '.join(dsts_unique)}\n")

    return out_path
