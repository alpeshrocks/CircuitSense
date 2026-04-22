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

struct Gate {
    std::string type;
    std::string name;
    int drive;
    double area;    // um^2
    double power;   // uW
};

struct Net {
    std::string name;
    std::string src;
    std::vector<std::string> dsts;
    int fanout() const { return static_cast<int>(dsts.size()); }
};

static std::string trim(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

static std::string parseKV(const std::string& token, const std::string& key) {
    // parse "key=value" token
    size_t eq = token.find('=');
    if (eq == std::string::npos) return "";
    if (token.substr(0, eq) == key) return token.substr(eq + 1);
    return "";
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: circuit_parser <netlist_file>\n";
        return 1;
    }

    std::ifstream fin(argv[1]);
    if (!fin.is_open()) {
        std::cerr << "Error: cannot open file " << argv[1] << "\n";
        return 1;
    }

    std::vector<Gate> gates;
    std::vector<Net> nets;

    std::string line;
    while (std::getline(fin, line)) {
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;

        std::istringstream iss(line);
        std::string keyword;
        iss >> keyword;

        if (keyword == "GATE") {
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
            Net n;
            iss >> n.name >> n.src;
            std::string dst;
            while (iss >> dst) n.dsts.push_back(dst);
            nets.push_back(n);
        }
    }
    fin.close();

    if (gates.empty()) {
        std::cerr << "Error: no gates found in netlist.\n";
        return 1;
    }

    // --- Statistics ---
    double total_area  = 0.0;
    double total_power = 0.0;
    std::map<std::string, int>    type_count;
    std::map<std::string, double> type_power;
    std::map<std::string, double> type_area;

    double max_gate_power = 0.0;
    std::string max_power_gate;
    double max_gate_area  = 0.0;
    std::string max_area_gate;

    int seq_count  = 0; // DFF
    int comb_count = 0;

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

    double power_density = (total_area > 0) ? total_power / total_area : 0.0;
    double avg_power = total_power / gates.size();
    double avg_area  = total_area  / gates.size();

    // fanout stats
    int total_fanout = 0, max_fanout = 0;
    std::string max_fanout_net;
    int high_fanout_nets = 0; // fanout > 4
    for (const auto& n : nets) {
        int fo = n.fanout();
        total_fanout += fo;
        if (fo > max_fanout) { max_fanout = fo; max_fanout_net = n.name; }
        if (fo > 4) high_fanout_nets++;
    }
    double avg_fanout = nets.empty() ? 0.0 : static_cast<double>(total_fanout) / nets.size();

    // --- JSON output ---
    std::cout << std::fixed << std::setprecision(4);
    std::cout << "{\n";
    std::cout << "  \"total_gates\": "          << gates.size()   << ",\n";
    std::cout << "  \"combinational_gates\": "  << comb_count     << ",\n";
    std::cout << "  \"sequential_gates\": "     << seq_count      << ",\n";
    std::cout << "  \"total_area_um2\": "       << total_area     << ",\n";
    std::cout << "  \"total_power_uW\": "       << total_power    << ",\n";
    std::cout << "  \"power_density_uW_um2\": " << power_density  << ",\n";
    std::cout << "  \"avg_gate_power_uW\": "    << avg_power      << ",\n";
    std::cout << "  \"avg_gate_area_um2\": "    << avg_area       << ",\n";
    std::cout << "  \"max_power_gate\": \""     << max_power_gate << "\",\n";
    std::cout << "  \"max_power_gate_uW\": "    << max_gate_power << ",\n";
    std::cout << "  \"max_area_gate\": \""      << max_area_gate  << "\",\n";
    std::cout << "  \"max_area_gate_um2\": "    << max_gate_area  << ",\n";
    std::cout << "  \"total_nets\": "           << nets.size()    << ",\n";
    std::cout << "  \"avg_fanout\": "           << avg_fanout     << ",\n";
    std::cout << "  \"max_fanout\": "           << max_fanout     << ",\n";
    std::cout << "  \"max_fanout_net\": \""     << max_fanout_net << "\",\n";
    std::cout << "  \"high_fanout_nets\": "     << high_fanout_nets << ",\n";

    // gate type breakdown
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

    // individual gate list (for floorplanner / STA downstream)
    std::cout << "  \"gates\": [\n";
    for (size_t gi = 0; gi < gates.size(); gi++) {
        const auto& g = gates[gi];
        std::cout << "    {\"name\": \"" << g.name << "\", \"type\": \"" << g.type
                  << "\", \"drive\": " << g.drive
                  << ", \"area\": " << g.area
                  << ", \"power\": " << g.power << "}";
        if (gi + 1 < gates.size()) std::cout << ",";
        std::cout << "\n";
    }
    std::cout << "  ]\n";
    std::cout << "}\n";

    return 0;
}
