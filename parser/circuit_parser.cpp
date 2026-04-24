/**
 * circuit_parser.cpp — CircuitSense Gate-Level Netlist Parser
 * ============================================================
 * PURPOSE:
 *   Reads a GATE/NET netlist file, computes Power-Area statistics
 *   for every gate and the circuit as a whole, and writes results
 *   to stdout as a single JSON object consumed by the Python layer.
 *
 * INPUT (netlist file format):
 *   Lines beginning with '#' are comments and are ignored.
 *
 *   GATE <type> <name> drive=<int> area=<float_um2> power=<float_uW>
 *     e.g.  GATE NAND2 g1 drive=1 area=1.44 power=2.10
 *
 *   NET <net_name> <src_gate> <dst_gate1> [dst_gate2 ...]
 *     e.g.  NET n1 g1 g2 g3
 *     The first gate listed after the net name is the driver;
 *     all remaining gates are loads (fanout destinations).
 *
 * OUTPUT (stdout, valid JSON):
 *   {
 *     "total_gates": int,
 *     "combinational_gates": int,      -- all non-DFF gates
 *     "sequential_gates": int,         -- DFF count
 *     "total_area_um2": float,
 *     "total_power_uW": float,
 *     "power_density_uW_um2": float,   -- total_power / total_area
 *     "avg_gate_power_uW": float,
 *     "avg_gate_area_um2": float,
 *     "max_power_gate": string,        -- instance name of hungriest gate
 *     "max_power_gate_uW": float,
 *     "max_area_gate": string,
 *     "max_area_gate_um2": float,
 *     "total_nets": int,
 *     "avg_fanout": float,
 *     "max_fanout": int,
 *     "max_fanout_net": string,
 *     "high_fanout_nets": int,         -- nets with fanout > 4
 *     "gate_type_counts": { type: count, ... },
 *     "gate_type_power_uW": { type: total_power, ... },
 *     "gate_type_area_um2": { type: total_area, ... },
 *     "gates": [ {name, type, drive, area, power}, ... ]
 *   }
 *
 * USAGE:
 *   ./circuit_parser <netlist_file>
 *
 * EXIT CODES:
 *   0 — success
 *   1 — bad arguments, file not found, or empty netlist
 *
 * COMPILE:
 *   g++ -std=c++17 -O2 -o circuit_parser circuit_parser.cpp
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <map>
#include <unordered_map>
#include <algorithm>
#include <cmath>
#include <iomanip>

// ── Data structures ───────────────────────────────────────────────────────────

/**
 * Gate — one standard cell instance in the netlist.
 *
 * Fields:
 *   type  — cell type from library (e.g. "NAND2", "DFF")
 *   name  — unique instance identifier (e.g. "g_nand1")
 *   drive — drive strength (integer multiplier, e.g. 1, 2, 4, 8)
 *   area  — cell area in square micrometres (um²)
 *   power — static + dynamic power estimate in microwatts (uW)
 */
struct Gate {
    std::string type;
    std::string name;
    int    drive = 1;
    double area  = 0.0;   // um²
    double power = 0.0;   // uW
};

/**
 * Net — one wire connecting one driver gate to one or more load gates.
 *
 * Fields:
 *   name  — logical net name (e.g. "n1", "clk")
 *   src   — name of the driving gate instance
 *   dsts  — names of all load gate instances
 *
 * fanout() returns the number of loads driven by this net.
 * High fanout (> 4) typically requires buffering to avoid timing degradation.
 */
struct Net {
    std::string name;
    std::string src;
    std::vector<std::string> dsts;

    /** Returns number of gates this net drives (fanout count). */
    int fanout() const { return static_cast<int>(dsts.size()); }
};

// ── Utility helpers ───────────────────────────────────────────────────────────

/**
 * trim — remove leading and trailing whitespace from a string.
 *
 * @param s  Input string (may have spaces, tabs, CR, LF)
 * @return   Trimmed string; empty string if s is all whitespace
 */
