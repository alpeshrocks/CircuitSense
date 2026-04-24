"""
vlsi/llm_agent.py — Agentic LLM Circuit Reviewer
=================================================
PURPOSE:
    Run an agentic Claude review loop that uses structured tool-use to
    query circuit statistics and timing data, then synthesises the findings
    into specific, actionable design optimisation suggestions.

    Unlike a simple one-shot prompt (paste all stats → get suggestions),
    this agent DECIDES which data to query, CALLS tools iteratively, and
    REASONS across multiple steps before writing its final response.
    This demonstrates real LLM agent behaviour, not just a wrapper.

HOW IT WORKS (tool-use loop):
    1. Claude receives an initial analysis request with no data attached.
    2. Claude decides to call tools to gather specific statistics.
    3. Each tool call is intercepted by _handle_tool(), which returns
       the requested slice of stats/timing data as a JSON string.
    4. Claude processes the tool results, may call more tools, and
       eventually produces a final text response (stop_reason = "end_turn").
    5. All intermediate tool calls are printed live to the terminal.
    6. The final text is returned for embedding in the HTML report.

AVAILABLE TOOLS (5 structured tools Claude can call):
    get_circuit_summary   — gate counts, total area/power, power density
    get_timing_analysis   — critical path, max frequency, WNS, TNS
    get_power_breakdown   — power (uW) per gate type
    get_area_breakdown    — area (um²) per gate type
    get_fanout_analysis   — avg/max fanout, high-fanout net count

MAX ROUNDS:
    Agent loop runs for at most 8 rounds to prevent runaway API usage.
    In practice Claude typically completes in 3-5 rounds.

INPUT:
    stats  — dict from run_parser()  (circuit_parser JSON output)
    timing — dict from run_sta()     (sta_engine JSON output)
    api_key — Anthropic API key string

OUTPUT:
    Final LLM text response (str) — also streamed live to stdout.
    Empty string if the loop produces no text.

DEPENDENCIES:
    anthropic >= 0.96.0
"""

import json
from typing import Optional

import anthropic

# ── Tool definitions (Claude's API schema) ────────────────────────────────────
# Each dict follows the Anthropic tool-use schema:
#   name         : identifier Claude uses to call the tool
#   description  : natural language description that guides Claude's decisions
#   input_schema : JSON Schema for the tool's input parameters

