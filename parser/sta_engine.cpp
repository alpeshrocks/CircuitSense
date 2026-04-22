// Static Timing Analysis Engine
// Input : netlist file (same GATE/NET format as circuit_parser)
// Output: JSON with critical path, slack, frequency estimate
// Usage : sta_engine <netlist> [--period <ns>]

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

// Representative 28nm standard cell delays (ns)
static const std::map<std::string, double> GATE_DELAY = {
    {"INV",   0.06}, {"BUF",   0.06},
    {"NAND2", 0.08}, {"NOR2",  0.08},
    {"AND2",  0.12}, {"OR2",   0.12},
    {"XOR2",  0.20}, {"XNOR2", 0.20},
    {"NAND3", 0.10}, {"NOR3",  0.10},
    {"MUX2",  0.18}, {"AOI21", 0.10},
    {"DFF",   0.25},
};

struct Gate {
    std::string name, type;
    double delay = 0.10;
};

struct Net {
    std::string name, src;
    std::vector<std::string> dsts;
};

static std::string trim(const std::string& s) {
    size_t a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    return s.substr(a, s.find_last_not_of(" \t\r\n") - a + 1);
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: sta_engine <netlist> [--period <ns>]\n";
        return 1;
    }

    double target_period = 10.0;
    std::string netlist_file = argv[1];
    for (int i = 2; i < argc - 1; i++) {
        if (std::string(argv[i]) == "--period")
            target_period = std::stod(argv[i + 1]);
    }

    std::ifstream fin(netlist_file);
    if (!fin.is_open()) {
        std::cerr << "Error: cannot open " << netlist_file << "\n";
        return 1;
    }

    std::vector<Gate> gate_vec;
    std::vector<Net>  net_vec;
    std::map<std::string, Gate*> gate_map;

    std::string line;
    while (std::getline(fin, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        std::istringstream iss(line);
        std::string kw; iss >> kw;
        if (kw == "GATE") {
            Gate g;
            iss >> g.type >> g.name;
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

    for (auto& g : gate_vec) gate_map[g.name] = &g;

    // --- Build adjacency ---
    std::map<std::string, std::vector<std::string>> succs;   // gate → successors
    std::map<std::string, std::vector<std::string>> preds;   // gate → predecessors
    std::map<std::string, int> in_deg;
    std::map<std::string, std::string> net_of_edge;

    for (auto& g : gate_vec) { succs[g.name] = {}; preds[g.name] = {}; in_deg[g.name] = 0; }

    for (auto& net : net_vec) {
        if (gate_map.find(net.src) == gate_map.end()) continue;
        for (auto& dst : net.dsts) {
            if (gate_map.find(dst) == gate_map.end()) continue;
            // Skip DFF-through edges to break cycles: DFF Q→D paths go through clock boundary
            // Treat DFF as a launch point: its outputs are "fresh" (no predecessors for STA)
            if (gate_map[net.src]->type == "DFF") continue;
            succs[net.src].push_back(dst);
            preds[dst].push_back(net.src);
            in_deg[dst]++;
        }
    }

    // --- Topological sort (Kahn's) ---
    std::queue<std::string> q;
    for (auto& [name, deg] : in_deg)
        if (deg == 0) q.push(name);

    std::vector<std::string> topo;
    while (!q.empty()) {
        auto g = q.front(); q.pop();
        topo.push_back(g);
        for (auto& s : succs[g])
            if (--in_deg[s] == 0) q.push(s);
    }

    // Any remaining nodes (cycle): append in original order
    std::set<std::string> visited(topo.begin(), topo.end());
    for (auto& g : gate_vec)
        if (!visited.count(g.name)) topo.push_back(g.name);

    // --- Forward pass: arrival times ---
    std::map<std::string, double> AT;
    std::map<std::string, std::string> crit_pred;

    for (auto& name : topo) {
        double max_pred = 0.0;
        std::string best_pred;
        for (auto& p : preds[name]) {
            if (AT[p] > max_pred) { max_pred = AT[p]; best_pred = p; }
        }
        AT[name] = max_pred + gate_map[name]->delay;
        crit_pred[name] = best_pred;
    }

    // --- Backward pass: required times ---
    std::map<std::string, double> RAT;
    for (auto& name : topo) RAT[name] = target_period;

    for (auto it = topo.rbegin(); it != topo.rend(); ++it) {
        auto& name = *it;
        for (auto& p : preds[name]) {
            double req = RAT[name] - gate_map[name]->delay;
            if (req < RAT[p]) RAT[p] = req;
        }
    }

    // --- Slack, WNS, TNS ---
    double wns = std::numeric_limits<double>::max();
    double tns = 0.0;
    std::string wns_gate;

    std::map<std::string, double> slack;
    for (auto& name : topo) {
        slack[name] = RAT[name] - AT[name];
        if (slack[name] < wns) { wns = slack[name]; wns_gate = name; }
        if (slack[name] < 0)   tns += slack[name];
    }

    // --- Critical path trace ---
    double cp_delay = 0.0;
    std::string cp_end;
    for (auto& [n, at] : AT)
        if (at > cp_delay) { cp_delay = at; cp_end = n; }

    std::vector<std::string> cp;
    for (std::string cur = cp_end; !cur.empty(); cur = crit_pred[cur])
        cp.push_back(cur);
    std::reverse(cp.begin(), cp.end());

    double fmax = (cp_delay > 0) ? 1000.0 / cp_delay : 0.0; // MHz
    bool timing_met = (cp_delay <= target_period);

    // --- JSON output ---
    std::cout << std::fixed << std::setprecision(4);
    std::cout << "{\n";
    std::cout << "  \"target_period_ns\": "     << target_period << ",\n";
    std::cout << "  \"critical_path_ns\": "     << cp_delay      << ",\n";
    std::cout << "  \"max_frequency_mhz\": "    << fmax          << ",\n";
    std::cout << "  \"timing_met\": "           << (timing_met ? "true" : "false") << ",\n";
    std::cout << "  \"wns_ns\": "               << wns           << ",\n";
    std::cout << "  \"tns_ns\": "               << tns           << ",\n";
    std::cout << "  \"wns_gate\": \""           << wns_gate      << "\",\n";
    std::cout << "  \"critical_path\": [";
    for (size_t i = 0; i < cp.size(); i++) {
        std::cout << "\"" << cp[i] << "\"";
        if (i + 1 < cp.size()) std::cout << ", ";
    }
    std::cout << "],\n";

    std::cout << "  \"gate_timing\": [\n";
    for (size_t i = 0; i < topo.size(); i++) {
        auto& name = topo[i];
        auto& g = *gate_map[name];
        std::cout << "    {\"name\": \"" << name
                  << "\", \"type\": \"" << g.type
                  << "\", \"delay_ns\": " << g.delay
                  << ", \"arrival_ns\": " << AT[name]
                  << ", \"required_ns\": " << RAT[name]
                  << ", \"slack_ns\": " << slack[name] << "}";
        if (i + 1 < topo.size()) std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "  ]\n";
    std::cout << "}\n";

    return 0;
}