static std::string trim(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

/**
 * parseKV — extract the value from a "key=value" token.
 *
 * @param token  One whitespace-separated word from the netlist line
 * @param key    The expected key name (e.g. "area", "power")
 * @return       Value string if the token matches the key; empty string otherwise
 *
 * Example:  parseKV("area=1.44", "area")  →  "1.44"
 *           parseKV("power=2.10", "area") →  ""
 */
static std::string parseKV(const std::string& token, const std::string& key) {
    size_t eq = token.find('=');
    if (eq == std::string::npos) return "";
    if (token.substr(0, eq) == key) return token.substr(eq + 1);
    return "";
}

// ── Main ──────────────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: circuit_parser <netlist_file>\n";
        return 1;
    }

    // ── 1. Open netlist file ─────────────────────────────────────────────────
    std::ifstream fin(argv[1]);
    if (!fin.is_open()) {
        std::cerr << "Error: cannot open file " << argv[1] << "\n";
        return 1;
    }

    std::vector<Gate> gates;
    std::vector<Net>  nets;

    // ── 2. Parse GATE and NET lines ──────────────────────────────────────────
    // Each line is one of:
    //   GATE <type> <name> drive=N area=F power=F
    //   NET  <name> <src>  <dst1> [<dst2> ...]
    //   # comment  (skipped)
    //   <blank>    (skipped)
    std::string line;
    while (std::getline(fin, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;

        std::istringstream iss(line);
        std::string keyword;
        iss >> keyword;

        if (keyword == "GATE") {
            // Parse: GATE <type> <name> [drive=N] [area=F] [power=F]
            Gate g;
            iss >> g.type >> g.name;
            std::string token;
            while (iss >> token) {
                std::string v;
                if (!(v = parseKV(token, "drive")).empty())  g.drive  = std::stoi(v);
                if (!(v = parseKV(token, "area")).empty())   g.area   = std::stod(v);
                if (!(v = parseKV(token, "power")).empty())  g.power  = std::stod(v);
            }
            gates.push_back(g);

        } else if (keyword == "NET") {
            // Parse: NET <name> <src_gate> <dst_gate...>
            Net n;
            iss >> n.name >> n.src;
            std::string dst;
            while (iss >> dst) n.dsts.push_back(dst);
            nets.push_back(n);
        }
        // Any other keyword is silently ignored (forward-compatible)
    }
    fin.close();

    if (gates.empty()) {
        std::cerr << "Error: no gates found in netlist.\n";
        return 1;
    }

    // ── 3. Compute aggregate statistics ─────────────────────────────────────
    double total_area  = 0.0;
    double total_power = 0.0;

    // Per-type aggregates (sorted alphabetically for deterministic JSON output)
    std::map<std::string, int>    type_count;
    std::map<std::string, double> type_power;
    std::map<std::string, double> type_area;

    // Extremes — track which gate has the highest individual power/area
    double max_gate_power = 0.0;  std::string max_power_gate;
    double max_gate_area  = 0.0;  std::string max_area_gate;

    // Count sequential (DFF) vs combinational gates
    int seq_count = 0, comb_count = 0;

    for (const auto& g : gates) {
        total_area  += g.area;
        total_power += g.power;
        type_count[g.type]++;
        type_power[g.type] += g.power;
        type_area[g.type]  += g.area;

        if (g.power > max_gate_power) { max_gate_power = g.power; max_power_gate = g.name; }
        if (g.area  > max_gate_area)  { max_gate_area  = g.area;  max_area_gate  = g.name; }

        if (g.type == "DFF") seq_count++;
        else                 comb_count++;
    }

    // Derived metrics
    double power_density = (total_area > 0) ? total_power / total_area : 0.0;
    double avg_power     = total_power / static_cast<double>(gates.size());
    double avg_area      = total_area  / static_cast<double>(gates.size());

    // ── 4. Compute fanout statistics ─────────────────────────────────────────
    // Fanout = number of loads a single net drives.
    // High fanout (> 4) degrades timing because the driver must charge more
    // load capacitance; these nets typically need buffer insertion.
    int total_fanout = 0, max_fanout = 0;
    std::string max_fanout_net;
    int high_fanout_nets = 0;   // threshold: fanout > 4

    for (const auto& n : nets) {
        int fo = n.fanout();
        total_fanout += fo;
        if (fo > max_fanout)  { max_fanout = fo; max_fanout_net = n.name; }
        if (fo > 4)           high_fanout_nets++;
    }
    double avg_fanout = nets.empty()
        ? 0.0
        : static_cast<double>(total_fanout) / static_cast<double>(nets.size());

    // ── 5. Emit JSON to stdout ───────────────────────────────────────────────
    // Python reads this with json.loads(subprocess.run(...).stdout)
    std::cout << std::fixed << std::setprecision(4);
    std::cout << "{\n";

    // Top-level scalar metrics
    std::cout << "  \"total_gates\": "          << gates.size()      << ",\n";
    std::cout << "  \"combinational_gates\": "  << comb_count        << ",\n";
    std::cout << "  \"sequential_gates\": "     << seq_count         << ",\n";
    std::cout << "  \"total_area_um2\": "       << total_area        << ",\n";
    std::cout << "  \"total_power_uW\": "       << total_power       << ",\n";
    std::cout << "  \"power_density_uW_um2\": " << power_density     << ",\n";
    std::cout << "  \"avg_gate_power_uW\": "    << avg_power         << ",\n";
    std::cout << "  \"avg_gate_area_um2\": "    << avg_area          << ",\n";
    std::cout << "  \"max_power_gate\": \""     << max_power_gate    << "\",\n";
    std::cout << "  \"max_power_gate_uW\": "    << max_gate_power    << ",\n";
    std::cout << "  \"max_area_gate\": \""      << max_area_gate     << "\",\n";
    std::cout << "  \"max_area_gate_um2\": "    << max_gate_area     << ",\n";
    std::cout << "  \"total_nets\": "           << nets.size()       << ",\n";
    std::cout << "  \"avg_fanout\": "           << avg_fanout        << ",\n";
    std::cout << "  \"max_fanout\": "           << max_fanout        << ",\n";
    std::cout << "  \"max_fanout_net\": \""     << max_fanout_net    << "\",\n";
    std::cout << "  \"high_fanout_nets\": "     << high_fanout_nets  << ",\n";

    // Per-type breakdown objects (used by report.py for charts)
    std::cout << "  \"gate_type_counts\": {\n";
    size_t i = 0;
    for (const auto& kv : type_count) {
        std::cout << "    \"" << kv.first << "\": " << kv.second;
        if (++i < type_count.size()) std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "  },\n";

    std::cout << "  \"gate_type_power_uW\": {\n";
    i = 0;
    for (const auto& kv : type_power) {
        std::cout << "    \"" << kv.first << "\": " << kv.second;
        if (++i < type_power.size()) std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "  },\n";

    std::cout << "  \"gate_type_area_um2\": {\n";
    i = 0;
    for (const auto& kv : type_area) {
        std::cout << "    \"" << kv.first << "\": " << kv.second;
        if (++i < type_area.size()) std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "  },\n";

    // Full gate list — consumed by floorplanner.py (needs area per instance)
    // and sta_engine (needs gate names for timing annotation)
    std::cout << "  \"gates\": [\n";
    for (size_t gi = 0; gi < gates.size(); gi++) {
        const auto& g = gates[gi];
        std::cout << "    {"
                  << "\"name\": \""  << g.name  << "\", "
                  << "\"type\": \""  << g.type  << "\", "
                  << "\"drive\": "   << g.drive << ", "
                  << "\"area\": "    << g.area  << ", "
                  << "\"power\": "   << g.power << "}";
        if (gi + 1 < gates.size()) std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "  ]\n";
    std::cout << "}\n";

    return 0;
}
