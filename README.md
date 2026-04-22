# CircuitSense

A lightweight mini EDA (Electronic Design Automation) pipeline that parses digital circuit netlists, computes Power-Performance-Area (PPA) metrics, runs Static Timing Analysis, generates automated floorplans, and integrates an agentic LLM to produce design optimization suggestions.

---

## Problem Statement

Modern SoC (System-on-Chip) designs contain billions of transistors across hundreds of functional blocks. Even at the IP block level, engineers routinely deal with netlists containing tens of thousands of standard cells. Before committing a design to expensive tape-out or physical implementation, teams need fast answers to three questions:

> **"Does this block fit within our power budget? Does it close timing at our target frequency? Where are the biggest inefficiencies?"**

Commercial EDA tools (Cadence Innovus, Synopsys Design Compiler) answer these questions — but they cost hundreds of thousands of dollars per license, require weeks of setup, and produce outputs that are hard to quickly interpret or share. For early-stage design exploration, student projects, research prototypes, and IP evaluation, engineers often resort to hand-calculations and spreadsheets.

**This tool solves that gap.** It provides an automated, zero-license, command-line EDA flow that:

- Parses gate-level Verilog or custom netlists
- Computes statistical PPA estimates in under a second
- Runs a full Static Timing Analysis with critical path extraction
- Generates a 2D floorplan visualization
- Produces a shareable HTML report with embedded charts
- Invokes an LLM agent that reasons over the circuit data using tool-use and outputs specific, actionable optimization suggestions

It will not replace Cadence. It will give you correct answers at 9 PM before a design review at 9 AM.

---

## Features

| Feature | Description |
|---|---|
| **Netlist Parser (C++)** | Parses GATE/NET format and gate-level Verilog; outputs area, power, fanout statistics as JSON |
| **Static Timing Analysis (C++)** | Topological-sort STA engine; computes arrival times, required times, slack, WNS, TNS, and critical path |
| **PPA Summary** | Full Power-Performance-Area report: total area (um²), power (uW), power density, max frequency estimate |
| **Verilog Parser (Python)** | Parses structural Verilog (positional and named-port styles); maps to standard cell library |
| **Yosys Integration** | Optional RTL synthesis via Yosys — feed it behavioral Verilog, get a gate-level netlist back |
| **Floorplanner (Python)** | Row-based gate placement with type-grouped layout; renders color-coded PNG |
| **HTML Report** | Self-contained report with embedded power pie chart, area bar chart, slack histogram, floorplan, and timing table |
| **Agentic LLM (Claude)** | Tool-use loop where Claude calls structured analysis tools iteratively before generating optimization suggestions |
| **Test Suite** | 45 pytest tests covering C++ binaries, Python modules, STA correctness, and report generation |

---

## Real-World Use Cases

**1. Early Design Exploration**
Before writing RTL, architects can sketch a gate-level estimate of a block (e.g., an FPU, AES core, or CNN accelerator) and immediately see whether the power/area budget is feasible at a given process node.

**2. IP Block Evaluation**
When evaluating third-party IP, you receive a gate-level netlist. Run it through this tool to instantly understand the power/area profile, worst-case timing path, and high-fanout nets — before spending days in a full EDA flow.

**3. Student / Research Prototyping**
Academic projects involving custom datapaths, novel arithmetic units, or approximate computing circuits need quick PPA feedback during iterative design. This tool provides that feedback in seconds without a commercial license.

**4. Design Review Prep**
Generate a clean, shareable HTML report with charts and LLM commentary before a design review — without needing access to the full EDA environment.

---

## Architecture

```
Input (.txt netlist or .v Verilog)
          │
          ▼
  ┌───────────────┐
  │ Verilog Parser│  ← Python: parses gate-level .v
  │ (if .v input) │    converts to GATE/NET format
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │Circuit Parser │  ← C++: computes power, area,
  │  (C++ binary) │    fanout stats → JSON
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │  STA Engine   │  ← C++: topological sort,
  │  (C++ binary) │    arrival/required times,
  │               │    slack, critical path → JSON
  └───────┬───────┘
          │
    ┌─────┴──────┐
    │            │
    ▼            ▼
┌────────┐  ┌─────────┐
│Floor-  │  │  HTML   │  ← Python: matplotlib charts,
│planner │  │ Report  │    base64-embedded, self-contained
└────────┘  └────┬────┘
                 │
                 ▼
          ┌────────────┐
          │ LLM Agent  │  ← Claude tool-use loop:
          │  (Claude)  │    5 structured tools,
          │            │    iterative reasoning,
          │            │    optimization output
          └────────────┘
```

---

## Project Structure