TOOLS: list[dict] = [
    {
        "name": "get_circuit_summary",
        "description": (
            "Return high-level circuit statistics: total gate count split by "
            "combinational vs sequential, total area (um²), total power (uW), "
            "and power density (uW/um²). Call this first to get an overview."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_timing_analysis",
        "description": (
            "Return Static Timing Analysis results: target clock period (ns), "
            "critical path delay (ns), maximum operating frequency (MHz), "
            "timing pass/fail status, WNS (worst negative slack), TNS (total "
            "negative slack), and the ordered list of gates on the critical path."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_power_breakdown",
        "description": (
            "Return total power consumption (uW) broken down by gate type "
            "(e.g. DFF, XOR2, NAND2). Use this to identify which cell types "
            "dominate power and should be targeted for clock gating or resizing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_area_breakdown",
        "description": (
            "Return total area utilization (um²) broken down by gate type. "
            "Use this to identify cell types that dominate area, which may "
            "indicate opportunities for logic sharing or cell downsizing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_fanout_analysis",
        "description": (
            "Return net fanout statistics: average fanout, the net with the "
            "highest fanout and its count, and the number of nets exceeding "
            "the given threshold. High fanout nets degrade timing and need "
            "buffer insertion. Use threshold parameter to adjust classification."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "threshold": {
                    "type": "integer",
                    "description": (
                        "Fanout count above which a net is classified as "
                        "'high fanout'. Typical values: 4 (default), 8, 16."
                    ),
                }
            },
            "required": [],
        },
    },
]


# ── Tool handler ──────────────────────────────────────────────────────────────

def _handle_tool(name: str, tool_input: dict, stats: dict, timing: dict) -> str:
    """
    Execute a tool call and return the result as a JSON string.

    This is the bridge between Claude's tool-use requests and CircuitSense's
    internal data. Each branch extracts a specific slice of stats/timing and
    serialises it to JSON for Claude to consume in the next turn.

    Args:
        name:       Tool name from Claude's tool_use block (e.g. "get_timing_analysis")
        tool_input: Parameters Claude passed with the tool call (may be empty dict)
        stats:      Full circuit_parser JSON output dict
        timing:     Full sta_engine JSON output dict

    Returns:
        JSON string with the requested data, or an error JSON if tool is unknown.

    Note:
        This function is intentionally simple — it's a read-only view into
        already-computed data. No EDA analysis happens here; all computation
        is done upfront by the C++ tools.
    """
    if name == "get_circuit_summary":
        # Return the top-level PPA overview
        return json.dumps({
            "total_gates":         stats.get("total_gates", 0),
            "combinational_gates": stats.get("combinational_gates", 0),
            "sequential_gates":    stats.get("sequential_gates", 0),
            "total_area_um2":      stats.get("total_area_um2", 0),
            "total_power_uW":      stats.get("total_power_uW", 0),
            "power_density":       stats.get("power_density_uW_um2", 0),
        }, indent=2)

    elif name == "get_timing_analysis":
        # Return STA results including the critical path gate sequence
        return json.dumps({
            "target_period_ns":  timing.get("target_period_ns", 0),
            "critical_path_ns":  timing.get("critical_path_ns", 0),
            "max_frequency_mhz": timing.get("max_frequency_mhz", 0),
            "timing_met":        timing.get("timing_met", True),
            "wns_ns":            timing.get("wns_ns", 0),
            "tns_ns":            timing.get("tns_ns", 0),
            "critical_path":     timing.get("critical_path", []),
        }, indent=2)

    elif name == "get_power_breakdown":
        # Return power per gate type — Claude uses this to flag DFF dominance,
        # XOR2 clusters, etc. and suggest clock gating or cell swapping
        return json.dumps(stats.get("gate_type_power_uW", {}), indent=2)

    elif name == "get_area_breakdown":
        # Return area per gate type — used to identify area hotspots
        return json.dumps(stats.get("gate_type_area_um2", {}), indent=2)

    elif name == "get_fanout_analysis":
        # threshold is optional; Claude may pass a custom value to explore
        threshold = tool_input.get("threshold", 4)
        return json.dumps({
            "avg_fanout":       stats.get("avg_fanout", 0),
            "max_fanout":       stats.get("max_fanout", 0),
            "max_fanout_net":   stats.get("max_fanout_net", ""),
            "high_fanout_nets": stats.get("high_fanout_nets", 0),
            "threshold_used":   threshold,
        }, indent=2)

    # Fallback for any unrecognised tool name
    return json.dumps({"error": f"Unknown tool: {name}"})


# ── System and initial prompts ────────────────────────────────────────────────

# System prompt defines Claude's role and constraints for the whole session
_SYSTEM = (
    "You are an expert VLSI/EDA design engineer with deep knowledge of digital "
    "circuit optimisation, standard cell libraries, timing closure, and power "
    "reduction techniques. Use the available tools to gather circuit statistics, "
    "then provide concise, actionable design optimisation suggestions. "
    "Focus on the most impactful improvements first. Be specific — reference "
    "gate types, net names, and quantitative targets where possible."
)

# Initial user message that kicks off the agent loop
_INITIAL_PROMPT = (
    "Please analyse this VLSI circuit design comprehensively. "
    "Start by gathering circuit statistics using the tools provided, then give:\n"
    "1. Power optimisation suggestions\n"
    "2. Area optimisation suggestions\n"
    "3. Timing and fanout concerns\n"
    "4. Overall design quality assessment\n"
    "5. Single highest-priority recommendation\n\n"
    "Reference specific gate names, net names, and numbers from the data."
)


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_agent(stats: dict, timing: dict, api_key: str) -> str:
    """
    Run the agentic Claude review loop and return the final analysis text.

    The loop continues until Claude emits stop_reason="end_turn" (no more
    tool calls) or the maximum round limit is reached. Each tool call is
    handled locally by _handle_tool() — no additional network calls are made
    for tool execution; only the Claude API itself is contacted.

    All text blocks emitted by Claude during the loop are streamed to stdout
    in real time so the user can see progress.

    Args:
        stats:   Dict from run_parser() — circuit_parser JSON output.
        timing:  Dict from run_sta()   — sta_engine JSON output.
        api_key: Anthropic API key (sk-ant-...).

    Returns:
        Complete final text response from Claude as a single string.
        This is also embedded in the HTML report by report.py.
        Returns empty string if Claude produces no text blocks.

    Example:
        suggestions = run_agent(stats, timing, os.environ["ANTHROPIC_API_KEY"])
        # → "**Power Optimisation**\n- DFF cells consume 46% of total power..."
    """
    client   = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": _INITIAL_PROMPT}]

    print("\n" + "=" * 55)
    print("  Agentic LLM Review (Claude + Tool Use)")
    print("=" * 55)

    final_text = ""
    max_rounds = 8   # safety cap — Claude typically finishes in 3-5 rounds

    for _round in range(max_rounds):
        # Send current conversation to Claude; may return tool_use blocks
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        # Add Claude's full response to conversation history
        # (required for multi-turn tool-use — Claude needs to see its own calls)
        messages.append({"role": "assistant", "content": response.content})

        # Separate text blocks (Claude's prose) from tool_use blocks
        tool_calls  = [b for b in response.content if b.type == "tool_use"]
        text_blocks = [b for b in response.content if b.type == "text"]

        # Stream any text Claude produced this round to stdout
        if text_blocks:
            for tb in text_blocks:
                print(tb.text, end="", flush=True)
            final_text += "".join(tb.text for tb in text_blocks)

        # If Claude is done (no tool calls or explicit end_turn), stop the loop
        if response.stop_reason == "end_turn" or not tool_calls:
            break

        # Execute each tool call and collect results for the next turn
        tool_results = []
        for tc in tool_calls:
            # Print which tool is being called so the user can follow the reasoning
            args_str = json.dumps(tc.input) if tc.input else ""
            print(f"\n[tool] {tc.name}({args_str})")

            result = _handle_tool(tc.name, tc.input, stats, timing)
            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": tc.id,      # must match the tool_use block id
                "content":     result,      # JSON string returned to Claude
            })

        # Feed tool results back as a user message — continues the conversation
        messages.append({"role": "user", "content": tool_results})

    print("\n" + "=" * 55)
    return final_text
