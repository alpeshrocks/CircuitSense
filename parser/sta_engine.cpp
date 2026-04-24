/**
 * sta_engine.cpp — CircuitSense Static Timing Analysis Engine
 * ============================================================
 * PURPOSE:
 *   Performs gate-level Static Timing Analysis (STA) on a GATE/NET netlist.
 *   STA is the standard technique used in every real EDA flow to verify that
 *   a digital circuit can operate at a target clock frequency without
 *   setup-time violations.
 *
 * ALGORITHM — three-phase approach:
 *
 *   Phase 1 — Graph construction
 *     Build a directed acyclic graph (DAG) where nodes are gates and edges
 *     represent signal flow through nets (src → dst).
 *     DFF outputs are treated as launch points (cycle breakers): their
 *     predecessors are ignored so that register-to-register paths are
 *     analyzed as combinational segments.
 *
 *   Phase 2 — Forward pass (Arrival Times)
 *     Process gates in topological order (Kahn's algorithm).
 *     AT[g] = max(AT[predecessor] for all predecessors) + delay[g]
 *     Gates with no predecessors (primary inputs / DFF outputs) get
 *     AT = delay[g] (just their own intrinsic delay).
 *
 *   Phase 3 — Backward pass (Required Times + Slack)
 *     Process in reverse topological order.
 *     RAT[g] = min(RAT[successor] - delay[successor]) for all successors
 *     Gates with no successors (primary outputs / DFF D-pins) get
 *     RAT = target_period.
 *     Slack[g] = RAT[g] - AT[g]
 *       Positive slack → gate has timing margin
 *       Negative slack → timing VIOLATION (path is too slow)
 *
 * KEY METRICS PRODUCED:
 *   - critical_path_ns : delay of the longest combinational path
 *   - max_frequency_mhz: 1000 / critical_path_ns
 *   - timing_met       : true if critical_path_ns <= target_period
 *   - WNS (Worst Negative Slack): slack of the most critical gate
 *   - TNS (Total Negative Slack): sum of all negative slacks
 *   - critical_path    : ordered list of gate names on the critical path
 *
 * GATE DELAY TABLE:
 *   Representative 28nm LP standard cell delays in nanoseconds.
 *   Sourced from publicly available 28nm characterisation data.
 *   Override by editing GATE_DELAY below and recompiling.
 *
 * INPUT (same GATE/NET format as circuit_parser):
 *   GATE <type> <name> drive=N area=F power=F
 *   NET  <name> <src>  <dst1> [<dst2> ...]
 *
 * OUTPUT (stdout, valid JSON):
 *   {
 *     "target_period_ns"  : float,   -- clock period provided via --period
 *     "critical_path_ns"  : float,   -- longest combinational path delay
 *     "max_frequency_mhz" : float,   -- 1000 / critical_path_ns
 *     "timing_met"        : bool,    -- critical_path_ns <= target_period
 *     "wns_ns"            : float,   -- worst negative slack (positive = no violation)
 *     "tns_ns"            : float,   -- total negative slack (0 = timing clean)
 *     "wns_gate"          : string,  -- gate name with worst slack
 *     "critical_path"     : [string, ...],  -- gate names in path order
 *     "gate_timing"       : [
 *       {name, type, delay_ns, arrival_ns, required_ns, slack_ns}, ...
 *     ]
 *   }
 *
 * USAGE:
 *   ./sta_engine <netlist_file> [--period <ns>]
 *   Default period: 10.0 ns  (100 MHz)
 *
 * COMPILE:
 *   g++ -std=c++17 -O2 -o sta_engine sta_engine.cpp
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <map>
#include <set>
#include <queue>
#include <algorithm>
#include <iomanip>
#include <limits>
#include <cmath>

// ── Standard cell delay table ─────────────────────────────────────────────────
// Values are intrinsic gate delays in nanoseconds at 28nm LP corner (typical).
// These approximate the combinational delay through each cell type.
// DFF represents clock-to-Q propagation delay.
// Any gate type not listed defaults to 0.10 ns.
static const std::map<std::string, double> GATE_DELAY = {
    {"INV",   0.06},  // inverter       — fastest cell
    {"BUF",   0.06},  // buffer         — same as INV structurally
    {"NAND2", 0.08},  // 2-input NAND   — faster than AND2 (CMOS advantage)
    {"NOR2",  0.08},  // 2-input NOR
    {"AND2",  0.12},  // 2-input AND    — NAND2 + INV internally
    {"OR2",   0.12},  // 2-input OR
    {"XOR2",  0.20},  // 2-input XOR    — most complex 2-input gate
    {"XNOR2", 0.20},  // 2-input XNOR
    {"NAND3", 0.10},  // 3-input NAND
    {"NOR3",  0.10},  // 3-input NOR
    {"MUX2",  0.18},  // 2:1 mux        — requires transmission gate
    {"AOI21", 0.10},  // AND-OR-Invert  — common compound cell
    {"DFF",   0.25},  // flip-flop      — clock-to-Q delay
};

// ── Data structures ───────────────────────────────────────────────────────────

/**
 * Gate — minimal gate representation for timing analysis.
 * Only name, type, and intrinsic delay are needed by the STA engine.
 */