```
VLSI_/
├── main.py                        # CLI entry point — full EDA flow
├── sample_circuit.txt             # Sample 4-bit adder netlist (19 gates)
├── requirements.txt
│
├── parser/
│   ├── circuit_parser.cpp         # Parses netlist → PPA JSON
│   ├── sta_engine.cpp             # STA: critical path, slack, frequency
│   └── Makefile
│
├── samples/
│   ├── full_adder_gate.v          # 1-bit full adder (5 gates)
│   ├── alu_simple_gate.v          # 4-bit ALU (50+ gates)
│   ├── counter_4bit_gate.v        # Synchronous counter with DFFs
│   └── half_adder_rtl.v           # RTL Verilog for Yosys demo
│
├── vlsi/
│   ├── verilog_parser.py          # Gate-level Verilog → GATE/NET format
│   ├── yosys_wrapper.py           # Yosys synthesis wrapper
│   ├── floorplanner.py            # 2D row-based placement + matplotlib
│   ├── report.py                  # Self-contained HTML report generator
│   └── llm_agent.py               # Claude agentic tool-use loop
│
├── tests/
│   ├── conftest.py                # Shared fixtures
│   ├── test_parser.py             # C++ parser tests (11 tests)
│   ├── test_verilog_parser.py     # Verilog parser tests (9 tests)
│   ├── test_sta.py                # STA engine tests (10 tests)
│   ├── test_floorplanner.py       # Floorplanner tests (8 tests)
│   └── test_report.py             # HTML report tests (7 tests)
│
└── output/                        # Generated floorplans and reports
```

---

## Netlist Format

The custom `.txt` netlist format is human-readable and easy to generate from any synthesis tool:

```
# VLSI Circuit Netlist
# GATE  <type> <name> drive=<int> area=<float_um2> power=<float_uW>
# NET   <net_name> <src_gate> <dst_gate1> [dst_gate2 ...]

GATE NAND2  g1   drive=1  area=1.44  power=2.10
GATE XOR2   g2   drive=1  area=2.88  power=3.80
GATE DFF    ff1  drive=2  area=5.40  power=8.20

NET  n1  g1   g2
NET  n2  g2   ff1
```

Gate-level Verilog (both positional and named-port styles) is also supported directly:

```verilog
module full_adder (a, b, cin, sum, cout);
    XOR2 g1 (w1, a, b);
    XOR2 g2 (sum, w1, cin);
    AND2 g3 (w2, a, b);
    AND2 g4 (w3, w1, cin);
    OR2  g5 (cout, w2, w3);
endmodule
```

---

## Installation

**Prerequisites:** Python 3.11+, g++ with C++17 support

```bash
# Clone and enter the project
git clone <repo-url>
cd VLSI_

# Create virtual environment and install Python dependencies
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Compile C++ tools (auto-triggered by main.py, or run manually)
make -C parser
```

**Optional — Yosys (for RTL synthesis):**
```bash
# macOS
brew install yosys

# Ubuntu/Debian
sudo apt install yosys
```

---

## Usage

```bash
# Activate the virtual environment first
source .venv/bin/activate
```

### Basic — stats and timing only (no API key needed)
```bash
python main.py --no-llm
```

### Full run with LLM optimization suggestions
```bash
export ANTHROPIC_API_KEY=your_key_here
python main.py
```

### Analyse a gate-level Verilog file
```bash
python main.py samples/full_adder_gate.v --no-llm
python main.py samples/counter_4bit_gate.v --period 5.0 --no-llm
```

### Synthesize RTL Verilog via Yosys then analyse
```bash
# Requires Yosys installed
python main.py samples/half_adder_rtl.v --no-llm
```

### Custom clock target
```bash
python main.py sample_circuit.txt --period 2.5      # 2.5 ns = 400 MHz target
```

### Skip individual stages
```bash
python main.py --no-floor                # skip floorplanning
python main.py --no-report               # terminal output only
python main.py --no-llm --no-report      # bare PPA + timing to terminal
```

### Custom output directory
```bash
python main.py --output ./my_reports
```

---

## Example Output

### Terminal
```
[*] Input: sample_circuit.txt
[*] Running circuit parser...

==========================================================
  VLSI Circuit Statistics
==========================================================
  Gates          : 19 (comb=15, seq=4)
  Total Area     : 51.84 um²
  Total Power    : 70.10 uW
  Power Density  : 1.3522 uW/um²
  Max Power Gate : ff_a (8.20 uW)
  Nets           : 16 | Avg fanout: 1.44 | Max fanout: 4 (n_buf_clk)

  Gate Type Breakdown:
    DFF      x4    power=32.80 uW  area=21.60 um²
    XOR2     x3    power=12.10 uW  area=9.36 um²
    AND2     x2    power=5.50 uW   area=4.32 um²
    ...
==========================================================
[*] Running static timing analysis...

==========================================================
  Static Timing Analysis
==========================================================
  Target Period  : 10.00 ns
  Critical Path  : 0.7100 ns
  Max Frequency  : 1408.45 MHz
  WNS            : 9.2900 ns
  TNS            : 0.0000 ns
  Timing         : PASS ✓
  Path           : g_buf2 → g_and2 → g_or1 → g_nand1 → g_nor1 → ff_sum
==========================================================
[+] Floorplan saved: output/sample_circuit_floorplan.png
[+] Report saved:    output/sample_circuit_report.html
```

