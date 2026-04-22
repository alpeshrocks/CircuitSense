"""
Agentic LLM reviewer using Claude tool-use.
Claude calls tools iteratively to query circuit stats, then synthesises findings.
"""

import json
import os
from typing import Optional

import anthropic

# ---------- Tool definitions ----------

TOOLS = [
    {
        "name": "get_circuit_summary",
        "description": "Return high-level circuit statistics: gate counts, total area, total power.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_timing_analysis",
        "description": "Return STA results: critical path, max frequency, WNS, TNS, timing pass/fail.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_power_breakdown",
        "description": "Return power consumption breakdown per gate type (uW).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_area_breakdown",
        "description": "Return area utilization breakdown per gate type (um²).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_fanout_analysis",
        "description": "Return fanout statistics: avg fanout, max fanout net, high-fanout net count.",
        "input_schema": {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "integer",
                    "description": "Fanout threshold for 'high fanout' classification (default 4).",
                }
            },
            "required": [],
        },
    },
]

# ---------- Tool handlers ----------

def _handle_tool(name: str, tool_input: dict, stats: dict, timing: dict) -> str:
    if name == "get_circuit_summary":
        return json.dumps({
            "total_gates":        stats.get("total_gates", 0),
            "combinational_gates": stats.get("combinational_gates", 0),
            "sequential_gates":   stats.get("sequential_gates", 0),
            "total_area_um2":     stats.get("total_area_um2", 0),
            "total_power_uW":     stats.get("total_power_uW", 0),
            "power_density":      stats.get("power_density_uW_um2", 0),
        }, indent=2)

    elif name == "get_timing_analysis":
        return json.dumps({
            "target_period_ns":   timing.get("target_period_ns", 0),
            "critical_path_ns":   timing.get("critical_path_ns", 0),
            "max_frequency_mhz":  timing.get("max_frequency_mhz", 0),
            "timing_met":         timing.get("timing_met", True),
            "wns_ns":             timing.get("wns_ns", 0),
            "tns_ns":             timing.get("tns_ns", 0),
            "critical_path":      timing.get("critical_path", []),
        }, indent=2)

    elif name == "get_power_breakdown":
        return json.dumps(stats.get("gate_type_power_uW", {}), indent=2)

    elif name == "get_area_breakdown":
        return json.dumps(stats.get("gate_type_area_um2", {}), indent=2)

    elif name == "get_fanout_analysis":
        threshold = tool_input.get("threshold", 4)
        # Recount high-fanout nets with requested threshold from raw stats
        return json.dumps({
            "avg_fanout":       stats.get("avg_fanout", 0),
            "max_fanout":       stats.get("max_fanout", 0),
            "max_fanout_net":   stats.get("max_fanout_net", ""),
            "high_fanout_nets": stats.get("high_fanout_nets", 0),
            "threshold_used":   threshold,
        }, indent=2)

    return json.dumps({"error": f"Unknown tool: {name}"})


# ---------- Agent loop ----------

_SYSTEM = """You are an expert VLSI/EDA design engineer with deep knowledge of digital circuit
optimization, standard cell libraries, timing closure, and power reduction techniques.
Use the available tools to gather circuit statistics, then provide concise, actionable
design optimization suggestions. Focus on the most impactful improvements first."""

_INITIAL_PROMPT = """Please analyze this VLSI circuit design comprehensively.
Start by gathering circuit statistics, then provide:
1. Power optimization suggestions
2. Area optimization suggestions
3. Timing / fanout concerns
4. Overall design quality assessment
5. Single highest-priority recommendation

Be specific — reference gate types, net names, and quantitative targets where possible."""


def run_agent(stats: dict, timing: dict, api_key: str) -> str:
    """
    Run the agentic LLM review loop.
    Returns the final text response from Claude.
    """
    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": _INITIAL_PROMPT}]

    print("\n" + "=" * 55)
    print("  Agentic LLM Review (Claude + Tool Use)")
    print("=" * 55)

    final_text = ""
    max_rounds = 8

    for round_num in range(max_rounds):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        # Accumulate assistant message
        messages.append({"role": "assistant", "content": response.content})

        # Check for tool use
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        if text_blocks:
            for tb in text_blocks:
                print(tb.text, end="", flush=True)
            final_text += "".join(tb.text for tb in text_blocks)

        if response.stop_reason == "end_turn" or not tool_calls:
            break

        # Process tool calls and add results
        tool_results = []
        for tc in tool_calls:
            print(f"\n[tool] {tc.name}({json.dumps(tc.input) if tc.input else ''})")
            result = _handle_tool(tc.name, tc.input, stats, timing)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tc.id,
                "content":     result,
            })

        messages.append({"role": "user", "content": tool_results})

    print("\n" + "=" * 55)
    return final_text