struct Gate {
    std::string name;   // instance identifier, e.g. "g_xor1"
    std::string type;   // cell type, e.g. "XOR2"
    double delay = 0.10; // intrinsic propagation delay (ns)
};

/**
 * Net — a wire from one driver to one or more loads.
 * Used to build the gate-level timing graph.
 */
struct Net {
    std::string name;                // logical net name
    std::string src;                 // driving gate instance name
    std::vector<std::string> dsts;  // load gate instance names
};

// ── Utility ───────────────────────────────────────────────────────────────────

/**
 * trim — strip leading/trailing whitespace from a string.
 * Handles spaces, tabs, carriage returns, and newlines.
 */
static std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    return s.substr(a, s.find_last_not_of(" \t\r\n") - a + 1);
}

// ── Main ──────────────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: sta_engine <netlist> [--period <ns>]\n";
        return 1;
    }

    // ── Parse command-line arguments ─────────────────────────────────────────
    double target_period = 10.0;   // default: 10 ns = 100 MHz
    std::string netlist_file = argv[1];
    for (int i = 2; i < argc - 1; i++) {
        if (std::string(argv[i]) == "--period")
            target_period = std::stod(argv[i + 1]);
    }

    // ── 1. Read and parse the netlist ────────────────────────────────────────
    std::ifstream fin(netlist_file);
    if (!fin.is_open()) {
        std::cerr << "Error: cannot open " << netlist_file << "\n";
        return 1;
    }

    std::vector<Gate> gate_vec;
    std::vector<Net>  net_vec;
    std::map<std::string, Gate*> gate_map;  // name → Gate* for O(log n) lookup

    std::string line;
    while (std::getline(fin, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;

        std::istringstream iss(line);
        std::string kw;
        iss >> kw;

        if (kw == "GATE") {
            Gate g;
            iss >> g.type >> g.name;
            // Look up delay from table; fall back to 0.10 ns for unknown types
            auto it = GATE_DELAY.find(g.type);
            g.delay = (it != GATE_DELAY.end()) ? it->second : 0.10;
            gate_vec.push_back(g);

        } else if (kw == "NET") {
            Net n;
            iss >> n.name >> n.src;
            std::string d;
            while (iss >> d) n.dsts.push_back(d);
            net_vec.push_back(n);
        }
    }
    fin.close();

    if (gate_vec.empty()) {
        std::cerr << "Error: no gates found.\n";
        return 1;
    }

    // Build name → pointer map after all gates are pushed
    // (vector reallocation would invalidate earlier pointers)
    for (auto& g : gate_vec) gate_map[g.name] = &g;

    // ── 2. Build directed timing graph ───────────────────────────────────────
    // succs[g] = list of gates that g drives (g → succ via some net)
    // preds[g] = list of gates that drive g  (pred → g via some net)
    // in_deg[g] = number of predecessors (for topological sort)
    std::map<std::string, std::vector<std::string>> succs;
    std::map<std::string, std::vector<std::string>> preds;
    std::map<std::string, int> in_deg;

    for (auto& g : gate_vec) {
        succs[g.name]  = {};
        preds[g.name]  = {};
        in_deg[g.name] = 0;
    }

    for (auto& net : net_vec) {
        if (gate_map.find(net.src) == gate_map.end()) continue;
        for (auto& dst : net.dsts) {
            if (gate_map.find(dst) == gate_map.end()) continue;

            // CYCLE BREAKING: DFF outputs are treated as timing launch points.
            // In a synchronous design, data flows: DFF_Q → logic → DFF_D.
            // We analyse each register-to-register segment as a standalone
            // combinational path. Ignoring DFF-as-source edges breaks
            // the feedback loop and allows topological sort to work.
            if (gate_map[net.src]->type == "DFF") continue;

            succs[net.src].push_back(dst);
            preds[dst].push_back(net.src);
            in_deg[dst]++;
        }
    }

    // ── 3. Topological sort (Kahn's algorithm) ────────────────────────────────
    // Start with all gates that have no combinational predecessors.
    // These are: primary inputs, DFF instances (their Q is a launch point),
    // and any gate not driven by another gate in the netlist.
    std::queue<std::string> q;
    for (auto& [name, deg] : in_deg)
        if (deg == 0) q.push(name);

    std::vector<std::string> topo;  // final processing order
    while (!q.empty()) {
        auto g = q.front(); q.pop();
        topo.push_back(g);
        // Decrement successor in-degrees; enqueue newly free successors
        for (auto& s : succs[g])
            if (--in_deg[s] == 0) q.push(s);
    }

    // If not all gates were sorted (cycle present despite DFF breaking),
    // append remaining gates in declaration order as a best-effort fallback.
    std::set<std::string> visited(topo.begin(), topo.end());
    for (auto& g : gate_vec)
        if (!visited.count(g.name)) topo.push_back(g.name);

    // ── 4. Forward pass — Arrival Times (AT) ─────────────────────────────────
    // AT[g] = the time at which gate g's output signal is stable.
    // Formula: AT[g] = max(AT[all predecessors]) + delay[g]
    // Gates with no predecessors start fresh: AT = delay[g]
    // crit_pred[g] tracks which predecessor set the arrival time (path trace).
    std::map<std::string, double> AT;
    std::map<std::string, std::string> crit_pred;  // for backward path tracing

    for (auto& name : topo) {
        double max_pred_at = 0.0;
        std::string best_pred;
        for (auto& p : preds[name]) {
            if (AT[p] > max_pred_at) {
                max_pred_at = AT[p];
                best_pred   = p;
            }
        }
        AT[name]        = max_pred_at + gate_map[name]->delay;
        crit_pred[name] = best_pred;
    }

    // ── 5. Backward pass — Required Arrival Times (RAT) ──────────────────────
    // RAT[g] = the latest time gate g's output can be valid without violating
    //          the timing constraint of any downstream endpoint.
    // Formula: RAT[g] = min(RAT[successor] - delay[successor]) for all successors
    // Gates with no successors (endpoints): RAT = target_period
    // This propagates the clock period requirement back through the graph.
    std::map<std::string, double> RAT;
    for (auto& name : topo) RAT[name] = target_period;  // initialise all to period

    for (auto it = topo.rbegin(); it != topo.rend(); ++it) {
        const auto& name = *it;
        for (auto& p : preds[name]) {
            // Required time at predecessor's output =
            // successor's required time minus successor's own delay
            double req = RAT[name] - gate_map[name]->delay;
            if (req < RAT[p]) RAT[p] = req;
        }
    }

    // ── 6. Slack, WNS, TNS ───────────────────────────────────────────────────
    // Slack[g] = RAT[g] - AT[g]
    //   > 0 : gate has timing margin (can tolerate more delay)
    //   = 0 : gate is exactly on the critical path
    //   < 0 : timing VIOLATION (signal arrives too late)
    //
    // WNS (Worst Negative Slack) = most negative slack in the design
    //   If WNS >= 0: design closes timing
    //   If WNS <  0: design has violations; magnitude = amount to recover
    //
    // TNS (Total Negative Slack) = sum of all negative slacks
    //   Measures total severity of all violations, not just the worst
    double wns = std::numeric_limits<double>::max();
    double tns = 0.0;
    std::string wns_gate;

    std::map<std::string, double> slack;
    for (auto& name : topo) {
        slack[name] = RAT[name] - AT[name];
        if (slack[name] < wns) { wns = slack[name]; wns_gate = name; }
        if (slack[name] < 0)   tns += slack[name];
    }

    // ── 7. Trace critical path ────────────────────────────────────────────────
    // The critical path is the longest path through the combinational graph.
    // It starts at the gate with maximum arrival time and follows crit_pred[]
    // backward to a gate with no predecessor.
    double cp_delay = 0.0;
    std::string cp_end;
    for (auto& [n, at] : AT)
        if (at > cp_delay) { cp_delay = at; cp_end = n; }

    std::vector<std::string> cp;
    for (std::string cur = cp_end; !cur.empty(); cur = crit_pred[cur])
        cp.push_back(cur);
    std::reverse(cp.begin(), cp.end());  // start-to-end order

    // Maximum operating frequency = reciprocal of critical path delay
    double fmax        = (cp_delay > 0) ? 1000.0 / cp_delay : 0.0;  // MHz
    bool   timing_met  = (cp_delay <= target_period);

    // ── 8. Emit JSON to stdout ────────────────────────────────────────────────
    std::cout << std::fixed << std::setprecision(4);
    std::cout << "{\n";
    std::cout << "  \"target_period_ns\": "  << target_period           << ",\n";
    std::cout << "  \"critical_path_ns\": "  << cp_delay                << ",\n";
    std::cout << "  \"max_frequency_mhz\": " << fmax                    << ",\n";
    std::cout << "  \"timing_met\": "        << (timing_met ? "true" : "false") << ",\n";
    std::cout << "  \"wns_ns\": "            << wns                     << ",\n";
    std::cout << "  \"tns_ns\": "            << tns                     << ",\n";
    std::cout << "  \"wns_gate\": \""        << wns_gate                << "\",\n";

    // Critical path: ordered list of gate names from input to output
    std::cout << "  \"critical_path\": [";
    for (size_t i = 0; i < cp.size(); i++) {
        std::cout << "\"" << cp[i] << "\"";
        if (i + 1 < cp.size()) std::cout << ", ";
    }
    std::cout << "],\n";

    // Per-gate timing table: one entry per gate in topological order
    // arrival_ns  = earliest time output is valid
    // required_ns = latest time output must be valid
    // slack_ns    = required - arrival (negative = violation)
    std::cout << "  \"gate_timing\": [\n";
    for (size_t i = 0; i < topo.size(); i++) {
        const auto& name = topo[i];
        const auto& g    = *gate_map[name];
        std::cout << "    {"
                  << "\"name\": \""      << name         << "\", "
                  << "\"type\": \""      << g.type       << "\", "
                  << "\"delay_ns\": "    << g.delay      << ", "
                  << "\"arrival_ns\": "  << AT[name]     << ", "
                  << "\"required_ns\": " << RAT[name]    << ", "
                  << "\"slack_ns\": "    << slack[name]  << "}";
        if (i + 1 < topo.size()) std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "  ]\n";
    std::cout << "}\n";

    return 0;
}