### HTML Report
The generated report (`output/*.html`) includes:
- PPA summary cards (gates, area, power, frequency, WNS)
- Power breakdown pie chart
- Area utilization bar chart
- Slack distribution histogram
- Color-coded 2D floorplan
- Full gate timing table with arrival/required/slack per gate
- LLM optimization suggestions (when API key is set)

### LLM Agent Output (example)
```
[tool] get_circuit_summary()
[tool] get_timing_analysis()
[tool] get_power_breakdown()
[tool] get_fanout_analysis({"threshold": 3})

Based on the circuit analysis:

**Power Optimization**
- DFF cells consume 32.80 uW — 46.8% of total power. Consider clock gating
  on ff_b and ff_carry when the enable signal is inactive.
- XOR2 gates account for 17.3% of power. If this is an adder, evaluate
  replacing the ripple-carry XOR chain with a carry-select structure...

**Priority Action**
Add clock gating logic to the four DFF instances. At typical toggle rates,
this alone can reduce dynamic power by 20–35% with minimal area overhead.
```

---

## Running Tests

```bash
# Run all 45 tests
python -m pytest tests/ -v

# Run a specific module
python -m pytest tests/test_sta.py -v
python -m pytest tests/test_verilog_parser.py -v

# Run with coverage
pip install pytest-cov
python -m pytest tests/ --cov=vlsi --cov-report=term-missing
```

Expected output: **45 passed**

---

## STA Engine — How It Works

The C++ `sta_engine` implements a standard forward/backward timing analysis:

1. **Graph construction** — builds a directed gate graph from NET declarations
2. **Topological sort** — Kahn's algorithm; DFF outputs treated as launch points (cycle-breaking)
3. **Forward pass** — `AT[g] = max(AT[predecessors]) + delay[g]`
4. **Backward pass** — `RAT[g] = min(RAT[successors]) − delay[successor]`
5. **Slack** — `slack[g] = RAT[g] − AT[g]`; negative = timing violation
6. **WNS/TNS** — worst negative slack and total negative slack across all gates
7. **Critical path** — traced backward from the gate with maximum arrival time

Gate delays use representative 28nm standard cell values (configurable in source):

| Gate | Delay (ns) | Gate | Delay (ns) |
|------|-----------|------|-----------|
| INV / BUF | 0.06 | XOR2 / XNOR2 | 0.20 |
| NAND2 / NOR2 | 0.08 | MUX2 | 0.18 |
| AND2 / OR2 | 0.12 | DFF (CK→Q) | 0.25 |

---

## Standard Cell Library

Area and power estimates use representative 28nm LP values. To target a different process node, update `STD_CELL` in [`vlsi/verilog_parser.py`](vlsi/verilog_parser.py) and `GATE_DELAY` in [`parser/sta_engine.cpp`](parser/sta_engine.cpp).

| Cell | Area (um²) | Power (uW) |
|------|-----------|-----------|
| INV / BUF | 0.72 | 0.90 |
| NAND2 / NOR2 | 1.44 | 2.10 / 1.80 |
| AND2 / OR2 | 1.80 | 2.40 / 2.30 |
| XOR2 | 2.88 | 3.80 |
| DFF | 5.40 | 8.20 |

---

## Limitations

This is a design-exploration tool, not a sign-off tool. Known simplifications:

- **No parasitics** — wire RC delay is not modelled; all delay is gate intrinsic
- **No clock uncertainty** — setup/hold margin, jitter, and skew are not included
- **Single clock domain** — multi-clock STA and false path constraints are not supported
- **Statistical area/power** — values are library averages, not instance-specific
- **No DRC/LVS** — the floorplanner does not enforce design rules

For sign-off analysis, use Synopsys PrimeTime, Cadence Tempus, or OpenSTA.

---

## Tech Stack

- **C++17** — circuit parser and STA engine (performance-critical path)
- **Python 3.11+** — orchestration, Verilog parsing, floorplanning, reporting
- **Anthropic Claude API** — agentic LLM with structured tool-use
- **matplotlib** — floorplan visualization and chart generation
- **pytest** — 45-test suite covering all modules
- **Yosys** (optional) — open-source RTL synthesis

---

## License

MIT License. See [LICENSE](LICENSE) for details.
